import json
import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import (
    OnboardingMapResponse,
    OnboardingTopic,
    OwnedService,
    PersonSummary,
    EvidenceSubgraph,
)
from app.evidence.formatter import build_graph_edge, build_graph_node, render_path, safe_str
from app.evidence.service import EvidenceService
from app.graph.gateway import GraphGateway, graph_gateway

logger = logging.getLogger(__name__)


def parse_stored_list(value: Any) -> List[str]:
    """Read a list-valued property that FalkorDB stored as a JSON encoded string."""
    if isinstance(value, list):
        return [safe_str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            logger.debug("Unable to parse stored list payload; treating as empty")
            return []
        return [safe_str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


class OnboardingContextService:
    """Retrieves team onboarding context: topics, services, people, and reading list."""

    def __init__(self, gateway: GraphGateway = graph_gateway, evidence: Optional[EvidenceService] = None):
        self.gateway = gateway
        self.evidence = evidence or EvidenceService()

    def get_onboarding_map(self, team_id: str) -> Optional[OnboardingMapResponse]:
        data = self.gateway.get_onboarding_context(team_id)
        if not data:
            logger.warning("No onboarding data found for team: %s", team_id)
            return None

        resolved_team_id = safe_str(data.get("team_id"))
        team_name = safe_str(data.get("team_name"))

        topics = []
        resource_ids: List[str] = []
        for raw_topic in data.get("topics") or []:
            topic_node = build_graph_node(raw_topic, label="OnboardingTopic")
            if topic_node is None:
                continue
            properties = topic_node.properties
            resources = parse_stored_list(properties.get("resources"))
            for resource_id in resources:
                if resource_id not in resource_ids:
                    resource_ids.append(resource_id)
            topics.append(
                OnboardingTopic(
                    id=topic_node.id,
                    title=safe_str(properties.get("title")),
                    sequence=int(properties.get("sequence") or 0),
                    summary=safe_str(properties.get("summary")),
                    resources=resources,
                )
            )
        topics.sort(key=lambda topic: topic.sequence)

        owned_services = []
        for raw_service in data.get("services") or []:
            service_node = build_graph_node(raw_service, label="Service")
            if service_node is None:
                continue
            properties = service_node.properties
            owned_services.append(
                OwnedService(
                    id=service_node.id,
                    name=service_node.name,
                    description=safe_str(properties.get("description")),
                    criticality=safe_str(properties.get("criticality") or "medium"),
                    repository_url=properties.get("url"),
                    maintainers=[safe_str(item) for item in properties.get("maintainers") or []],
                )
            )

        people_to_meet = []
        seen_people = set()
        for raw_person in data.get("people") or []:
            person_node = build_graph_node(raw_person, label="Person")
            if person_node is None or person_node.id in seen_people:
                continue
            seen_people.add(person_node.id)
            properties = person_node.properties
            people_to_meet.append(
                PersonSummary(
                    id=person_node.id,
                    name=person_node.name,
                    role=safe_str(properties.get("role")),
                    expertise=parse_stored_list(properties.get("expertise")),
                )
            )

        nodes: List = []
        edges: List = []
        paths: List[str] = []
        if resolved_team_id:
            nodes.append(
                build_graph_node({"id": resolved_team_id, "name": team_name}, label="Team")
            )
        for service in owned_services:
            nodes.append(build_graph_node({"id": service.id, "name": service.name}, label="Service"))
            edges.append(
                build_graph_edge(
                    f"team_owns_{service.id}", resolved_team_id, service.id, "OWNS"
                )
            )
        if owned_services:
            paths.append(
                render_path(
                    team_name,
                    "Team",
                    [("OWNS", ", ".join(service.name for service in owned_services), "Services")],
                )
            )

        reading_list = self.evidence.normalize_citations(
            self.gateway.get_documents_by_ids(resource_ids), source_type="document"
        )

        return OnboardingMapResponse(
            team_id=resolved_team_id,
            team_name=team_name,
            mission=safe_str(data.get("team_mission")),
            topics=topics,
            owned_services=owned_services,
            people_to_meet=people_to_meet,
            reading_list=reading_list,
            graph=EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        )