from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.core.config import settings
from app.graph.connection import graph_manager

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Report API liveness and whether the knowledge graph is reachable."""
    status = graph_manager.graph_status()
    return HealthResponse(
        status="ok",
        service="orgatlas-api",
        environment=settings.ENVIRONMENT,
        version="0.1.0",
        graph_connected=status["graph_connected"] and status["graph_exists"],
        graph_name=status["graph_name"],
        graph_exists=status["graph_exists"],
        available_graphs=status["available_graphs"],
    )