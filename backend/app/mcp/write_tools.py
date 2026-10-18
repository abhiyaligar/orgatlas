"""MCP tools that change the knowledge graph.

Everything else the context server exposes is read-only. These are not, and they
say so: a tool that can rewrite the graph must not declare ``readOnlyHint``,
because that hint is what a client uses to decide whether it may run a tool
without asking anyone.

Two rules shape the design:

* **Enqueue, never block.** An ingestion clones a repository in an E2B sandbox
  and calls a model for every undocumented file. That runs for minutes, and an
  MCP call is a synchronous HTTP request. The tools therefore create a job and
  return its id; the caller polls.
* **A write token is required, and the REST ingest runs unchanged.** The tools
  reuse the same job row and the same background worker as
  ``POST /repos/ingest``, so there is one ingest path to reason about rather
  than two that drift.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from app.core.dependencies import SessionLocal
from app.db.models import AuditLog, IngestJob
from app.mcp import refusal
from app.mcp.scope import require_write

logger = logging.getLogger(__name__)


def _job_payload(job: IngestJob) -> Dict[str, Any]:
    return {
        "job_id": job.id,
        "repository_url": job.repository_url,
        "repository_id": job.repository_id,
        "status": job.status,
        "stage_detail": job.stage_detail,
        "commits_ingested": job.commits_ingested,
        "files_indexed": job.files_indexed,
        "identities_resolved": job.identities_resolved,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def enqueue_repository_ingest(repository_url: str) -> Dict[str, Any]:
    """Queue a repository ingestion and return immediately with a job id."""
    require_write()

    url = (repository_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return refusal("repository_url must be an http or https URL.")

    session = SessionLocal()
    try:
        job = IngestJob(
            repository_url=url,
            status="queued",
            stage_detail="queued via the MCP context server",
        )
        session.add(job)
        # The job records what happened; this records who asked for it. An
        # IngestJob is indistinguishable from one started over REST without it.
        session.add(
            AuditLog(
                query_text=url,
                intent="mcp_write_repository_ingest",
                caller_type="mcp_agent",
            )
        )
        session.commit()
        session.refresh(job)
        payload = _job_payload(job)
        job_id = job.id
    finally:
        session.close()

    # Started on its own thread rather than awaited, because ingest_repository is
    # blocking and the MCP call must return a job id rather than wait minutes.
    threading.Thread(
        target=_run, args=(job_id,), name=f"mcp-ingest-{job_id}", daemon=True
    ).start()

    payload["poll_with"] = "get_ingest_job"
    payload["note"] = (
        "This runs for minutes. Poll get_ingest_job until status is done or failed."
    )
    return payload


def get_ingest_job(job_id: int) -> Dict[str, Any]:
    """Report the current state of an ingestion job."""
    require_write()

    session = SessionLocal()
    try:
        job = session.get(IngestJob, int(job_id))
        if job is None:
            return refusal(f"No ingest job with id {job_id}.")
        return _job_payload(job)
    finally:
        session.close()


def _run(job_id: int) -> None:
    """Drive one ingestion, using the same worker the REST endpoint uses."""
    from app.api.routes.repos import _run_ingest

    job = _load(job_id)
    if job is None:
        return
    try:
        _run_ingest(job_id, job.repository_url)
    except Exception:
        logger.exception("MCP-triggered ingestion %s failed", job_id)


def _load(job_id: int) -> Optional[IngestJob]:
    session = SessionLocal()
    try:
        return session.get(IngestJob, job_id)
    finally:
        session.close()