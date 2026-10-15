"""Decision trace endpoints exposing why an architectural choice was made."""

from fastapi import APIRouter, HTTPException

from app.api.schemas import DecisionTraceResponse
from app.evidence.service import EvidenceService
from app.services.decision_service import DecisionTraceService

router = APIRouter(prefix="/decisions", tags=["Decisions"])

_service = DecisionTraceService()
_evidence = EvidenceService()


@router.get("/{decision_id}", response_model=DecisionTraceResponse)
async def get_decision_trace(decision_id: str):
    """Return rationale, alternatives, deciders and sources for a single decision."""
    result = _service.trace_decision(decision_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Decision '{decision_id}' was not found in the knowledge graph. "
                "Known decision: dec_kafka_async"
            ),
        )

    result["graph"] = _evidence.truncate_subgraph(result["graph"])
    return result