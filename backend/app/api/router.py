"""Central API router aggregating every versioned route module."""

from fastapi import APIRouter

from app.api.routes import ask, decisions, demo_prompts, entities, health, onboarding, repos

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(demo_prompts.router)
api_router.include_router(onboarding.router)
api_router.include_router(decisions.router)
api_router.include_router(entities.router)
api_router.include_router(repos.router)
api_router.include_router(ask.router)