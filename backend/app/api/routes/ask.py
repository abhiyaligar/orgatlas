import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import AskQuestionRequest, AskQuestionResponse
from app.services.ask_service import AskService

router = APIRouter(prefix="/ask", tags=["Ask"])
logger = logging.getLogger(__name__)

_ask = AskService()


@router.post("", response_model=AskQuestionResponse)
async def ask_question(body: AskQuestionRequest):
    """Route a question to an approved intent and return a graph-grounded answer.

    The answer narrative is written by the model from retrieved evidence, and
    every citation it emits is validated against that evidence. If the provider
    is unavailable, or the narrative cannot be grounded, the same evidence is
    answered deterministically instead.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    package = _ask.retrieve(question, body.context)

    if package is None:
        logger.info("No approved intent matched; returning insufficient evidence")
        return _ask.insufficient(question)

    package["confidence"] = _ask.confidence_for(
        package.get("citations") or [], package.get("graph")
    )
    package = await _ask.synthesize(question, package)
    return _ask.build_response(question, package)