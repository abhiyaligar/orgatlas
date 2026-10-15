from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse


class OrgAtlasError(Exception):
    """Base error for all application-level errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class GraphConnectionError(OrgAtlasError):
    def __init__(self, message: str = "Unable to connect to FalkorDB knowledge graph"):
        super().__init__(message=message, status_code=503)


class GraphNotFoundError(OrgAtlasError):
    def __init__(self, graph_name: str, available: list):
        super().__init__(
            message=(
                f"FalkorDB graph '{graph_name}' does not exist on this instance. "
                f"Available graphs: {', '.join(available) or 'none'}. "
                "Check FALKORDB_GRAPH_NAME, or run the seed script to create it."
            ),
            status_code=503,
            details={"graph_name": graph_name, "available_graphs": available},
        )


class GraphQueryError(OrgAtlasError):
    def __init__(self, message: str = "Knowledge graph query failed"):
        super().__init__(message=message, status_code=503)


class EntityNotFoundError(OrgAtlasError):
    def __init__(self, entity_id: str):
        super().__init__(
            message=f"Entity with ID '{entity_id}' not found in knowledge graph",
            status_code=404,
            details={"entity_id": entity_id},
        )


class InsufficientEvidenceError(OrgAtlasError):
    def __init__(self, query: str):
        super().__init__(
            message="No supporting evidence found in knowledge graph for query",
            status_code=200,
            details={"query": query, "confidence": "insufficient"},
        )


async def orgatlas_exception_handler(request: Request, exc: OrgAtlasError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.message,
                "type": exc.__class__.__name__,
                "details": exc.details,
            }
        },
    )
