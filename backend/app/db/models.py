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


class Document(Base):
    """One ingested document: an upload, or a Slack export entry.

    The full text lives here rather than on the graph node. A Document node in
    FalkorDB carries what retrieval needs -- title, kind, a summary, and the
    decisions and metrics extracted from it -- while the original text stays in
    the relational store where a blob of several thousand words belongs.
    """

    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)
    title = Column(String(500), nullable=False)
    # pdf | markdown | text | csv | slack
    kind = Column(String(20), nullable=False, index=True)
    # Where the original lives on disk, or the Slack permalink for a message.
    uri = Column(String(1000), nullable=True)
    # Content hash, so re-uploading the same file is a no-op rather than a
    # duplicate node with a second, possibly different, extraction.
    sha256 = Column(String(64), nullable=False, index=True)
    char_count = Column(Integer, nullable=False, default=0, server_default="0")
    text = Column(Text, nullable=True)
    # Author as stated by the source: an uploader, or a Slack speaker.
    author = Column(String(200), nullable=True)
    source_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "uri": self.uri,
            "sha256": self.sha256,
            "char_count": self.char_count,
            "author": self.author,
            "source_at": self.source_at.isoformat() if self.source_at else None,
        }


class DocumentExtraction(Base):
    """What the model pulled out of a document, kept verbatim and re-runnable.

    Stored as JSON so a prompt change does not require a schema change, and kept
    next to the raw response so an extraction can be audited against what the
    model actually returned rather than trusted.
    """

    __tablename__ = "document_extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(64), nullable=False, index=True)
    # decisions | people | quotes | metrics | entities
    payload = Column(Text, nullable=False)
    model = Column(String(200), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    input_sha = Column(String(64), nullable=True)
    trigger = Column(String(50), nullable=True)
    usage = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SlackMessage(Base):
    """One ingested Slack message, retained so 'who said what' is answerable."""

    __tablename__ = "slack_messages"

    id = Column(String(64), primary_key=True)
    channel_id = Column(String(64), nullable=False, index=True)
    channel_name = Column(String(200), nullable=True)
    slack_user_id = Column(String(64), nullable=True, index=True)
    author = Column(String(200), nullable=True)
    posted_at = Column(DateTime, nullable=True)
    text = Column(Text, nullable=True)
    permalink = Column(String(1000), nullable=True)
    thread_ts = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DocumentIngestJob(Base):
    """Tracks one document ingestion run from upload through to graph write."""

    __tablename__ = "document_ingest_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(500), nullable=False)
    kind = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="queued", server_default="queued", index=True)
    stage_detail = Column(String(500), nullable=True)
    documents_ingested = Column(Integer, nullable=False, default=0, server_default="0")
    decisions_extracted = Column(Integer, nullable=False, default=0, server_default="0")
    entities_linked = Column(Integer, nullable=False, default=0, server_default="0")
    metrics_extracted = Column(Integer, nullable=False, default=0, server_default="0")
    model_calls = Column(Integer, nullable=False, default=0, server_default="0")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
