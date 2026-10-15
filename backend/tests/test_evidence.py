from app.api.schemas import Citation, EvidenceSubgraph, GraphEdge, GraphNode
from app.evidence.formatter import (
    build_graph_edge,
    build_graph_node,
    build_graph_nodes,
    display_name,
    extract_labels,
    extract_properties,
    render_path,
    safe_str,
)
from app.evidence.service import MAX_EDGES, MAX_NODES, EvidenceService


class FakeNode:
    """Minimal stand-in for a FalkorDB node record."""

    def __init__(self, properties, labels):
        self.properties = properties
        self.labels = labels


def _document(doc_id="doc_rfp_kafka", title="RFC-042"):
    return FakeNode({"id": doc_id, "title": title, "type": "design_doc", "excerpt": "excerpt text"}, ["Document"])


def _graph(node_count, edge_count):
    nodes = [GraphNode(id=f"n{i}", label="Service", name=f"Service {i}") for i in range(node_count)]
    edges = [GraphEdge(id=f"e{i}", source=f"n{i}", target=f"n{i + 1}", type="DEPENDS_ON") for i in range(edge_count)]
    return EvidenceSubgraph(nodes=nodes, edges=edges)


def test_safe_str_never_returns_none():
    assert safe_str(None) == ""
    assert safe_str(0) == "0"
    assert safe_str("text") == "text"


def test_extract_properties_handles_nodes_dicts_and_none():
    assert extract_properties(None) == {}
    assert extract_properties({"id": "svc_checkout"}) == {"id": "svc_checkout"}
    assert extract_properties(FakeNode({"id": "svc_checkout"}, ["Service"])) == {"id": "svc_checkout"}
    assert extract_properties("not-a-node") == {}


def test_extract_labels_supports_both_record_shapes():
    assert extract_labels(FakeNode({}, ["Service", "Owned"])) == ["Service", "Owned"]
    assert extract_labels({"label": "Decision"}) == ["Decision"]
    assert extract_labels(None) == []


def test_display_name_falls_back_from_name_to_title_to_id():
    assert display_name(FakeNode({"name": "Checkout"}, ["Service"])) == "Checkout"
    assert display_name(FakeNode({"title": "RFC-042"}, ["Document"])) == "RFC-042"
    assert display_name(FakeNode({"id": "svc_checkout"}, ["Service"])) == "svc_checkout"
    assert display_name(FakeNode({}, [])) == ""


def test_build_graph_node_requires_a_stable_id():
    assert build_graph_node(FakeNode({"title": "no id"}, ["Document"])) is None
    assert build_graph_node(None) is None


def test_build_graph_node_uses_explicit_label_over_record_labels():
    node = build_graph_node(FakeNode({"id": "dec_1", "title": "Adopt Kafka"}, ["Decision"]), label="Decision")
    assert node.id == "dec_1"
    assert node.label == "Decision"
    assert node.name == "Adopt Kafka"


def test_build_graph_nodes_drops_unidentifiable_records():
    nodes = build_graph_nodes([_document(), FakeNode({}, ["Document"]), None], label="Document")
    assert len(nodes) == 1


def test_build_graph_edge_normalises_values():
    edge = build_graph_edge("e1", "a", "b", "DEPENDS_ON")
    assert (edge.id, edge.source, edge.target, edge.type) == ("e1", "a", "b", "DEPENDS_ON")
    assert edge.properties == {}


def test_render_path_matches_documented_format():
    rendered = render_path("Checkout", "Service", [("USES", "Apache Kafka", "Technology")])
    assert rendered == "Checkout [Service] ──USES──> Apache Kafka [Technology]"


def test_render_path_chains_multiple_hops():
    rendered = render_path("Checkout", "Service", [("USES", "Kafka", "Technology"), ("LED_TO", "Outage", "Incident")])
    assert rendered.count("──") == 4
    assert rendered.startswith("Checkout [Service]")
    assert rendered.endswith("Outage [Incident]")


def test_render_path_without_hops_is_a_single_node():
    assert render_path("Checkout", "Service", []) == "Checkout [Service]"


def test_normalize_citation_reads_alternative_excerpt_field():
    citation = EvidenceService().normalize_citation(FakeNode({"id": "inc_1", "title": "Outage", "summary": "s"}, ["Incident"]), source_type="incident")
    assert citation.source_id == "inc_1"
    assert citation.type == "incident"
    assert citation.excerpt == "s"


def test_normalize_citation_returns_none_without_stable_id():
    assert EvidenceService().normalize_citation(FakeNode({"title": "orphan"}, ["Document"])) is None


def test_normalize_citations_deduplicates_by_source_id():
    citations = EvidenceService().normalize_citations([_document(), _document(), None], source_type="document")
    assert len(citations) == 1
    assert citations[0].source_id == "doc_rfp_kafka"


def test_compute_confidence_is_insufficient_without_any_evidence():
    assert EvidenceService().compute_confidence([], EvidenceSubgraph()) == "insufficient"
    assert EvidenceService().compute_confidence(None, None) == "insufficient"


def test_compute_confidence_is_supported_with_two_or_more_citations():
    citations = [Citation(source_id="a", title="A", type="document"), Citation(source_id="b", title="B", type="document")]
    assert EvidenceService().compute_confidence(citations, _graph(2, 1)) == "supported"


def test_compute_confidence_is_partial_with_graph_evidence_but_no_citations():
    assert EvidenceService().compute_confidence([], _graph(3, 2)) == "partial"


def test_compute_confidence_is_partial_with_a_single_citation():
    citations = [Citation(source_id="a", title="A", type="document")]
    assert EvidenceService().compute_confidence(citations, _graph(2, 1)) == "partial"


def test_truncate_subgraph_caps_nodes_and_edges():
    truncated = EvidenceService().truncate_subgraph(_graph(MAX_NODES + 20, MAX_EDGES + 20))
    assert len(truncated.nodes) == MAX_NODES
    assert len(truncated.edges) <= MAX_EDGES


def test_truncate_subgraph_drops_edges_pointing_at_removed_nodes():
    graph = EvidenceSubgraph(
        nodes=[GraphNode(id="kept", label="Service", name="Kept")],
        edges=[GraphEdge(id="e1", source="kept", target="removed", type="DEPENDS_ON")],
    )
    truncated = EvidenceService().truncate_subgraph(graph)
    assert truncated.edges == []


def test_insufficient_response_never_claims_support():
    response = EvidenceService().build_insufficient_response("Why do we use Cobol?")
    assert response["confidence"] == "insufficient"
    assert response["citations"] == []
    assert response["graph"].nodes == []
    assert response["suggested_questions"]


def test_fallback_answer_reports_partial_confidence_when_graph_has_evidence():
    response = EvidenceService().build_fallback_answer(
        {"citations": [], "graph": _graph(2, 1)}, "Who owns Token Service?"
    )
    assert response["confidence"] == "partial"
    assert "fallback mode" in response["evidence_summary"]