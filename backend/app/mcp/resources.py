"""Stable, readable MCP resources backed by the knowledge graph."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.change_forensics_service import ChangeForensicsService
from app.services.decision_service import DecisionTraceService
from app.services.onboarding_service import OnboardingContextService
from app.services.ownership_service import OwnershipService

logger = logging.getLogger(__name__)

_decisions = DecisionTraceService()
_onboarding = OnboardingContextService()
_ownership = OwnershipService()
_forensics = ChangeForensicsService()

SCHEME = "orgatlas://"


def register_resources(server) -> None:
    """Attach readable resources to an MCPServer instance."""

    @server.resource(
        f"{SCHEME}services/{{service_id}}",
        name="service_context",
        title="Service architecture context",
        description="Repository, owners, dependencies and linked decisions for a service.",
        mime_type="application/json",
    )
    def service_context(service_id: str) -> str:
        ownership = _ownership.get_ownership(service_id)
        if ownership is None:
            return _empty(f"No service '{service_id}' in the knowledge graph.")

        impact = _ownership.graph_gateway.get_change_impact(service_id)
        return _json(
            {
                "service": {
                    "id": ownership["service_id"],
                    "name": ownership["service_name"],
                },
                "owner_team": ownership["owner_team"],
                "repository": ownership.get("repository_url"),
                "team_members": ownership["team_members"],
                "contributors": ownership["contributors"],
                "sources": [c.model_dump() for c in ownership["citations"]],
                "downstream_count": len((impact or {}).get("downstream_services", [])),
            }
        )

    @server.resource(
        f"{SCHEME}teams/{{team_id}}",
        name="team_context",
        title="Team onboarding context",
        description="Owned systems, key people, learning path and reading for a team.",
        mime_type="application/json",
    )
    def team_context(team_id: str) -> str:
        result = _onboarding.get_onboarding_map(team_id)
        if result is None:
            return _empty(f"No team '{team_id}' in the knowledge graph.")
        return _json(
            {
                "team": {"id": result.team_id, "name": result.team_name},
                "mission": result.mission,
                "topics": [t.model_dump() for t in result.topics],
                "owned_services": [s.model_dump() for s in result.owned_services],
                "people": [p.model_dump() for p in result.people_to_meet],
                "reading_list": [c.model_dump() for c in result.reading_list],
            }
        )

    @server.resource(
        f"{SCHEME}decisions/{{decision_id}}",
        name="decision_context",
        title="Decision record",
        description="Rationale, alternatives, deciders and supporting sources.",
        mime_type="application/json",
    )
    def decision_context(decision_id: str) -> str:
        trace = _decisions.trace_decision(decision_id)
        if trace is None:
            return _empty(f"No decision '{decision_id}' in the knowledge graph.")
        return _json(
            {
                "decision": {
                    "id": trace["decision_id"],
                    "title": trace["title"],
                    "status": trace["status"],
                    "decided_at": trace["decided_at"],
                },
                "summary": trace["summary"],
                "alternatives": trace["alternatives"],
                "sources": [c.model_dump() for c in trace["citations"]],
                "evidence_paths": trace["graph"].paths,
            }
        )

    @server.resource(
        f"{SCHEME}repositories/{{repository_id}}",
        name="repository_context",
        title="Repository change context",
        description=(
            "High-churn areas, experienced contributors and declared cross-repository "
            "dependencies for an ingested repository."
        ),
        mime_type="application/json",
    )
    def repository_context(repository_id: str) -> str:
        brief = _forensics.investigation_brief(repository_id)
        if not brief["hotspots"] and not brief["dependency_blast_radius"]:
            return _empty(f"No ingested history for repository '{repository_id}'.")
        return _json(
            {
                "repository": repository_id,
                "hotspots": brief["hotspots"],
                "contributors": brief["contributors"],
                "dependencies": brief["dependency_blast_radius"],
                "guidance": brief["guidance"],
            }
        )


def _json(payload: Dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, default=str)


def _empty(reason: str) -> str:
    return _json({"available": False, "reason": reason})