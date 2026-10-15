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


class ChangeImpactService:
    """Assesses the bounded change impact of a target service (2-hop max)."""

    def __init__(self, gateway: GraphGateway = graph_gateway):
        self.gateway = gateway

    def assess_impact(self, service_id: str) -> Optional[Dict[str, Any]]:
        data = self.gateway.get_change_impact(service_id)
        if not data:
            return None

        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        citations: List[Citation] = []
        paths: List[str] = []

        # Target service
        target_props = _extract_node_props(data.get("target_service"))
        target_id = _safe_str(target_props.get("id"))
        target_name = _safe_str(target_props.get("name"))
        nodes.append(GraphNode(id=target_id, label="Service", name=target_name, properties=target_props))

        # Owner team
        owner_props = _extract_node_props(data.get("owner_team"))
        owner_id = _safe_str(owner_props.get("id"))
        owner_name = _safe_str(owner_props.get("name"))
        if owner_id:
            nodes.append(GraphNode(id=owner_id, label="Team", name=owner_name, properties=owner_props))
            edges.append(GraphEdge(id=f"owns_{target_id}", source=owner_id, target=target_id, type="OWNS", properties={}))

        # Downstream dependencies
        downstream = []
        for raw in (data.get("downstream_services") or []):
            props = _extract_node_props(raw)
            svc_id = _safe_str(props.get("id"))
            if svc_id and svc_id != target_id:
                downstream.append(props.get("name", svc_id))
                nodes.append(GraphNode(id=svc_id, label="Service", name=_safe_str(props.get("name")), properties=props))
                edges.append(GraphEdge(id=f"dep_{target_id}_{svc_id}", source=target_id, target=svc_id, type="DEPENDS_ON", properties={}))
        if downstream:
            paths.append(f"Service '{target_name}' depends on: {', '.join(downstream)}")

        # Upstream services (things that depend on us)
        upstream = []
        for raw in (data.get("upstream_services") or []):
            props = _extract_node_props(raw)
            svc_id = _safe_str(props.get("id"))
            if svc_id and svc_id != target_id:
                upstream.append(props.get("name", svc_id))
                nodes.append(GraphNode(id=svc_id, label="Service", name=_safe_str(props.get("name")), properties=props))
                edges.append(GraphEdge(id=f"upstream_{svc_id}_{target_id}", source=svc_id, target=target_id, type="DEPENDS_ON", properties={}))
        if upstream:
            paths.append(f"Service '{target_name}' is depended upon by: {', '.join(upstream)}")

        # Related incidents
        for raw in (data.get("incidents") or []):
            props = _extract_node_props(raw)
            inc_id = _safe_str(props.get("id"))
            if inc_id:
                nodes.append(GraphNode(id=inc_id, label="Incident", name=_safe_str(props.get("title")), properties=props))
                edges.append(GraphEdge(id=f"inc_affects_{inc_id}", source=inc_id, target=target_id, type="AFFECTS", properties={}))
                citations.append(Citation(
                    source_id=inc_id,
                    title=_safe_str(props.get("title")),
                    type="incident",
                    excerpt=props.get("summary"),
                ))

        return {
            "service_id": target_id,
            "service_name": target_name,
            "owner_team": owner_name,
            "downstream_count": len(downstream),
            "upstream_count": len(upstream),
            "risk_notes": f"Changing '{target_name}' may affect: {', '.join(upstream)} (upstream consumers)." if upstream else "No upstream consumers detected.",
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }
