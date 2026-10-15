import logging
from typing import Optional, Dict, Any, List

from app.graph.gateway import GraphGateway, graph_gateway
from app.api.schemas import EvidenceSubgraph, GraphNode, GraphEdge, Citation

logger = logging.getLogger(__name__)


def _safe_str(val) -> str:
    return "" if val is None else str(val)


def _extract_node_props(node) -> dict:
    if node is None:
        return {}
    if hasattr(node, "properties"):
        return node.properties or {}
    if isinstance(node, dict):
        return node
    return {}


class OwnershipService:
    """Returns accountable team, maintainers, contributors and repository for a service."""

    def __init__(self, gateway: GraphGateway = graph_gateway):
        self.gateway = gateway

    def get_ownership(self, service_id: str) -> Optional[Dict[str, Any]]:
        data = self.gateway.get_service_ownership(service_id)
        if not data:
            return None

        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        paths: List[str] = []

        svc_props = _extract_node_props(data.get("service"))
        svc_id = _safe_str(svc_props.get("id"))
        svc_name = _safe_str(svc_props.get("name"))
        nodes.append(GraphNode(id=svc_id, label="Service", name=svc_name, properties=svc_props))

        team_props = _extract_node_props(data.get("team"))
        team_id = _safe_str(team_props.get("id"))
        team_name = _safe_str(team_props.get("name"))
        if team_id:
            nodes.append(GraphNode(id=team_id, label="Team", name=team_name, properties=team_props))
            edges.append(GraphEdge(id=f"owns_{svc_id}", source=team_id, target=svc_id, type="OWNS", properties={}))
            paths.append(f"Team '{team_name}' → OWNS → Service '{svc_name}'")

        members = []
        for raw in (data.get("team_members") or []):
            props = _extract_node_props(raw)
            person_id = _safe_str(props.get("id"))
            if person_id:
                members.append({"id": person_id, "name": props.get("name"), "role": props.get("role")})
                nodes.append(GraphNode(id=person_id, label="Person", name=_safe_str(props.get("name")), properties=props))
                edges.append(GraphEdge(id=f"member_{person_id}_{team_id}", source=person_id, target=team_id, type="MEMBER_OF", properties={}))

        contributors = []
        for raw in (data.get("contributors") or []):
            props = _extract_node_props(raw)
            person_id = _safe_str(props.get("id"))
            if person_id:
                contributors.append({"id": person_id, "name": props.get("name"), "role": props.get("role")})
                if person_id not in {m["id"] for m in members}:
                    nodes.append(GraphNode(id=person_id, label="Person", name=_safe_str(props.get("name")), properties=props))
                edges.append(GraphEdge(id=f"contrib_{person_id}_{svc_id}", source=person_id, target=svc_id, type="CONTRIBUTED_TO", properties={}))

        repo_props = _extract_node_props(data.get("repository"))
        repo_id = _safe_str(repo_props.get("id"))
        if repo_id:
            nodes.append(GraphNode(id=repo_id, label="Repository", name=_safe_str(repo_props.get("name")), properties=repo_props))
            edges.append(GraphEdge(id=f"repo_{repo_id}_{svc_id}", source=repo_id, target=svc_id, type="PRIMARY_IMPLEMENTATION_OF", properties={}))

        return {
            "service_id": svc_id,
            "service_name": svc_name,
            "owner_team": team_name,
            "owner_team_id": team_id,
            "team_members": members,
            "contributors": contributors,
            "repository_url": repo_props.get("url"),
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }
