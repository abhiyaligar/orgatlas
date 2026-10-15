from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.graph.connection import FalkorDBManager, graph_manager

# SQLAlchemy engine for metadata and audit logging
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
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
