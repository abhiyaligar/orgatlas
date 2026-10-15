import logging
from typing import Optional

from app.graph.gateway import GraphGateway, graph_gateway
from app.api.schemas import (
    OnboardingMapResponse,
    OnboardingTopic,
    OwnedService,
    PersonSummary,
    Citation,
    EvidenceSubgraph,
    GraphNode,
    GraphEdge,
)

logger = logging.getLogger(__name__)


def _safe_str(val) -> str:
    if val is None:
        return ""
    return str(val)


def _extract_node_props(node) -> dict:
    """Safely extract properties from a FalkorDB node object."""
    if node is None:
        return {}
    if hasattr(node, "properties"):
        return node.properties or {}
    if isinstance(node, dict):
        return node
    return {}


def _node_to_graph_node(node, label: str) -> GraphNode:
    props = _extract_node_props(node)
    return GraphNode(
        id=_safe_str(props.get("id", "")),
        label=label,
        name=_safe_str(props.get("name", props.get("title", ""))),
        properties=props,
    )


class OnboardingContextService:
    """Retrieves team onboarding context: topics, services, people, and reading list."""

    def __init__(self, gateway: GraphGateway = graph_gateway):
        self.gateway = gateway

    def get_onboarding_map(self, team_id: str) -> Optional[OnboardingMapResponse]:
        data = self.gateway.get_onboarding_context(team_id)
        if not data:
            logger.warning("No onboarding data found for team: %s", team_id)
            return None

        # Build topics
        topics = []
        for raw_topic in (data.get("topics") or []):
            props = _extract_node_props(raw_topic)
            if props.get("id"):
                topics.append(OnboardingTopic(
                    id=_safe_str(props.get("id")),
                    title=_safe_str(props.get("title")),
                    sequence=int(props.get("sequence", 1)),
                    summary=_safe_str(props.get("summary")),
                    resources=[],
                ))
        topics.sort(key=lambda t: t.sequence)

        # Build owned services
        owned_services = []
        for raw_svc in (data.get("services") or []):
            props = _extract_node_props(raw_svc)
            if props.get("id"):
                owned_services.append(OwnedService(
                    id=_safe_str(props.get("id")),
                    name=_safe_str(props.get("name")),
                    description=_safe_str(props.get("description")),
                    criticality=_safe_str(props.get("criticality", "medium")),
                    maintainers=[],
                ))

        # Build people to meet
        people_to_meet = []
        seen_people = set()
        for raw_person in (data.get("people") or []):
            props = _extract_node_props(raw_person)
            person_id = props.get("id")
            if person_id and person_id not in seen_people:
                seen_people.add(person_id)
                expertise_raw = props.get("expertise", "[]")
                try:
                    import json
                    expertise = json.loads(expertise_raw) if isinstance(expertise_raw, str) else expertise_raw
                except Exception:
                    expertise = []
                people_to_meet.append(PersonSummary(
                    id=_safe_str(person_id),
                    name=_safe_str(props.get("name")),
                    role=_safe_str(props.get("role")),
                    expertise=expertise,
                ))

        # Build minimal evidence subgraph
        nodes = []
        edges = []
        if data.get("team_id"):
            nodes.append(GraphNode(
                id=data["team_id"],
                label="Team",
                name=_safe_str(data.get("team_name")),
                properties={},
            ))
        for svc in owned_services:
            nodes.append(GraphNode(id=svc.id, label="Service", name=svc.name, properties={}))
            edges.append(GraphEdge(
                id=f"team_owns_{svc.id}",
                source=data["team_id"],
                target=svc.id,
                type="OWNS",
                properties={},
            ))

        paths = [
            f"Team '{data.get('team_name')}' owns {len(owned_services)} service(s) and has {len(people_to_meet)} member(s)"
        ]

        return OnboardingMapResponse(
            team_id=_safe_str(data.get("team_id")),
            team_name=_safe_str(data.get("team_name")),
            mission=_safe_str(data.get("team_mission")),
            topics=topics,
            owned_services=owned_services,
            people_to_meet=people_to_meet,
            reading_list=[],
            graph=EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        )
