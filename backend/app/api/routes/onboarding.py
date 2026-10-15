from fastapi import APIRouter, HTTPException
from app.api.schemas import OnboardingMapResponse
from app.services.onboarding_service import OnboardingContextService
from app.evidence.service import EvidenceService

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])
_onboarding = OnboardingContextService()
_evidence = EvidenceService()


@router.get("/{team_id}", response_model=OnboardingMapResponse)
async def get_onboarding_map(team_id: str):
    """Returns full first-week onboarding journey for a team including services, topics, and people."""
    result = _onboarding.get_onboarding_map(team_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No onboarding data found for team '{team_id}'. Valid IDs: team_payments, team_platform",
        )
    result.graph = _evidence.truncate_subgraph(result.graph)
    return result
