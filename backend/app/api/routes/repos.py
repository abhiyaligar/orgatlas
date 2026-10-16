"""Repository ingestion endpoints.

Ingestion is delegated to an isolated sandbox, so these handlers only accept
work, report progress, and surface the result. They never block on a clone.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import IngestJobResponse, IngestRequest, RepositorySummary
from app.core.dependencies import get_db
from app.db.models import IngestJob
from app.ingestion.sandbox_client import SandboxError, SandboxUnavailableError

router = APIRouter(prefix="/repos", tags=["Repositories"])
logger = logging.getLogger(__name__)


def _serialize(job: IngestJob) -> IngestJobResponse:
    return IngestJobResponse(
        id=job.id,
        repository_url=job.repository_url,
        repository_id=job.repository_id,
        status=job.status,
        stage_detail=job.stage_detail,
        commits_ingested=job.commits_ingested,
        files_indexed=job.files_indexed,
        identities_resolved=job.identities_resolved,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


def _run_ingest(job_id: int, repository_url: str) -> None:
    """Background entry point that drives one ingestion run."""
    from datetime import datetime, timezone

    from app.core.dependencies import SessionLocal
    from app.ingestion.seed_repo import ingest_repository

    session: Session = SessionLocal()
    job = session.get(IngestJob, job_id)
    if job is None:
        session.close()
        return

    def advance(status: str, detail: str | None = None) -> None:
        job.status = status
        if detail:
            job.stage_detail = detail[:500]
        session.commit()

    try:
        advance("cloning", "starting sandbox")
        summary = ingest_repository(
            repository_url,
            on_stage=lambda message: advance("cloning", message),
        )
        job.commits_ingested = summary.get("commits", 0)
        job.files_indexed = summary.get("files", 0)
        job.identities_resolved = summary.get("dependencies", 0)
        job.status = "done"
        job.stage_detail = "ingestion complete"
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
    except SandboxUnavailableError as exc:
        logger.warning("Ingestion not configured: %s", exc)
        job.status = "failed"
        job.error_message = str(exc)[:500]
        session.commit()
    except SandboxError as exc:
        logger.error("Sandbox ingestion failed: %s", exc)
        job.status = "failed"
        job.error_message = str(exc)[:500]
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected ingestion failure")
        job.status = "failed"
        job.error_message = f"{type(exc).__name__}: {exc}"[:500]
        session.commit()
    finally:
        session.close()


@router.post("/ingest", response_model=IngestJobResponse, status_code=202)
async def start_ingest(
    body: IngestRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue a repository ingestion and return immediately with a job id."""
    url = body.repository_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="repository_url must be an http(s) URL")

    job = IngestJob(repository_url=url, status="queued", stage_detail="queued for sandbox")
    db.add(job)
    db.commit()
    db.refresh(job)

    background.add_task(_run_ingest, job.id, url)
    logger.info("Queued ingestion job %s for %s", job.id, url)
    return _serialize(job)


@router.get("/ingest/{job_id}", response_model=IngestJobResponse)
async def get_ingest_job(job_id: int, db: Session = Depends(get_db)):
    """Return the current state of an ingestion job."""
    job = db.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Ingest job {job_id} not found")
    return _serialize(job)


@router.get("", response_model=list[RepositorySummary])
async def list_repositories(db: Session = Depends(get_db)):
    """List ingested repositories and their direct dependency edges."""
    from app.graph.gateway import graph_gateway

    rows = graph_gateway.search_entities("http")
    repositories = [
        RepositorySummary(
            id=row["id"],
            name=row["name"],
            url=row["properties"].get("url", ""),
            source=row["properties"].get("source"),
        )
        for row in rows
        if row.get("label") == "Repository" and row.get("id", "").startswith("repo_")
    ]
    return repositories