from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.core.config import settings
from app.graph.connection import graph_manager

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Report API liveness and whether the knowledge graph is reachable."""
    return HealthResponse(
        status="ok",
        service="orgatlas-api",
        environment=settings.ENVIRONMENT,
        version="0.1.0",
        graph_connected=graph_manager.check_health(),
    )