import logging
from typing import Optional
from falkordb import FalkorDB

from app.core.config import settings
from app.core.errors import GraphConnectionError

logger = logging.getLogger(__name__)


class FalkorDBManager:
    """Singleton connection manager for FalkorDB."""

    _instance: Optional["FalkorDBManager"] = None
    _client: Optional[FalkorDB] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FalkorDBManager, cls).__new__(cls)
        return cls._instance

    def get_client(self) -> FalkorDB:
        if self._client is None:
            try:
                logger.info(
                    "Connecting to FalkorDB at %s:%d (graph: %s)",
                    settings.FALKORDB_HOST,
                    settings.FALKORDB_PORT,
                    settings.FALKORDB_GRAPH_NAME,
                )
                self._client = FalkorDB(
                    host=settings.FALKORDB_HOST,
                    port=settings.FALKORDB_PORT,
                    username=settings.FALKORDB_USERNAME,
                    password=settings.FALKORDB_PASSWORD,
                )
            except Exception as e:
                logger.error("Failed to connect to FalkorDB: %s", str(e))
                raise GraphConnectionError(f"FalkorDB connection failed: {str(e)}")
        return self._client

    def get_graph(self):
        client = self.get_client()
        return client.select_graph(settings.FALKORDB_GRAPH_NAME)

    def check_health(self) -> bool:
        try:
            client = self.get_client()
            client.connection.ping()
            return True
        except Exception as e:
            logger.warning("FalkorDB health check failed: %s", str(e))
            return False

    def close(self):
        if self._client is not None:
            try:
                self._client.connection.close()
            except Exception:
                pass
            self._client = None


graph_manager = FalkorDBManager()
