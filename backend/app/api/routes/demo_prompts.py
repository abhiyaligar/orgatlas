from typing import List
from fastapi import APIRouter
from app.api.schemas import DemoPrompt
from app.services.demo_prompt_service import DemoPromptService

router = APIRouter(prefix="/demo-prompts", tags=["Demo"])
_service = DemoPromptService()


@router.get("", response_model=List[DemoPrompt])
async def get_demo_prompts():
    """Returns the 5 stable curated demo questions for the seeded graph."""
    return _service.get_all_prompts()
