from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from app.db.base import Base


class AuditLog(Base):
    """Tracks all architecture and context queries for compliance and auditability."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_text = Column(Text, nullable=False)
    intent = Column(String(100), nullable=False)
    caller_type = Column(String(50), nullable=False, default="web_ui")  # web_ui, mcp_agent
    session_id = Column(String(100), nullable=True)
    execution_time_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SessionContext(Base):
    """Tracks user active session context (selected team, role, service)."""

    __tablename__ = "session_contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), unique=True, index=True, nullable=False)
    active_team_id = Column(String(100), nullable=True)
    active_service_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SchemaVersion(Base):
    """Records which schema revisions have been applied, per component."""

    __tablename__ = "schema_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    applied_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


INGEST_STATUSES = ("queued", "cloning", "parsing", "writing", "done", "failed")


class IngestJob(Base):
    """Tracks one repository ingestion run from queue through to graph write."""

    __tablename__ = "ingest_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_url = Column(String(500), nullable=False)
    repository_id = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="queued", server_default="queued", index=True)
    stage_detail = Column(String(500), nullable=True)
    commits_ingested = Column(Integer, nullable=False, default=0, server_default="0")
    files_indexed = Column(Integer, nullable=False, default=0, server_default="0")
    identities_resolved = Column(Integer, nullable=False, default=0, server_default="0")
    sandbox_id = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
