import logging
from typing import List, Optional
from falkordb import FalkorDB

from redis.backoff import ExponentialWithJitterBackoff
from redis.retry import Retry

from app.core.config import settings
from app.core.errors import GraphConnectionError, GraphNotFoundError

# A bulk write in the model fallback can carry hundreds of rows in one query.
GRAPH_WRITE_TIMEOUT_SECONDS = 120
GRAPH_CONNECT_TIMEOUT_SECONDS = 10
GRAPH_HEALTH_CHECK_SECONDS = 30

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
                    # A bulk write over a few hundred rows outlasts any default
                    # read timeout, and the connection is idle for minutes while
                    # the model fallback runs. Without these, that write fails
                    # after the expensive work has already been paid for.
                    socket_timeout=GRAPH_WRITE_TIMEOUT_SECONDS,
                    socket_connect_timeout=GRAPH_CONNECT_TIMEOUT_SECONDS,
                    retry=Retry(ExponentialWithJitterBackoff(base=1, cap=10), retries=3),
                    socket_keepalive=True,
                    health_check_interval=GRAPH_HEALTH_CHECK_SECONDS,
                )
            except Exception as e:
                logger.error("Failed to connect to FalkorDB: %s", str(e))
                raise GraphConnectionError(f"FalkorDB connection failed: {str(e)}")
        return self._client

    def reset_client(self) -> None:
        """Discard a connection that has gone stale and build a fresh one.

        The client is a process-wide singleton, so a connection opened before a
        long model pass can be closed by the server long before it is next used.
        Dropping it is the only way to recover without a restart.
        """
        if self._client is None:
            return
        logger.warning("Discarding a stale FalkorDB connection")
        try:
            self._client.connection.close()
        except Exception as e:
            logger.debug("stale connection close failed, ignoring: %s", e)
        self._client = None

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
