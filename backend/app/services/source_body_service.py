"""Storing what a scan returned: bodies into object storage, pointers into Postgres.

Kept out of :mod:`app.ingestion.seed_repo` because it is a different concern --
the graph is the product and this is an addition to it. Every path through here
degrades to "source bodies were not stored" with a reason, because a repository
whose graph is complete is worth more than one that failed over a blob.

An ingest is also not blocked on storage being configured. With no bucket the
scan still produces a full graph, and the pointers table stays empty; retrieval
then reports that the body is absent rather than pretending it does not exist.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.db.models import SourceBody
from app.storage import source_store

logger = logging.getLogger(__name__)


def store_scan_sources(
    payload: Dict[str, Any],
    repository_id: str,
    commit_sha: str = "",
) -> Dict[str, Any]:
    """Upload the file bodies a scan returned and record their pointers.

    Content is deduplicated by digest, so an unchanged file across two ingests
    is one stored object. The pointer is written against the commit the scan
    read at, which is what pins a description to the code it describes.

    A failure here is reported and swallowed: the graph write already happened,
    and losing source bodies is a gap in retrieval, not a reason to fail an
    otherwise complete ingest.
    """
    source = payload.get("source") or {}
    files = source.get("files") or []

    if not files:
        return {"stored": 0, "bytes": 0, "skipped": source.get("skipped") or {}, "enabled": source_store.is_configured()}

    if not source_store.is_configured():
        logger.info(
            "Source storage is not configured; %d file body/bodies were not stored. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to serve file contents.",
            len(files),
        )
        return {
            "stored": 0,
            "bytes": 0,
            "skipped": {**source.get("skipped", {}), "storage_not_configured": len(files)},
            "enabled": False,
        }

    session_factory = _session_factory()
    if session_factory is None:
        return {"stored": 0, "bytes": 0, "skipped": {"database_unavailable": len(files)}, "enabled": True}

    sha = commit_sha or source.get("commit_sha") or payload.get("described_at_sha") or ""
    stored = 0
    total_bytes = 0
    failures: Dict[str, int] = {}

    try:
        source_store.ensure_bucket()
    except source_store.SourceStorageError as exc:
        logger.warning("Source bucket is not available: %s", exc)
        return {"stored": 0, "bytes": 0, "skipped": {"bucket_unavailable": len(files)}, "enabled": True}

    session = session_factory()
    try:
        for item in files:
            path = item["path"]
            text = item["text"]
            data = text.encode("utf-8")
            digest = source_store.content_digest(data)
            file_id = f"{repository_id}::{path}"

            try:
                key = source_store.store_blob(digest, data)
            except source_store.SourceStorageError as exc:
                # One file failing must not abandon the rest.
                logger.warning("Could not store %s: %s", path, exc)
                failures["upload_failed"] = failures.get("upload_failed", 0) + 1
                continue

            try:
                session.add(
                    SourceBody(
                        file_id=file_id,
                        repository_id=repository_id,
                        path=path,
                        commit_sha=sha,
                        content_sha256=digest,
                        storage_key=key,
                        byte_size=len(data),
                    )
                )
            except Exception as exc:  # pragma: no cover - constraint violation
                logger.warning("Could not record a pointer for %s: %s", path, exc)
                failures["pointer_failed"] = failures.get("pointer_failed", 0) + 1
                continue

            stored += 1
            total_bytes += len(data)

        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("Source pointers were not recorded: %s", exc)
        return {
            "stored": 0,
            "bytes": 0,
            "skipped": {**source.get("skipped", {}), "pointer_write_failed": len(files)},
            "enabled": True,
        }
    finally:
        session.close()

    skipped = dict(source.get("skipped") or {})
    skipped.update(failures)
    logger.info(
        "stored %d file body/bodies (%d bytes) for %s at %s",
        stored, total_bytes, repository_id, sha[:10] or "unknown",
    )
    return {"stored": stored, "bytes": total_bytes, "skipped": skipped, "enabled": True}


def _session_factory():
    """The app's session factory, or None when there is no database to write to."""
    try:
        from app.core.dependencies import SessionLocal

        return SessionLocal
    except Exception:  # pragma: no cover - configuration failure
        return None


def find_body(file_id: str) -> Optional[SourceBody]:
    """The stored body for a graph file id, most recent revision first."""
    from app.core.dependencies import SessionLocal

    from sqlalchemy import select

    session = SessionLocal()
    try:
        return session.execute(
            select(SourceBody)
            .where(SourceBody.file_id == file_id)
            .order_by(SourceBody.stored_at.desc())
            .limit(1)
        ).scalars().first()
    finally:
        session.close()


def pointer_count(repository_id: Optional[str] = None) -> int:
    """How many bodies are held, for reporting."""
    from sqlalchemy import func, select

    session = _session_factory()()
    try:
        query = select(func.count()).select_from(SourceBody)
        if repository_id:
            query = query.where(SourceBody.repository_id == repository_id)
        return int(session.execute(query).scalar() or 0)
    except Exception:
        return 0
    finally:
        session.close()