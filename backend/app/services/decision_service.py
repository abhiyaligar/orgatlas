import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import EvidenceSubgraph
from app.evidence.formatter import (
    build_graph_edge,
    build_graph_node,
    display_name,
    extract_properties,
    render_path,
    safe_str,
)
from app.evidence.service import EvidenceService
from app.graph.gateway import GraphGateway, graph_gateway

logger = logging.getLogger(__name__)


class DecisionTraceService:
    """Traverses a decision node with evidence, deciders, incidents, and sources."""

    def __init__(self, gateway: GraphGateway = graph_gateway, evidence: Optional[EvidenceService] = None):
        self.gateway = gateway
        self.evidence = evidence or EvidenceService()

    def trace_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        data = self.gateway.get_decision_trace(decision_id)
        if not data:
            logger.warning("No decision node found for id: %s", decision_id)
            return None

        decision_properties = extract_properties(data.get("decision"))
        decision_node = build_graph_node(data.get("decision"), label="Decision")
        if decision_node is None:
            logger.warning("Decision record is missing a stable id: %s", decision_id)
            return None

        nodes: List = [decision_node]
        edges: List = []
        paths: List[str] = []

        for document in data.get("documents") or []:
            document_node = build_graph_node(document, label="Document")
            if document_node is None:
                continue
            nodes.append(document_node)
            edges.append(
                build_graph_edge(f"dec_supported_{document_node.id}", decision_node.id, document_node.id, "SUPPORTED_BY")
            )

        for incident in data.get("incidents") or []:
            incident_node = build_graph_node(incident, label="Incident")
            if incident_node is None:
                continue
            nodes.append(incident_node)
            edges.append(build_graph_edge(f"inc_led_{incident_node.id}", incident_node.id, decision_node.id, "LED_TO"))
            paths.append(render_path(incident_node.name, incident_node.label, [("LED_TO", decision_node.name, decision_node.label)]))

        for person in data.get("people") or []:
            person_node = build_graph_node(person, label="Person")
            if person_node is None:
                continue
            nodes.append(person_node)
            edges.append(build_graph_edge(f"dec_by_{person_node.id}", decision_node.id, person_node.id, "DECIDED_BY"))

        for service in data.get("services") or []:
            service_node = build_graph_node(service, label="Service")
            if service_node is None:
                continue
            nodes.append(service_node)
            edges.append(build_graph_edge(f"dec_affects_{service_node.id}", decision_node.id, service_node.id, "AFFECTS"))
            paths.append(render_path(decision_node.name, decision_node.label, [("AFFECTS", service_node.name, service_node.label)]))

        citations = self.evidence.normalize_citations(data.get("documents") or [], source_type="document")
        citations.extend(self.evidence.normalize_citations(data.get("incidents") or [], source_type="incident"))
        citations.extend(self.evidence.normalize_citations(data.get("pull_requests") or [], source_type="pull_request"))
        citations.extend(self.evidence.normalize_citations(data.get("tickets") or [], source_type="ticket"))

        return {
            "decision_id": decision_node.id,
            "title": safe_str(decision_properties.get("title")),
            "summary": safe_str(decision_properties.get("summary")),
            "alternatives": safe_str(decision_properties.get("alternatives")),
            "status": safe_str(decision_properties.get("status")),
            "decided_at": safe_str(decision_properties.get("decided_at")),
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }