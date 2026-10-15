"""Evidence shaping: citation normalisation, confidence scoring and bounded subgraphs."""

import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import Citation, EvidenceSubgraph
from app.evidence.formatter import extract_properties, safe_str

logger = logging.getLogger(__name__)

MAX_NODES = 50
MAX_EDGES = 75

SUPPORTED = "supported"
PARTIAL = "partial"
INSUFFICIENT = "insufficient"

SOURCE_TYPE_FALLBACK = "document"


class EvidenceService:
    """Normalises citations, bounds subgraphs, and scores confidence."""

    def normalize_citation(self, source: Any, source_type: str = SOURCE_TYPE_FALLBACK) -> Optional[Citation]:
        """Build a Citation from a raw graph node, or None when it has no stable id."""
        properties = extract_properties(source)
        source_id = safe_str(properties.get("id"))
        if not source_id:
            return None

        return Citation(
            source_id=source_id,
            title=safe_str(properties.get("title") or properties.get("name") or source_id),
            type=safe_str(properties.get("type")) or source_type,
            url=properties.get("url"),
            excerpt=properties.get("excerpt") or properties.get("summary"),
            author=properties.get("author"),
            created_at=properties.get("created_at"),
        )

    def normalize_citations(self, sources: List[Any], source_type: str = SOURCE_TYPE_FALLBACK) -> List[Citation]:
        """Build a deduplicated citation list preserving retrieval order."""
        citations: List[Citation] = []
        seen: set = set()
        for source in sources or []:
            citation = self.normalize_citation(source, source_type=source_type)
            if citation is not None and citation.source_id not in seen:
                seen.add(citation.source_id)
                citations.append(citation)
        return citations

    def compute_confidence(
        self,
        citations: Optional[List[Citation]] = None,
        graph: Optional[EvidenceSubgraph] = None,
    ) -> str:
        """Score how well the retrieved evidence supports an answer.

        A response backed only by graph relationships but no source documents
        is reported as partial rather than supported, because no claim can be
        traced back to a document the reader can inspect.
        """
        citation_count = len(citations or [])
        has_graph = bool(graph and graph.nodes)

        if citation_count == 0 and not has_graph:
            return INSUFFICIENT
        if citation_count >= 2:
            return SUPPORTED
        return PARTIAL

    def truncate_subgraph(self, graph: EvidenceSubgraph) -> EvidenceSubgraph:
        """Bound the subgraph so the browser graph view stays responsive."""
        nodes = graph.nodes[:MAX_NODES]
        node_ids = {node.id for node in nodes}
        edges = [edge for edge in graph.edges if edge.source in node_ids and edge.target in node_ids][:MAX_EDGES]
        return EvidenceSubgraph(nodes=nodes, edges=edges, paths=graph.paths)

    def build_insufficient_response(self, query: str) -> Dict[str, Any]:
        """Return a safe structured response instead of guessing at an answer."""
        return {
            "answer": (
                "Insufficient evidence was found in the knowledge graph to answer this question confidently. "
                "The graph may not contain entities or relationships relevant to your query."
            ),
            "evidence_summary": "No supporting graph paths were found.",
            "citations": [],
            "graph": EvidenceSubgraph(nodes=[], edges=[], paths=[]),
            "confidence": INSUFFICIENT,
            "suggested_questions": self.default_follow_ups(),
        }

    def default_follow_ups(self) -> List[str]:
        """Return the stable demo prompts as safe follow-up suggestions."""
        return [
            "Why does Checkout use Kafka instead of synchronous calls?",
            "Who owns Token Service and which services depend on it?",
            "What should a new Payments engineer learn in their first week?",
        ]

    def build_fallback_answer(self, graph_data: Dict[str, Any], question: str) -> Dict[str, Any]:
        """Build a deterministic text answer from graph facts when the LLM is unavailable."""
        citations = graph_data.get("citations", [])
        lines = [f"**Graph Evidence for:** {question}", ""]

        if citations:
            for index, citation in enumerate(citations[:5], 1):
                lines.append(f"[{index}] **{citation.title}** ({citation.type})")
                if citation.excerpt:
                    lines.append(f"   > {citation.excerpt[:200]}...")
        else:
            lines.append("No source documents were retrieved for this query.")

        return {
            "answer": "\n".join(lines),
            "evidence_summary": (
                f"Retrieved {len(citations)} source(s) directly from FalkorDB graph traversal. "
                "(Synthesised in fallback mode — LLM unavailable.)"
            ),
            "citations": citations,
            "graph": graph_data.get("graph", EvidenceSubgraph()),
            "confidence": self.compute_confidence(citations, graph_data.get("graph")),
            "suggested_questions": self.default_follow_ups(),
        }