from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import OrgAtlasError, orgatlas_exception_handler


def create_app() -> FastAPI:
    app = FastAPI(
        title="OrgAtlas API",
        description="Engineering onboarding and architecture decision knowledge agent powered by FalkorDB",
        version="0.1.0",
        debug=settings.DEBUG,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register custom exception handler
    app.add_exception_handler(OrgAtlasError, orgatlas_exception_handler)

    # Base health check endpoint
    @app.get("/api/health", tags=["Health"])
    async def health_check():
        return {
            "status": "ok",
            "service": "orgatlas-api",
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0",
        }

    return app


app = create_app()
