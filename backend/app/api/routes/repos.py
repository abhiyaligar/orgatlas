"""Repository ingestion endpoints.

Ingestion is delegated to an isolated sandbox, so these handlers only accept
work, report progress, and surface the result. They never block on a clone.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChurnResponse,
    CommitSummary,
    CouplingResponse,
    FileDescriptionResponse,
    FileTimelineResponse,
    IngestJobResponse,
    IngestRequest,
    InvestigationBriefResponse,
    SymbolDescriptionResponse,
    ProvenanceResponse,
    RepositorySummary,
)
from app.core.dependencies import get_db
from app.db.models import IngestJob
from app.ingestion.sandbox_client import SandboxError, SandboxUnavailableError
from app.services.change_forensics_service import ChangeForensicsService
from app.services.commit_provenance_service import CommitProvenanceService

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


def _progress_advance(job, session, stage: str):
    """Report the stage a message belongs to, so the panel shows real progress.

    The scan runs sandbox creation, clone, parsing, graph writes and the
    description fallback in one call. Mapping its stage messages onto distinct
    statuses is what lets a caller see a scan progressing instead of sitting on
    one label for its whole duration. Messages that match nothing only refresh
    the detail text, so an unmapped message never invents a status change.
    """
    stages = (
        ("creating sandbox", "cloning"),
        ("syncing", "cloning"),
        ("starting clone", "cloning"),
        ("cloning", "cloning"),
        ("scanned", "writing"),
        ("batch", "writing"),
        ("model fallback", "describing"),
    )

    def report(message: str) -> None:
        for marker, status in stages:
            if marker in message.lower():
                job.status = status
                job.stage_detail = message[:500]
                session.commit()
                return
        job.stage_detail = message[:500]
        session.commit()

    return report


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
        advance("queued", "sandbox created")
        advance("cloning", "cloning the target repository")
        summary = ingest_repository(
            repository_url,
            on_stage=lambda message: advance("cloning", message),
            on_progress=_progress_advance(job, session, "parsing"),
        )
        job.commits_ingested = summary.get("commits", 0)
        job.files_indexed = summary.get("files", 0)
        # identities_resolved counts contributors, not declared dependencies.
        job.identities_resolved = int(summary.get("identities_resolved", 0))
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
async def list_repositories():
    """List ingested repositories with their commit and file counts."""
    from app.graph.gateway import graph_gateway

    rows = graph_gateway.list_repositories()
    summaries = []
    for row in rows:
        summary = RepositorySummary(
            id=row["id"], name=row["name"], url=row["url"], source=row["source"] or None
        )
        summary.commit_count = row["commit_count"]
        summary.file_count = row["file_count"]
        summaries.append(summary)
    return summaries


# --- Read-only forensics -----------------------------------------------------
# These answer questions a developer or coding agent asks mid-task. They never
# write, and every traversal is bounded.

_forensics = ChangeForensicsService()
_provenance = CommitProvenanceService()


def _require_repository(repository_id: str) -> None:
    from app.graph.gateway import graph_gateway

    if not graph_gateway.repository_exists(repository_id):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Repository '{repository_id}' is not in the knowledge graph. "
                "Ingest it first via POST /api/repos/ingest."
            ),
        )


@router.get("/{repository_id}/brief", response_model=InvestigationBriefResponse)
async def get_investigation_brief(repository_id: str, path_prefix: str = ""):
    """Where to start in an unfamiliar area: volatile files, owners, blast radius."""
    _require_repository(repository_id)
    return _forensics.investigation_brief(repository_id, path_prefix=path_prefix)


@router.get("/{repository_id}/churn", response_model=ChurnResponse)
async def get_file_churn(repository_id: str, path_prefix: str = "", limit: int = 25):
    """Rank files by how often they change."""
    _require_repository(repository_id)
    return _forensics.churn_ranking(repository_id, path_prefix=path_prefix, limit=limit)


@router.get("/file/timeline", response_model=FileTimelineResponse)
async def get_file_timeline(file_id: str, limit: int = 50):
    """Who changed a file, when, and through which pull request."""
    result = _forensics.file_timeline(file_id, limit=limit)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ingested history for file '{file_id}'. Ingest the repository first.",
        )
    result["graph"] = _forensics.evidence.truncate_subgraph(result["graph"])
    return result


@router.get("/file/describe", response_model=FileDescriptionResponse)
async def describe_file(file_id: str):
    """Describe a file from the documentation its authors wrote.

    The summary and symbols come from the file's own ``//!``/``///`` docs or
    declarations as they were at ingest time. The response says explicitly
    whether that description is still current.
    """
    result = _forensics.describe_file(file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"File '{file_id}' is not in the knowledge graph. "
                "Ingest the repository first."
            ),
        )
    return result


@router.get("/file/coupling", response_model=CouplingResponse)
async def get_file_coupling(file_id: str, limit: int = 15):
    """Files that historically change in the same commits as this one."""
    return _forensics.coupled_files(file_id, limit=limit)


@router.get("/{repository_id}/commits", response_model=list[CommitSummary])
async def get_module_commits(repository_id: str, path_prefix: str, limit: int = 50):
    """Recent commits touching a module or directory."""
    _require_repository(repository_id)
    return _forensics.module_history(
        repository_id, path_prefix=path_prefix, limit=limit
    )["commits"]


@router.get("/commit/{commit_id}", response_model=ProvenanceResponse)
async def get_commit_provenance(commit_id: str):
    """Trace a commit to its author, pull request, decisions and sources."""
    result = _provenance.trace(commit_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Commit '{commit_id}' is not in the knowledge graph."
        )
    return result
@router.get("/file/symbols/{name}", response_model=SymbolDescriptionResponse)
async def describe_symbol(name: str, file_id: str = "", limit: int = 10):
    """Explain a declaration from the documentation its authors wrote.

    Returns every match when a name is shared, each with its container, so the
    caller can tell them apart instead of receiving a silently chosen one.
    """
    return _forensics.describe_symbol(name, file_id=file_id, limit=limit)