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


class OwnershipService:
    """Returns accountable team, maintainers, contributors and repository for a service."""

    def __init__(self, gateway: GraphGateway = graph_gateway, evidence: Optional[EvidenceService] = None):
        self.gateway = gateway
        self.evidence = evidence or EvidenceService()

    def get_ownership(self, service_id: str) -> Optional[Dict[str, Any]]:
        data = self.gateway.get_service_ownership(service_id)
        if not data:
            logger.warning("No ownership data found for service: %s", service_id)
            return None

        service_node = build_graph_node(data.get("service"), label="Service")
        if service_node is None:
            logger.warning("Ownership record is missing a stable service id: %s", service_id)
            return None

        nodes: List = [service_node]
        edges: List = []
        paths: List[str] = []

        team_node = build_graph_node(data.get("team"), label="Team")
        if team_node is not None:
            nodes.append(team_node)
            edges.append(build_graph_edge(f"owns_{service_node.id}", team_node.id, service_node.id, "OWNS"))
            paths.append(render_path(team_node.name, team_node.label, [("OWNS", service_node.name, service_node.label)]))

        member_ids = set()
        members = []
        for raw_member in data.get("team_members") or []:
            member_node = build_graph_node(raw_member, label="Person")
            if member_node is None:
                continue
            member_ids.add(member_node.id)
            properties = extract_properties(raw_member)
            members.append(
                {"id": member_node.id, "name": member_node.name, "role": safe_str(properties.get("role"))}
            )
            nodes.append(member_node)
            if team_node is not None:
                edges.append(
                    build_graph_edge(
                        f"member_{member_node.id}_{team_node.id}", member_node.id, team_node.id, "MEMBER_OF"
                    )
                )

        contributors = []
        for raw_contributor in data.get("contributors") or []:
            contributor_node = build_graph_node(raw_contributor, label="Person")
            if contributor_node is None:
                continue
            properties = extract_properties(raw_contributor)
            contributors.append(
                {"id": contributor_node.id, "name": contributor_node.name, "role": safe_str(properties.get("role"))}
            )
            if contributor_node.id not in member_ids:
                nodes.append(contributor_node)
            edges.append(
                build_graph_edge(
                    f"contrib_{contributor_node.id}_{service_node.id}",
                    contributor_node.id,
                    service_node.id,
                    "CONTRIBUTED_TO",
                )
            )

        repository_node = build_graph_node(data.get("repository"), label="Repository")
        repository_url = None
        if repository_node is not None:
            nodes.append(repository_node)
            edges.append(
                build_graph_edge(
                    f"repo_{repository_node.id}_{service_node.id}",
                    repository_node.id,
                    service_node.id,
                    "PRIMARY_IMPLEMENTATION_OF",
                )
            )
            repository_url = repository_node.properties.get("url")

        citations = self.evidence.normalize_citations(data.get("documents") or [], source_type="document")

        return {
            "service_id": service_node.id,
            "service_name": service_node.name,
            "owner_team": team_node.name if team_node else "",
            "owner_team_id": team_node.id if team_node else "",
            "team_members": members,
            "contributors": contributors,
            "repository_url": repository_url,
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }