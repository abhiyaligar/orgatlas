import logging
from typing import Optional, Dict, Any, List

from app.graph.gateway import GraphGateway, graph_gateway
from app.api.schemas import (
    AskQuestionResponse,
    Citation,
    EvidenceSubgraph,
    GraphNode,
    GraphEdge,
)

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


class DecisionTraceService:
    """Traverses a decision node with evidence, deciders, incidents, and sources."""

    def __init__(self, gateway: GraphGateway = graph_gateway):
        self.gateway = gateway

    def trace_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        data = self.gateway.get_decision_trace(decision_id)
        if not data:
            return None

        dec_props = _extract_node_props(data.get("decision"))
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        citations: List[Citation] = []
        paths: List[str] = []

        # Decision node
        dec_node = GraphNode(
            id=_safe_str(dec_props.get("id")),
            label="Decision",
            name=_safe_str(dec_props.get("title")),
            properties=dec_props,
        )
        nodes.append(dec_node)

        # Documents → Citations
        for doc in (data.get("documents") or []):
            props = _extract_node_props(doc)
            doc_id = _safe_str(props.get("id"))
            if doc_id:
                nodes.append(GraphNode(id=doc_id, label="Document", name=_safe_str(props.get("title")), properties=props))
                edges.append(GraphEdge(id=f"dec_supported_{doc_id}", source=dec_node.id, target=doc_id, type="SUPPORTED_BY", properties={}))
                citations.append(Citation(
                    source_id=doc_id,
                    title=_safe_str(props.get("title")),
                    type=_safe_str(props.get("type", "document")),
                    url=props.get("url"),
                    excerpt=props.get("excerpt"),
                ))

        # Incidents
        for inc in (data.get("incidents") or []):
            props = _extract_node_props(inc)
            inc_id = _safe_str(props.get("id"))
            if inc_id:
                nodes.append(GraphNode(id=inc_id, label="Incident", name=_safe_str(props.get("title")), properties=props))
                edges.append(GraphEdge(id=f"inc_led_{inc_id}", source=inc_id, target=dec_node.id, type="LED_TO", properties={}))
                paths.append(f"Incident '{props.get('title')}' → LED_TO → Decision '{dec_props.get('title')}'")
                citations.append(Citation(
                    source_id=inc_id,
                    title=_safe_str(props.get("title")),
                    type="incident",
                    excerpt=props.get("summary"),
                ))

        # People who decided
        for person in (data.get("people") or []):
            props = _extract_node_props(person)
            person_id = _safe_str(props.get("id"))
            if person_id:
                nodes.append(GraphNode(id=person_id, label="Person", name=_safe_str(props.get("name")), properties=props))
                edges.append(GraphEdge(id=f"dec_by_{person_id}", source=dec_node.id, target=person_id, type="DECIDED_BY", properties={}))

        # Affected services
        for svc in (data.get("services") or []):
            props = _extract_node_props(svc)
            svc_id = _safe_str(props.get("id"))
            if svc_id:
                nodes.append(GraphNode(id=svc_id, label="Service", name=_safe_str(props.get("name")), properties=props))
                edges.append(GraphEdge(id=f"dec_affects_{svc_id}", source=dec_node.id, target=svc_id, type="AFFECTS", properties={}))
                paths.append(f"Decision '{dec_props.get('title')}' → AFFECTS → Service '{props.get('name')}'")

        return {
            "decision_id": _safe_str(dec_props.get("id")),
            "title": _safe_str(dec_props.get("title")),
            "summary": _safe_str(dec_props.get("summary")),
            "alternatives": _safe_str(dec_props.get("alternatives")),
            "status": _safe_str(dec_props.get("status")),
            "decided_at": _safe_str(dec_props.get("decided_at")),
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }
