"""Upload documents and Slack history; read decisions with their whole story.

Document ingestion is asynchronous for the same reason repository ingestion is:
extraction calls a model per document, and a CSV of decision records can be
hundreds of rows. The upload returns a job id immediately and the caller polls.

Extraction is optional per request. A caller uploading a file to link it into the
graph without spending model calls can say so, and the pipeline still parses,
stores and links -- it just extracts nothing.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.schemas import (
    DecisionEvidenceResponse,
    DocumentIngestStatus,
    DocumentSummaryResponse,
    SlackIngestResponse,
    SlackMessageIngestRequest,
)
from app.core.dependencies import SessionLocal
from app.db.models import Document, DocumentIngestJob
from app.ingestion.document_ingest import DocumentIngestor
from app.ingestion.doc_parsers import DocumentParseError, kind_for_filename
from app.services.decision_evidence_service import DecisionEvidenceService

router = APIRouter(prefix="/docs", tags=["Documents"])
logger = logging.getLogger(__name__)

# A model call per document is the expensive part, so an upload is bounded.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _to_status(job: DocumentIngestJob) -> DocumentIngestStatus:
    return DocumentIngestStatus(
        id=job.id,
        filename=job.filename,
        kind=job.kind,
        status=job.status,
        stage_detail=job.stage_detail,
        documents_ingested=job.documents_ingested,
        decisions_extracted=job.decisions_extracted,
        entities_linked=job.entities_linked,
        metrics_extracted=job.metrics_extracted,
        model_calls=job.model_calls,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


def _run_ingest(
    job_id: int,
    data: bytes,
    filename: str,
    title: Optional[str],
    author: Optional[str],
    run_extraction: bool,
) -> None:
    """Background work for one upload. Never raises; records the failure."""
    session: Session = SessionLocal()
    try:
        ingestor = DocumentIngestor()

        def advance(message: str) -> None:
            job = session.get(DocumentIngestJob, job_id)
            if job is None:
                return
            job.stage_detail = message[:500]
            session.commit()

        job = session.get(DocumentIngestJob, job_id)
        if job is not None:
            job.status = "parsing"
            session.commit()

        summary = ingestor.ingest(
            data,
            filename,
            title=title,
            author=author,
            on_stage=advance,
            run_extraction=run_extraction,
        )

        job = session.get(DocumentIngestJob, job_id)
        if job is not None:
            job.status = "done"
            job.documents_ingested = summary.get("documents", 0)
            job.decisions_extracted = summary.get("decisions", 0)
            job.entities_linked = summary.get("entities_linked", 0)
            job.metrics_extracted = summary.get("metrics", 0)
            job.model_calls = summary.get("model_calls", 0)
            from datetime import datetime, timezone

            job.completed_at = datetime.now(timezone.utc)
            session.commit()
    except DocumentParseError as exc:
        session.rollback()
        job = session.get(DocumentIngestJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("document ingest failed")
        session.rollback()
        job = session.get(DocumentIngestJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"
            session.commit()
    finally:
        session.close()


@router.post("", response_model=DocumentIngestStatus)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    author: Optional[str] = Form(default=None),
    extract: bool = Form(default=True),
):
    """Accept a document and ingest it in the background.

    Returns immediately with a job id. The same pipeline serves the API and any
    script, so a document ingested here is retrievable through ``/ask`` and MCP
    exactly as a seeded one is.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {MAX_UPLOAD_BYTES} bytes",
        )

    # The file type is checked before a job exists. Discovering it afterwards
    # made an unsupported upload answer 200 with status "failed", so a client
    # reading only the status code saw success for a rejected file.
    filename = file.filename or "document"
    try:
        kind = kind_for_filename(filename)
    except DocumentParseError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    session: Session = SessionLocal()
    try:
        job = DocumentIngestJob(filename=filename, kind=kind, status="queued")
        session.add(job)
        session.commit()
        job_id = job.id
    finally:
        session.close()

    import anyio

    await anyio.to_thread.run_sync(
        lambda: _run_ingest(job_id, data, filename, title, author, extract)
    )

    session = SessionLocal()
    try:
        stored = session.get(DocumentIngestJob, job_id)
        return _to_status(stored)
    finally:
        session.close()


@router.get("/ingest/{job_id}", response_model=DocumentIngestStatus)
def poll_ingest(job_id: int):
    """Poll a document ingestion job."""
    session: Session = SessionLocal()
    try:
        job = session.get(DocumentIngestJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"no document job {job_id}")
        return _to_status(job)
    finally:
        session.close()


@router.get("", response_model=List[DocumentSummaryResponse])
def list_documents(limit: int = 50, kind: Optional[str] = None):
    """List ingested documents with what was extracted from each."""
    session: Session = SessionLocal()
    try:
        query = session.query(Document)
        if kind:
            query = query.filter(Document.kind == kind)
        rows = query.order_by(Document.created_at.desc()).limit(min(limit, 200)).all()

        return [
            DocumentSummaryResponse(
                id=row.id,
                title=row.title,
                kind=row.kind,
                uri=row.uri,
                sha256=row.sha256,
                char_count=row.char_count,
                author=row.author,
                source_at=row.source_at.isoformat() if row.source_at else None,
                summary=(row.text or "")[:2000],
                decisions=0,
                metrics=0,
            )
            for row in rows
        ]
    finally:
        session.close()


@router.post("/slack/ingest", response_model=SlackIngestResponse)
def ingest_slack(payload: SlackMessageIngestRequest):
    """Ingest Slack history so "who said what" is answerable with a citation.

    Each message is stored as an excerpt and linked to whatever it was about. A
    speaker who is not already in the graph is left unattributed rather than
    invented as a person.
    """
    if not payload.messages:
        return SlackIngestResponse()

    ingestor = DocumentIngestor()
    summary = ingestor.ingest_slack_messages(
        [message.model_dump() for message in payload.messages]
    )
    return SlackIngestResponse(**summary)


@router.get("/decisions/{decision_id}", response_model=DecisionEvidenceResponse)
def get_decision(decision_id: str):
    """Every kind of evidence attached to one decision, with its gaps stated."""
    evidence = DecisionEvidenceService().get_evidence(decision_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"no decision {decision_id}")
    return evidence