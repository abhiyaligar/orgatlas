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
