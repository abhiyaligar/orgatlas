import logging
from typing import List, Optional
from falkordb import FalkorDB

from app.core.config import settings
from app.core.errors import GraphConnectionError, GraphNotFoundError

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

    def list_graphs(self) -> List[str]:
        """Return every graph name that exists on the connected instance."""
        try:
            return list(self.get_client().list_graphs())
        except Exception as e:
            logger.error("Failed to list FalkorDB graphs: %s", str(e))
            raise GraphConnectionError(f"Unable to list FalkorDB graphs: {str(e)}")

    def get_graph(self):
        """Return the configured graph, refusing to silently return an empty one.

        select_graph() accepts any name and yields a usable handle, so a typo in
        FALKORDB_GRAPH_NAME otherwise looks exactly like an unseeded graph.
        """
        graph_name = settings.FALKORDB_GRAPH_NAME
        available = self.list_graphs()
        if graph_name not in available:
            logger.error("Graph '%s' not found. Available: %s", graph_name, available)
            raise GraphNotFoundError(graph_name, available)
        return self.get_client().select_graph(graph_name)

    def get_or_create_graph(self):
        """Return the configured graph, allowing it to be created by a later write.

        Used only by the seed workflow, where the graph is expected to be absent
        on a first run.
        """
        return self.get_client().select_graph(settings.FALKORDB_GRAPH_NAME)

    def check_health(self) -> bool:
        try:
            client = self.get_client()
            client.connection.ping()
            return True
        except Exception as e:
            logger.warning("FalkorDB health check failed: %s", str(e))
            return False

    def graph_status(self) -> dict:
        """Report connectivity and whether the configured graph actually exists.

        Reported separately from the connection check so a wrong graph name is
        never mistaken for an unseeded graph.
        """
        graph_name = settings.FALKORDB_GRAPH_NAME
        connected = self.check_health()
        if not connected:
            return {"graph_name": graph_name, "graph_connected": False, "graph_exists": False, "available_graphs": []}

        try:
            available = list(self.get_client().list_graphs())
        except Exception as e:
            logger.warning("Unable to list graphs for health check: %s", str(e))
            return {"graph_name": graph_name, "graph_connected": True, "graph_exists": False, "available_graphs": []}

        return {
            "graph_name": graph_name,
            "graph_connected": True,
            "graph_exists": graph_name in available,
            "available_graphs": available,
        }

    def close(self):
        if self._client is not None:
            try:
                self._client.connection.close()
            except Exception:
                pass
            self._client = None


graph_manager = FalkorDBManager()
