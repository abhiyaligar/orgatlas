"""Trace why a specific change exists.

Walks a commit to its pull request reference, its attributed author, any
architecture decision it implements, and the source documents that support
those decisions — then states plainly which links are missing rather than
guessing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import Citation, EvidenceSubgraph, GraphEdge, GraphNode
from app.evidence.formatter import build_graph_edge, build_graph_node, render_path
from app.evidence.service import EvidenceService
from app.graph.gateway import GraphGateway, graph_gateway

logger = logging.getLogger(__name__)

GET_COMMIT_DECISIONS = """
MATCH (c:Commit {id: $commit_id})-[:IMPLEMENTS]->(d:Decision)
RETURN d.id AS id, d.title AS title, d.summary AS summary
LIMIT $limit
"""

GET_DECISION_SOURCES = """
MATCH (d:Decision {id: $decision_id})-[:SUPPORTED_BY]->(src)
RETURN src.id AS id,
       coalesce(src.title, src.name, '') AS title,
       labels(src)[0] AS label,
       coalesce(src.url, '') AS url
LIMIT $limit
"""


class CommitProvenanceService:
    """Explain a change from the evidence available in the graph."""

    def __init__(
        self,
        gateway: GraphGateway = graph_gateway,
        evidence: Optional[EvidenceService] = None,
    ) -> None:
        self.gateway = gateway
        self.evidence = evidence or EvidenceService()

    def _decisions(
        self, commit_id: str, limit: int = 10, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self.gateway._execute(
            GET_COMMIT_DECISIONS,
            {"commit_id": commit_id, "limit": limit},
            graph_name=graph_name,
        )
        return [
            {"id": row[0], "title": row[1], "summary": row[2] or ""} for row in rows
        ]

    def _decision_sources(self, decision_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.gateway._execute(
            GET_DECISION_SOURCES, {"decision_id": decision_id, "limit": limit}
        )
        return [
            {"id": row[0], "title": row[1], "label": row[2], "url": row[3] or None}
            for row in rows
            if row[0]
        ]

    def trace(self, commit_id: str, graph_name: str = "") -> Optional[Dict[str, Any]]:
        """Trace one commit to its author, pull request, decisions and sources.

        ``graph_name`` names the repository graph holding the commit. A commit
        id alone does not say which repository it came from, so the route either
        resolves it first or searches the repository graphs for it.
        """
        commit = self.gateway.get_commit_detail(commit_id, graph_name=graph_name)
        if not commit:
            logger.info("Commit %s not found in the knowledge graph", commit_id)
            return None

        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        paths: List[str] = []
        citations: List[Citation] = []
        gaps: List[str] = []

        commit_node = build_graph_node(
            {
                "id": commit["sha"],
                "name": commit["message"][:70],
                "authored_at": commit["authored_at"],
                "pr_number": commit["pr_number"],
            },
            label="Commit",
        )
        if commit_node is not None:
            nodes.append(commit_node)

        if commit.get("author_id"):
            author_node = build_graph_node(
                {"id": commit["author_id"], "name": commit.get("author") or commit["author_id"]},
                label="ExternalIdentity",
            )
            if author_node is not None:
                nodes.append(author_node)
                edges.append(
                    build_graph_edge(
                        f"authored_{author_node.id}_{commit['sha']}",
                        author_node.id,
                        commit["sha"],
                        "AUTHORED",
                    )
                )
                paths.append(
                    render_path(
                        author_node.name,
                        author_node.label,
                        [("AUTHORED", commit_node.name if commit_node else commit["sha"], "Commit")],
                    )
                )

        citations.append(
            Citation(
                source_id=commit["sha"],
                title=commit["message"][:90],
                type="commit",
                author=commit.get("author") or None,
                created_at=commit.get("authored_at") or None,
                url=(
                    f"https://github.com/{commit['repository_id']}/commit/{commit['sha']}"
                    if commit.get("repository_id")
                    else None
                ),
            )
        )

        decisions = self._decisions(commit["sha"], graph_name=graph_name)
        for decision in decisions:
            decision_node = build_graph_node(
                {"id": decision["id"], "name": decision["title"]}, label="Decision"
            )
            if decision_node is None:
                continue
            nodes.append(decision_node)
            edges.append(
                build_graph_edge(
                    f"implements_{commit['sha']}_{decision_node.id}",
                    commit["sha"],
                    decision_node.id,
                    "IMPLEMENTS",
                )
            )
            if commit_node is not None:
                paths.append(
                    render_path(
                        commit_node.name,
                        commit_node.label,
                        [("IMPLEMENTS", decision_node.name, decision_node.label)],
                    )
                )

            for source in self._decision_sources(decision["id"]):
                source_node = build_graph_node(
                    {"id": source["id"], "name": source["title"]}, label=source["label"]
                )
                if source_node is None:
                    continue
                nodes.append(source_node)
                edges.append(
                    build_graph_edge(
                        f"supported_{decision_node.id}_{source_node.id}",
                        decision_node.id,
                        source_node.id,
                        "SUPPORTED_BY",
                    )
                )
                citations.append(
                    Citation(
                        source_id=source["id"],
                        title=source["title"],
                        type=source["label"].lower(),
                        url=source.get("url"),
                    )
                )

        if not decisions:
            gaps.append(
                "No architecture decision is linked to this commit. The graph can say who "
                "changed what and when, but not why. Ingested history is not retro-fitted "
                "to the seeded decisions."
            )
        if not commit.get("pr_number"):
            gaps.append(
                "No pull-request reference was recovered from the commit subject. Squash "
                "and merge styles differ; some commits legitimately have none."
            )
        if not commit.get("author_id"):
            gaps.append(
                "This commit has no attributed author identity. It was most likely produced "
                "by automation or an unresolved email."
            )

        return {
            "commit": commit,
            "decisions": decisions,
            "citations": citations,
            "gaps": gaps,
            "confidence": self.evidence.compute_confidence(
                citations, EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths)
            ),
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }