import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.api.schemas import AskQuestionRequest, AskQuestionResponse
from app.evidence.service import EvidenceService
from app.services.decision_service import DecisionTraceService
from app.services.impact_service import ChangeImpactService
from app.services.onboarding_service import OnboardingContextService
from app.services.ownership_service import OwnershipService

router = APIRouter(prefix="/ask", tags=["Ask"])
logger = logging.getLogger(__name__)

_evidence = EvidenceService()
_decisions = DecisionTraceService(evidence=_evidence)
_impact = ChangeImpactService(evidence=_evidence)
_onboarding = OnboardingContextService(evidence=_evidence)
_ownership = OwnershipService(evidence=_evidence)

ONBOARDING_KEYWORDS = ("onboard", "first week", "new engineer", "learning path", "week one", "join")
DECISION_KEYWORDS = (
    "why",
    "kafka",
    "decision",
    "chose",
    "chosen",
    "architecture",
    "decided",
    "instead",
    "rationale",
    "reason",
)
IMPACT_KEYWORDS = (
    "impact",
    "change",
    "changing",
    "affect",
    "affecting",
    "depend",
    "before changing",
    "what depends",
    "risk",
)
OWNERSHIP_KEYWORDS = (
    "who owns",
    "owner",
    "maintainer",
    "who is responsible",
    "who should i contact",
    "expertise",
    "experience",
    "worked on",
    "expert",
)

DECISION_ENTITIES = {
    "kafka": "dec_kafka_async",
    "checkout": "dec_kafka_async",
    "synchronous": "dec_kafka_async",
    "settlement": "dec_kafka_async",
}
SERVICE_ENTITIES = {
    "checkout": "svc_checkout",
    "token": "svc_token_service",
    "billing": "svc_billing",
    "notification": "svc_notification",
}
TEAM_ENTITIES = {
    "payments": "team_payments",
    "platform": "team_platform",
    "infrastructure": "team_platform",
}

DEFAULT_TEAM_ID = "team_payments"


def _classify_intent(question: str) -> Optional[str]:
    """Map a question to an approved retrieval intent, or None when nothing matches."""
    normalized = question.lower()

    if any(keyword in normalized for keyword in ONBOARDING_KEYWORDS):
        return "onboarding"
    if any(keyword in normalized for keyword in DECISION_KEYWORDS):
        return "decision"

    asks_ownership = any(keyword in normalized for keyword in OWNERSHIP_KEYWORDS)
    asks_impact = any(keyword in normalized for keyword in IMPACT_KEYWORDS)

    if asks_ownership and not asks_impact:
        return "ownership"
    if asks_impact:
        return "impact"
    if asks_ownership:
        return "ownership"
    return None


def _resolve_entity(question: str, entity_map: dict) -> Optional[str]:
    """Resolve a stable entity id from the question text."""
    normalized = question.lower()
    for keyword, entity_id in entity_map.items():
        if keyword in normalized:
            return entity_id
    return None


def _build_onboarding_answer(question: str, team_id: str) -> Optional[dict]:
    result = _onboarding.get_onboarding_map(team_id)
    if result is None:
        return None

    topics = "\n".join(f"{topic.sequence}. {topic.title} — {topic.summary}" for topic in result.topics)
    services = ", ".join(service.name for service in result.owned_services) or "none recorded"
    people = ", ".join(f"{person.name} ({person.role})" for person in result.people_to_meet) or "none recorded"

    return {
        "answer": (
            f"**Onboarding guide for {result.team_name}**\n\n"
            f"**Mission:** {result.mission}\n\n"
            f"**First-week learning path:**\n{topics}\n\n"
            f"**Services you own:** {services}\n\n"
            f"**People to meet:** {people}"
        ),
        "evidence_summary": (
            f"Retrieved from the team graph: {len(result.topics)} topics, "
            f"{len(result.owned_services)} services, {len(result.people_to_meet)} people."
        ),
        "citations": result.reading_list,
        "graph": result.graph,
        "confidence": _evidence.compute_confidence(result.reading_list, result.graph),
        "suggested_questions": [
            "Why does Checkout use Kafka instead of synchronous calls?",
            "Who owns Token Service and what depends on it?",
        ],
    }


def _build_decision_answer(decision_id: str) -> Optional[dict]:
    result = _decisions.trace_decision(decision_id)
    if result is None:
        return None

    decided_at = result["decided_at"][:10] if result["decided_at"] else "not recorded"
    return {
        "answer": (
            f"**Decision: {result['title']}**\n\n{result['summary']}\n\n"
            f"**Alternatives considered:** {result['alternatives'] or 'none recorded'}\n\n"
            f"**Status:** {result['status']} (decided {decided_at})"
        ),
        "evidence_summary": (
            f"Traced from the FalkorDB decision graph. {len(result['citations'])} source(s) found."
        ),
        "citations": result["citations"],
        "graph": result["graph"],
        "confidence": _evidence.compute_confidence(result["citations"], result["graph"]),
        "suggested_questions": [
            "Who owns Checkout Service and what are its dependencies?",
            "Which incident led to this decision?",
        ],
    }


def _build_impact_answer(service_id: str) -> Optional[dict]:
    result = _impact.assess_impact(service_id)
    if result is None:
        return None

    return {
        "answer": (
            f"**Change Impact: {result['service_name']}**\n\n"
            f"**Owner:** {result['owner_team'] or 'not recorded'}\n"
            f"**Downstream dependencies:** {result['downstream_count']}\n"
            f"**Upstream consumers:** {result['upstream_count']}\n\n"
            f"**Risk notes:** {result['risk_notes']}"
        ),
        "evidence_summary": (
            f"Traversed up to 2 hops from {result['service_name']}. "
            f"{len(result['citations'])} incident/decision record(s) found."
        ),
        "citations": result["citations"],
        "graph": result["graph"],
        "confidence": _evidence.compute_confidence(result["citations"], result["graph"]),
        "suggested_questions": [
            "Who should I contact before changing this service?",
            "What incidents have affected this service?",
        ],
    }


def _build_ownership_answer(service_id: str) -> Optional[dict]:
    result = _ownership.get_ownership(service_id)
    if result is None:
        return None

    members = ", ".join(f"{member['name']} ({member['role']})" for member in result["team_members"]) or "none recorded"
    contributors = ", ".join(person["name"] for person in result["contributors"]) or "none recorded"

    return {
        "answer": (
            f"**Ownership: {result['service_name']}**\n\n"
            f"**Owner team:** {result['owner_team'] or 'not recorded'}\n"
            f"**Team members:** {members}\n"
            f"**Contributors:** {contributors}\n"
            f"**Repository:** {result['repository_url'] or 'not recorded'}"
        ),
        "evidence_summary": (
            f"Retrieved ownership from FalkorDB. {len(result['team_members'])} team member(s), "
            f"{len(result['contributors'])} contributor(s)."
        ),
        "citations": result["citations"],
        "graph": result["graph"],
        "confidence": _evidence.compute_confidence(result["citations"], result["graph"]),
        "suggested_questions": [
            "What depends on this service?",
            "What incidents have affected this service?",
        ],
    }


@router.post("", response_model=AskQuestionResponse)
async def ask_question(body: AskQuestionRequest):
    """Route a question to an approved intent and return a graph-grounded answer."""
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    intent = _classify_intent(question)
    logger.info("Ask intent '%s' for session=%s", intent, body.session_id or "anonymous")

    if intent == "onboarding":
        team_id = (
            (body.context or "").strip()
            or _resolve_entity(question, TEAM_ENTITIES)
            or DEFAULT_TEAM_ID
        )
        if not team_id.startswith("team_"):
            team_id = DEFAULT_TEAM_ID
        payload = _build_onboarding_answer(question, team_id)
    elif intent == "decision":
        decision_id = _resolve_entity(question, DECISION_ENTITIES)
        payload = _build_decision_answer(decision_id) if decision_id else None
    elif intent == "impact":
        service_id = _resolve_entity(question, SERVICE_ENTITIES)
        payload = _build_impact_answer(service_id) if service_id else None
    elif intent == "ownership":
        service_id = _resolve_entity(question, SERVICE_ENTITIES)
        payload = _build_ownership_answer(service_id) if service_id else None
    else:
        logger.info("No approved intent matched question; returning insufficient evidence")
        payload = None

    if payload is None:
        return AskQuestionResponse(**_evidence.build_insufficient_response(question))

    payload["graph"] = _evidence.truncate_subgraph(payload["graph"])
    return AskQuestionResponse(**payload)