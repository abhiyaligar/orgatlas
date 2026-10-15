import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import EvidenceSubgraph
from app.evidence.formatter import (
    build_graph_edge,
    build_graph_node,
    extract_properties,
    render_path,
    safe_str,
)
from app.evidence.service import EvidenceService
from app.graph.gateway import GraphGateway, graph_gateway

logger = logging.getLogger(__name__)


class ChangeImpactService:
    """Assesses the bounded change impact of a target service (2-hop max)."""

    def __init__(self, gateway: GraphGateway = graph_gateway, evidence: Optional[EvidenceService] = None):
        self.gateway = gateway
        self.evidence = evidence or EvidenceService()

    def assess_impact(self, service_id: str) -> Optional[Dict[str, Any]]:
        data = self.gateway.get_change_impact(service_id)
        if not data:
            logger.warning("No change impact data found for service: %s", service_id)
            return None

        target_node = build_graph_node(data.get("target_service"), label="Service")
        if target_node is None:
            logger.warning("Change impact record is missing a stable service id: %s", service_id)
            return None

        nodes: List = [target_node]
        edges: List = []
        paths: List[str] = []

        owner_node = build_graph_node(data.get("owner_team"), label="Team")
        owner_name = ""
        if owner_node is not None:
            owner_name = owner_node.name
            nodes.append(owner_node)
            edges.append(build_graph_edge(f"owns_{target_node.id}", owner_node.id, target_node.id, "OWNS"))

        downstream = []
        for service in data.get("downstream_services") or []:
            dependency_node = build_graph_node(service, label="Service")
            if dependency_node is None or dependency_node.id == target_node.id:
                continue
            downstream.append(dependency_node.name)
            nodes.append(dependency_node)
            edges.append(
                build_graph_edge(f"dep_{target_node.id}_{dependency_node.id}", target_node.id, dependency_node.id, "DEPENDS_ON")
            )
        if downstream:
            paths.append(
                render_path(
                    target_node.name,
                    target_node.label,
                    [("DEPENDS_ON", downstream[0], "Service")] if len(downstream) == 1
                    else [("DEPENDS_ON", f"{downstream[0]} and {len(downstream) - 1} more", "Services")],
                )
            )

        upstream = []
        for service in data.get("upstream_services") or []:
            consumer_node = build_graph_node(service, label="Service")
            if consumer_node is None or consumer_node.id == target_node.id:
                continue
            upstream.append(consumer_node.name)
            nodes.append(consumer_node)
            edges.append(
                build_graph_edge(f"upstream_{consumer_node.id}_{target_node.id}", consumer_node.id, target_node.id, "DEPENDS_ON")
            )
        if upstream:
            paths.append(render_path(upstream[0], "Service", [("DEPENDS_ON", target_node.name, target_node.label)]))

        citations = self.evidence.normalize_citations(data.get("incidents") or [], source_type="incident")

        for incident in data.get("incidents") or []:
            incident_node = build_graph_node(incident, label="Incident")
            if incident_node is None:
                continue
            nodes.append(incident_node)
            edges.append(build_graph_edge(f"inc_affects_{incident_node.id}", incident_node.id, target_node.id, "AFFECTS"))

        decision_citations = self.evidence.normalize_citations(data.get("decisions") or [], source_type="decision")
        citations.extend(decision_citations)

        risk_notes = (
            f"Changing '{target_node.name}' may affect: {', '.join(upstream)} (upstream consumers)."
            if upstream
            else f"No upstream consumers detected for '{target_node.name}'."
        )

        return {
            "service_id": target_node.id,
            "service_name": target_node.name,
            "owner_team": owner_name,
            "downstream_count": len(downstream),
            "upstream_count": len(upstream),
            "risk_notes": risk_notes,
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }