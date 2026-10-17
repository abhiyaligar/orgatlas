"""Document ingestion, Slack ingestion, and decision evidence.

Everything here runs against fakes. The extraction guard is the part worth
protecting hardest: it is the one place where a model's output becomes graph
structure, and an unverified claim written into the graph is read back later as
fact.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.api.schemas import Citation, DecisionEvidenceResponse, MetricResponse
from app.ingestion.doc_parsers import (
    DocumentParseError,
    for_extraction,
    kind_for_filename,
    parse_csv,
    parse_document,
)
from app.ingestion.document_ingest import DocumentIngestor, _migration_pairs, person_id_for
from app.services.decision_evidence_service import DecisionEvidenceService
from app.services.doc_extractor import (
    DocumentExtractor,
    ExtractionOutcome,
    ExtractionResult,
    quote_is_supported,
    validate,
)

MIGRATION_DOC = """# Migration Record: Checkout from Kafka to Redis Streams

We migrated Checkout from Kafka to Redis Streams in June 2024. The reason was
consumer lag during peak season. Kafka Streams was rejected because the consumer
group could not be replayed safely.

Sarah Chen proposed the migration and Dvir Dukhan approved it.

Checkout p99 latency fell from 840ms to 120ms after the migration.
"""


# --- parsers ----------------------------------------------------------------


def test_a_markdown_title_comes_from_the_heading():
    doc = parse_document(b"# ADR-014: Caching\n\nBody text.\n", "adr.md", "d1")[0]
    assert doc.kind == "markdown"
    assert doc.title == "ADR-014: Caching"


def test_a_csv_becomes_one_document_per_row():
    rows = parse_document(
        b"date,title,owner\n2024-03-02,Move to Kafka,Sarah Chen\n2024-06-11,Add replica,Dvir Dukhan\n",
        "decisions.csv",
        "d2",
    )
    assert len(rows) == 2
    assert rows[0].title == "Move to Kafka"
    assert rows[0].metadata["fields"]["owner"] == "Sarah Chen"


def test_an_empty_csv_is_an_error_not_an_empty_document():
    with pytest.raises(DocumentParseError):
        parse_csv(b"", "d3", "t")


def test_an_unsupported_extension_is_refused_by_name():
    with pytest.raises(DocumentParseError) as excinfo:
        kind_for_filename("design.docx")
    assert "supported" in str(excinfo.value)


def test_a_pdf_with_no_text_layer_is_refused_rather_than_returned_empty():
    """A scan has nothing to link; reporting it as an empty document would read
    later as 'the authors wrote nothing'."""
    # A minimal but structurally valid PDF with no text operators.
    blank = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>"
    with pytest.raises(DocumentParseError):
        parse_document(blank, "scan.pdf", "d4")


def test_dehyphenation_survives_a_line_wrap():
    """A PDF that wraps a word must still resolve to the whole word."""
    from app.ingestion.doc_parsers import _clean

    assert "asynchronous" in _clean("asynchro-\nnous calls")


def test_extraction_text_is_bounded_but_the_document_is_not():
    long_text = "para\n\n" * 5000
    assert len(for_extraction(long_text)) <= 24000


# --- extraction verification ------------------------------------------------


def test_a_quote_that_is_not_verbatim_is_not_support():
    assert not quote_is_supported("We migrated it quickly.", MIGRATION_DOC)


def test_whitespace_folding_still_matches_across_a_wrap():
    assert quote_is_supported(
        "Sarah Chen proposed the migration and Dvir Dukhan approved it.",
        "Sarah Chen proposed\nthe migration and Dvir Dukhan approved it.",
    )


def test_an_invented_person_is_dropped():
    parsed = {
        "people": [
            {"name": "Sarah Chen", "involvement": "proposed", "quote": "Sarah Chen proposed the migration and Dvir Dukhan approved it."},
            {"name": "Mallory Invented", "involvement": "proposed", "quote": "Mallory wrote the spec."},
        ]
    }
    result = validate(parsed, MIGRATION_DOC)
    assert [p["name"] for p in result.people] == ["Sarah Chen"]


def test_a_metric_without_a_verifiable_quote_is_dropped():
    parsed = {
        "metrics": [
            {"name": "Guessed gain", "value": 42, "unit": "percent",
             "quote": "we improved a lot"}
        ]
    }
    assert validate(parsed, MIGRATION_DOC).metrics == []


def test_a_metric_the_document_states_is_kept_with_its_baseline():
    parsed = {
        "metrics": [
            {"name": "Checkout p99 latency", "value": 120, "unit": "ms",
             "baseline": "840ms", "direction": "improvement",
             "quote": "Checkout p99 latency fell from 840ms to 120ms after the migration."}
        ]
    }
    metric = validate(parsed, MIGRATION_DOC).metrics[0]
    assert metric["value"] == 120.0
    assert metric["baseline"] == "840ms"


def test_a_quote_that_is_not_in_the_document_is_dropped():
    parsed = {"quotes": [{"speaker": "Sarah Chen", "text": "words nobody wrote"}]}
    assert validate(parsed, MIGRATION_DOC).quotes == []


def test_a_fenced_json_response_is_recovered():
    from app.services.doc_extractor import _parse_json

    parsed = _parse_json('```json\n{"decisions": []}\n```')
    assert parsed == {"decisions": []}


def test_an_empty_document_reports_an_error_instead_of_calling_a_model():
    outcome = DocumentExtractor().extract("t", "   ")
    assert not outcome.ok
    assert "no text" in outcome.error


# --- migration detection ----------------------------------------------------


def test_a_stated_migration_yields_both_ends():
    pairs = _migration_pairs(MIGRATION_DOC, ["Kafka", "Redis Streams"])
    assert pairs == [("Kafka", "Redis Streams")]


def test_two_technologies_merely_mentioned_are_not_a_migration():
    text = "Kafka powers billing. Redis Streams is used elsewhere. No move was made."
    assert _migration_pairs(text, ["Kafka", "Redis Streams"]) == []


def test_an_unknown_technology_is_never_guessed_from_prose():
    """A trailing clause must not become a system name."""
    pairs = _migration_pairs(
        "We migrated Checkout from Kafka to Redis Streams in June 2024.",
        ["Kafka", "Redis Streams"],
    )
    assert all(source in ("Kafka",) for source, _ in pairs)
    assert all(target in ("Redis Streams",) for _, target in pairs)


# --- ingest pipeline --------------------------------------------------------


class FakeExtractor:
    def __init__(self, result=None):
        self.result = result or ExtractionResult(
            decisions=[{"title": "Migrate Checkout from Kafka to Redis Streams",
                        "summary": "Moved off Kafka.", "rationale": "Consumer lag.",
                        "alternatives": "Kafka Streams", "status": "accepted",
                        "decided_at": "2024-06",
                        "quote": "We migrated Checkout from Kafka to Redis Streams in June 2024."}],
            people=[{"name": "Sarah Chen", "role": "proposer", "involvement": "proposed",
                     "quote": "Sarah Chen proposed the migration and Dvir Dukhan approved it."}],
            quotes=[],
            metrics=[{"name": "Checkout p99 latency", "value": 120.0, "unit": "ms",
                      "baseline": "840ms", "direction": "improvement",
                      "quote": "Checkout p99 latency fell from 840ms to 120ms after the migration."}],
            entities=[{"name": "Kafka", "kind": "Technology"},
                      {"name": "Redis Streams", "kind": "Technology"}],
        )

    def extract(self, title, text, kind="text"):
        return ExtractionOutcome(result=self.result, model="fake", usage={"total_tokens": 10})


def make_ingestor(extractor=None, entities=None):
    gateway = MagicMock()
    gateway.search_entities_by_terms.return_value = entities if entities is not None else [
        {"term": "Kafka", "id": "tech_kafka", "label": "Technology", "name": "Apache Kafka", "quality": 1}
    ]
    gateway.upsert_extracted_decisions.return_value = ["dec_extracted_1"]
    gateway.record_migration.return_value = 1
    gateway.record_migration_to.return_value = 1
    gateway.link_document.return_value = 1
    return DocumentIngestor(
        gateway=gateway, extractor=extractor or FakeExtractor(), session_factory=MagicMock()
    ), gateway


def test_ingest_reports_every_stage():
    ingestor, _ = make_ingestor()
    stages = []
    ingestor.ingest(MIGRATION_DOC.encode(), "migration.md", on_stage=stages.append)
    joined = " | ".join(stages)
    for expected in ("parsing", "extracting", "storing", "writing", "complete"):
        assert expected in joined, f"{expected} missing from {joined}"


def test_ingest_writes_the_decision_and_its_people():
    ingestor, gateway = make_ingestor()
    ingestor.ingest(MIGRATION_DOC.encode(), "migration.md")
    gateway.upsert_extracted_decisions.assert_called_once()
    gateway.upsert_decision_people.assert_called_once()
    people = gateway.upsert_decision_people.call_args[0][1]
    assert people[0]["person_id"] == person_id_for("Sarah Chen")


def test_ingest_records_both_ends_of_a_migration():
    ingestor, gateway = make_ingestor()
    ingestor.ingest(MIGRATION_DOC.encode(), "migration.md")
    assert gateway.record_migration.call_args[0][1][0]["name"] == "Kafka"
    assert gateway.record_migration_to.call_args[0][1][0]["name"] == "Redis Streams"


def test_a_term_resolving_to_nothing_is_not_linked():
    ingestor, gateway = make_ingestor(entities=[])
    ingestor.ingest(MIGRATION_DOC.encode(), "migration.md")
    gateway.link_document.assert_not_called()


def test_extraction_can_be_switched_off_and_the_document_still_lands():
    ingestor, gateway = make_ingestor()
    ingestor.ingest(MIGRATION_DOC.encode(), "migration.md", run_extraction=False)
    gateway.upsert_extracted_decisions.assert_not_called()
    gateway.upsert_document.assert_called()


def test_slack_messages_are_stored_as_excerpts_not_transcripts():
    ingestor, gateway = make_ingestor()
    long_message = "x" * 4000
    summary = ingestor.ingest_slack_messages(
        [{"channel_id": "C1", "text": long_message, "author": "Sarah Chen", "ts": "1.1"}]
    )
    assert summary["messages"] == 1
    excerpt = gateway.upsert_slack_message.call_args[0][0]["excerpt"]
    assert len(excerpt) <= 500


def test_an_empty_slack_message_is_skipped():
    ingestor, _ = make_ingestor()
    assert ingestor.ingest_slack_messages([{"channel_id": "C1", "text": "  "}])["skipped"] == 1


def test_an_unknown_slack_speaker_is_not_invented_as_a_person():
    ingestor, gateway = make_ingestor(entities=[])
    ingestor.ingest_slack_messages(
        [{"channel_id": "C1", "text": "hello", "author": "Nobody Known", "ts": "1.1"}]
    )
    gateway.link_slack_author.assert_not_called()


# --- decision evidence ------------------------------------------------------


def _evidence(**overrides):
    base = dict(
        decision_id="dec_1",
        title="Migrate Checkout to Redis Streams",
        summary="Moved off Kafka.",
        rationale="Consumer lag at peak.",
        status="Accepted",
        decided_at="2024-06-01T00:00:00Z",
        documents=[Citation(source_id="doc_1", title="Migration Record", type="document")],
        people=[],
        metrics=[],
        notes=[],
    )
    base.update(overrides)
    return DecisionEvidenceResponse(**base)


def test_a_complete_decision_reports_no_gaps():
    from app.api.schemas import PersonInvolvement

    evidence = _evidence(
        people=[PersonInvolvement(person_id="p1", name="Sarah Chen", involvement="PROPOSED")],
        metrics=[MetricResponse(id="m1", name="p99", value=120, unit="ms")],
    )
    notes = DecisionEvidenceService._notes(
        documents=[{"id": "d"}],
        people=[{"person_id": "p1"}],
        discussion=[{"source_id": "s1"}],
        metrics=[{"id": "m1"}],
        commits=[{"sha": "a" * 40}],
        migration={"from": ["Kafka"], "to": ["Redis Streams"]},
    )
    assert notes == []


def test_an_unevidenced_improvement_claim_is_refused_outright():
    """The graph holds no metric, so the answer must not imply one exists."""
    notes = DecisionEvidenceService._notes(
        documents=[{"id": "d"}],
        people=[{"person_id": "p1"}],
        discussion=[{"source_id": "s1"}],
        metrics=[],
        commits=[{"sha": "a" * 40}],
        migration={"from": ["Kafka"], "to": ["Redis Streams"]},
    )
    assert any("No improvement figure is recorded" in note for note in notes)


def test_a_decision_with_no_reason_says_so_rather_than_inventing_one():
    rendered = DecisionEvidenceService().render(_evidence(rationale=""))
    assert "not recorded" in rendered


def test_the_narrative_includes_every_section_that_has_data():
    from app.api.schemas import PersonInvolvement, QuotedStatement

    rendered = DecisionEvidenceService().render(
        _evidence(
            people=[PersonInvolvement(person_id="p1", name="Sarah Chen",
                                     involvement="PROPOSED", quote="I propose we move.")],
            quotes=[QuotedStatement(source_id="s1", speaker="Dvir Dukhan",
                                    text="Approved.", channel="payments")],
            metrics=[MetricResponse(id="m1", name="Checkout p99 latency",
                                    value=120, unit="ms", baseline="840ms")],
        )
    )
    for heading in ("People involved", "In discussion", "Stated outcomes", "Sources"):
        assert heading in rendered, f"{heading} missing"


def test_a_metric_renders_with_its_unit_and_baseline():
    rendered = DecisionEvidenceService().render(
        _evidence(metrics=[MetricResponse(id="m1", name="Checkout p99 latency",
                                          value=120, unit="ms", baseline="840ms",
                                          direction="improvement")])
    )
    assert "120ms" in rendered
    assert "from 840ms" in rendered


def test_the_document_node_exists_before_anything_links_to_it():
    """Ordering bug guard.

    Every graph writer MATCHes on the Document node, so writing it last drops
    each row silently: the MERGE still creates the decision, the MATCH finds no
    document, no SUPPORTED_BY edge is written, and no id comes back -- which
    also silently loses every person and every migration.
    """
    ingestor, gateway = make_ingestor()
    order = []
    for name in ("upsert_document", "upsert_extracted_decisions",
                 "upsert_decision_people", "upsert_metrics"):
        original = getattr(gateway, name)

        def record(*args, _n=name, _o=original, **kwargs):
            order.append(_n)
            return _o(*args, **kwargs)

        setattr(gateway, name, record)

    ingestor.ingest(MIGRATION_DOC.encode(), "migration.md")

    assert order.index("upsert_document") < order.index("upsert_extracted_decisions")
    assert order.index("upsert_extracted_decisions") < order.index("upsert_decision_people")


def test_counts_report_what_reached_the_graph_not_what_the_model_proposed():
    """A run that writes nothing must not report one decision extracted."""
    gateway_calls = {"decisions": 0, "metrics": 0, "people": 0}

    ingestor, gateway = make_ingestor()
    gateway.upsert_extracted_decisions.return_value = []          # nothing accepted
    gateway.upsert_metrics.return_value = []
    gateway.upsert_decision_people.return_value = 0

    summary = ingestor.ingest(MIGRATION_DOC.encode(), "migration.md")

    assert summary["decisions"] == 0, "a decision the graph rejected is not counted"
    assert summary["metrics"] == 0
    assert summary["people"] == 0
