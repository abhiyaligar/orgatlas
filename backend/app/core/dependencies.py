from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.graph.connection import FalkorDBManager, graph_manager

# SQLAlchemy engine for metadata and audit logging
_IS_SQLITE = "sqlite" in settings.DATABASE_URL
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _IS_SQLITE else {},
    poolclass=StaticPool if settings.DATABASE_URL.startswith("sqlite:///:memory:") else None,
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _record):
    """Let readers run while a background ingest holds the write lock.

    A repository scan commits continuously for minutes while an upload request
    commits once. In rollback-journal mode the reader/writer exclusion meant the
    upload could time out and surface as a 500, even though nothing was wrong
    with it. WAL removes that contention; the busy timeout covers the remaining
    single-writer case. Journal mode is per-database, not per-connection, so it
    has to be set on every new connection.
    """
    if not _IS_SQLITE:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session for metadata and audit persistence."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_graph_manager() -> FalkorDBManager:
    """Dependency providing singleton access to FalkorDB."""
    return graph_manager
