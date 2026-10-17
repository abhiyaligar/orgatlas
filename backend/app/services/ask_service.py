"""Ask-question orchestration: intent routing, evidence assembly, answer shape.

This module owns everything that happens between a question and an
``AskQuestionResponse``. Keeping it out of the route means the route only
validates input and serialises output, and it gives the answer-synthesis
boundary one place to live.

Retrieval is deliberately split from presentation. The retrieval services return
structured evidence; building the deterministic narrative from it is one step,
and asking the model to write a narrative from the same evidence is another.
The two are alternatives, never sequential, so a slow or missing provider never
blocks the deterministic answer.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import AskQuestionResponse, EvidenceSubgraph
from app.evidence.service import EvidenceService
from app.services.decision_service import DecisionTraceService
from app.services.impact_service import ChangeImpactService
from app.services.onboarding_service import OnboardingContextService
from app.services.ownership_service import OwnershipService

logger = logging.getLogger(__name__)

ONBOARDING_KEYWORDS = (
    "onboard",
    "first week",
    "new engineer",
    "learning path",
    "week one",
    "join",
)
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


class AskService:
    """Routes a question to an approved intent and assembles its evidence."""

    def __init__(
        self,
        evidence: Optional[EvidenceService] = None,
        decisions: Optional[DecisionTraceService] = None,
        impact: Optional[ChangeImpactService] = None,
        onboarding: Optional[OnboardingContextService] = None,
        ownership: Optional[OwnershipService] = None,
    ) -> None:
        self.evidence = evidence or EvidenceService()
        self.decisions = decisions or DecisionTraceService(evidence=self.evidence)
        self.impact = impact or ChangeImpactService(evidence=self.evidence)
        self.onboarding = onboarding or OnboardingContextService(evidence=self.evidence)
        self.ownership = ownership or OwnershipService(evidence=self.evidence)

    # --- intent routing ------------------------------------------------------

    @staticmethod
    def classify_intent(question: str) -> Optional[str]:
        """Map a question to an approved retrieval intent, or None."""
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

    @staticmethod
    def resolve_entity(question: str, entity_map: Dict[str, str]) -> Optional[str]:
        normalized = question.lower()
        for keyword, entity_id in entity_map.items():
            if keyword in normalized:
                return entity_id
        return None

    def resolve_team_id(self, question: str, context: Optional[str]) -> str:
        candidate = (context or "").strip()
        if not candidate:
            candidate = self.resolve_entity(question, TEAM_ENTITIES) or DEFAULT_TEAM_ID
        return candidate if candidate.startswith("team_") else DEFAULT_TEAM_ID

    # --- evidence retrieval --------------------------------------------------

    def retrieve(self, question: str, context: Optional[str]) -> Optional[Dict[str, Any]]:
        """Run the approved retrieval for a question and build its evidence package.

        Returns ``None`` when nothing matches, which the caller turns into an
        explicit insufficient-evidence response rather than a guess.
        """
        intent = self.classify_intent(question)
        logger.info("Ask intent '%s'", intent)

        if intent == "onboarding":
            return self.retrieve_onboarding(question, context)
        if intent == "decision":
            decision_id = self.resolve_entity(question, DECISION_ENTITIES)
            return self.retrieve_decision(decision_id) if decision_id else None
        if intent in ("impact", "ownership"):
            service_id = self.resolve_entity(question, SERVICE_ENTITIES)
            if not service_id:
                return None
            return (
                self.retrieve_impact(service_id)
                if intent == "impact"
                else self.retrieve_ownership(service_id)
            )
        return None

    def retrieve_onboarding(
        self, question: str, context: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        team_id = self.resolve_team_id(question, context)
        result = self.onboarding.get_onboarding_map(team_id)
        if result is None:
            return None

        topics = "\n".join(
            f"{topic.sequence}. {topic.title} — {topic.summary}"
            for topic in result.topics
        )
        services = (
            ", ".join(service.name for service in result.owned_services)
            or "none recorded"
        )
        people = (
            ", ".join(
                f"{person.name} ({person.role})" for person in result.people_to_meet
            )
            or "none recorded"
        )

        answer = (
            f"**Onboarding guide for {result.team_name}**\n\n"
            f"**Mission:** {result.mission}\n\n"
            f"**First-week learning path:**\n{topics}\n\n"
            f"**Services you own:** {services}\n\n"
            f"**People to meet:** {people}"
        )

        return {
            "intent": "onboarding",
            "entity_id": team_id,
            "answer": answer,
            "evidence_summary": (
                f"Retrieved from the team graph: {len(result.topics)} topics, "
                f"{len(result.owned_services)} services, "
                f"{len(result.people_to_meet)} people."
            ),
            "citations": result.reading_list,
            "graph": result.graph,
            "suggested_questions": [
                "Why does Checkout use Kafka instead of synchronous calls?",
                "Who owns Token Service and what depends on it?",
            ],
        }

    def retrieve_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        result = self.decisions.trace_decision(decision_id)
        if result is None:
            return None

        decided_at = result["decided_at"][:10] if result["decided_at"] else "not recorded"
        answer = (
            f"**Decision: {result['title']}**\n\n{result['summary']}\n\n"
            f"**Alternatives considered:** "
            f"{result['alternatives'] or 'none recorded'}\n\n"
            f"**Status:** {result['status']} (decided {decided_at})"
        )

        return {
            "intent": "decision",
            "entity_id": decision_id,
            "answer": answer,
            "evidence_summary": (
                "Traced from the FalkorDB decision graph. "
                f"{len(result['citations'])} source(s) found."
            ),
            "citations": result["citations"],
            "graph": result["graph"],
            "suggested_questions": [
                "Who owns Checkout Service and what are its dependencies?",
                "Which incident led to this decision?",
            ],
        }

    def retrieve_impact(self, service_id: str) -> Optional[Dict[str, Any]]:
        result = self.impact.assess_impact(service_id)
        if result is None:
            return None

        answer = (
            f"**Change Impact: {result['service_name']}**\n\n"
            f"**Owner:** {result['owner_team'] or 'not recorded'}\n\n"
            f"**Downstream dependencies:** {result['downstream_count']}\n\n"
            f"**Upstream consumers:** {result['upstream_count']}\n\n"
            f"**Risk notes:** {result['risk_notes']}"
        )

        return {
            "intent": "impact",
            "entity_id": service_id,
            "answer": answer,
            "evidence_summary": (
                f"Traversed up to 2 hops from {result['service_name']}. "
                f"{len(result['citations'])} incident/decision record(s) found."
            ),
            "citations": result["citations"],
            "graph": result["graph"],
            "suggested_questions": [
                "Who should I contact before changing this service?",
                "What incidents have affected this service?",
            ],
        }

    def retrieve_ownership(self, service_id: str) -> Optional[Dict[str, Any]]:
        result = self.ownership.get_ownership(service_id)
        if result is None:
            return None

        members = (
            ", ".join(
                f"{member['name']} ({member['role']})"
                for member in result["team_members"]
            )
            or "none recorded"
        )
        contributors = (
            ", ".join(person["name"] for person in result["contributors"])
            or "none recorded"
        )

        answer = (
            f"**Ownership: {result['service_name']}**\n\n"
            f"**Owner team:** {result['owner_team'] or 'not recorded'}\n\n"
            f"**Team members:** {members}\n\n"
            f"**Contributors:** {contributors}\n\n"
            f"**Repository:** {result['repository_url'] or 'not recorded'}"
        )

        return {
            "intent": "ownership",
            "entity_id": service_id,
            "answer": answer,
            "evidence_summary": (
                f"Retrieved ownership from FalkorDB. "
                f"{len(result['team_members'])} team member(s), "
                f"{len(result['contributors'])} contributor(s)."
            ),
            "citations": result["citations"],
            "graph": result["graph"],
            "suggested_questions": [
                "What depends on this service?",
                "What incidents have affected this service?",
            ],
        }

    # --- response assembly ---------------------------------------------------

    def insufficient(self, question: str) -> AskQuestionResponse:
        return AskQuestionResponse(**self.evidence.build_insufficient_response(question))

    def build_response(self, question: str, package: Dict[str, Any]) -> AskQuestionResponse:
        """Assemble the final response, bounding the subgraph for rendering."""
        package["graph"] = self.evidence.truncate_subgraph(package["graph"])
        return AskQuestionResponse(
            answer=package["answer"],
            evidence_summary=package["evidence_summary"],
            citations=package.get("citations") or [],
            graph=package["graph"] or EvidenceSubgraph(),
            confidence=package["confidence"],
            suggested_questions=package.get("suggested_questions")
            or self.evidence.default_follow_ups(),
        )

    def confidence_for(
        self, citations: List[Any], graph: Optional[EvidenceSubgraph]
    ) -> str:
        return self.evidence.compute_confidence(citations, graph)