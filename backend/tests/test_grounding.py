"""Tests for citation validation, the hallucination boundary.

Pure and offline: no provider, no graph, no network.
"""

import pytest

from app.llm.grounding import (
    GroundingResult,
    extract_citations,
    lower_confidence,
    strip_invalid_citations,
    validate_citations,
)

ALLOWED = ["doc_rfp_kafka", "doc_postmortem_2024_03", "inc_2024_03_black_friday"]


class TestExtraction:
    def test_finds_citations_in_order_without_duplicates(self):
        answer = "Kafka was chosen [doc_rfp_kafka]. The outage forced it [inc_2024_03_black_friday]."
        assert extract_citations(answer) == ["doc_rfp_kafka", "inc_2024_03_black_friday"]

    def test_ignores_markdown_links(self):
        answer = "See [the design doc](https://example.com) and [doc_rfp_kafka]."
        assert extract_citations(answer) == ["doc_rfp_kafka"]

    def test_handles_empty_answer(self):
        assert extract_citations("") == []

    def test_non_identifier_brackets_are_left_alone(self):
        assert extract_citations("a list [1] and [x]") == []


class TestStripping:
    def test_removes_only_the_invalid_tags(self):
        answer = "Real [doc_rfp_kafka] and invented [doc_made_up]."
        assert strip_invalid_citations(answer, ["doc_made_up"]) == (
            "Real [doc_rfp_kafka] and invented ."
        )

    def test_no_invalid_ids_leaves_text_untouched(self):
        answer = "Real [doc_rfp_kafka]."
        assert strip_invalid_citations(answer, []) == answer


class TestValidation:
    def test_fully_valid_answer_is_accepted_unchanged(self):
        answer = "Kafka was adopted [doc_rfp_kafka] after the outage [doc_postmortem_2024_03]."
        result = validate_citations(answer, ALLOWED)

        assert result.accepted is True
        assert result.degraded is False
        assert result.invalid_ids == []
        assert result.answer == answer
        assert result.confidence_ceiling == "supported"

    def test_mixed_answer_is_kept_but_degraded(self):
        answer = "Real [doc_rfp_kafka] plus invented [doc_invented]."
        result = validate_citations(answer, ALLOWED)

        assert result.accepted is True
        assert result.degraded is True
        assert result.valid_ids == ["doc_rfp_kafka"]
        assert result.invalid_ids == ["doc_invented"]
        assert "doc_invented" not in result.answer
        assert result.confidence_ceiling == "partial"
        assert any("doc_invented" in note for note in result.notes)

    def test_only_invented_citations_are_discarded(self):
        result = validate_citations("Nothing real [doc_a] [doc_b].", ALLOWED)

        assert result.accepted is False
        assert result.valid_ids == []
        assert sorted(result.invalid_ids) == ["doc_a", "doc_b"]
        assert result.confidence_ceiling == "insufficient"

    def test_uncited_answer_is_discarded(self):
        result = validate_citations("Kafka was a good idea.", ALLOWED)

        assert result.accepted is False
        assert result.valid_ids == []
        assert any("cited no source" in note for note in result.notes)

    def test_citation_not_offered_by_retrieval_is_invalid(self):
        """A real-looking id that retrieval never returned is still invalid."""
        result = validate_citations("Claim [doc_other_repo].", ALLOWED)

        assert result.accepted is False
        assert result.invalid_ids == ["doc_other_repo"]

    def test_empty_allowed_set_rejects_everything(self):
        result = validate_citations("Claim [doc_rfp_kafka].", [])

        assert result.accepted is False
        assert result.confidence_ceiling == "insufficient"

    def test_citation_can_be_optional(self):
        result = validate_citations("No tags here.", ALLOWED, require_citation=False)
        assert result.accepted is True
        assert result.confidence_ceiling == "supported"

    def test_empty_answer_is_not_accepted_as_a_narrative(self):
        result = validate_citations("", ALLOWED)
        assert isinstance(result, GroundingResult)
        assert result.accepted is False


class TestConfidenceCeiling:
    @pytest.mark.parametrize(
        ("current", "ceiling", "expected"),
        [
            ("supported", "supported", "supported"),
            ("supported", "partial", "partial"),
            ("supported", "insufficient", "insufficient"),
            ("partial", "supported", "partial"),
            ("insufficient", "supported", "insufficient"),
            ("partial", "partial", "partial"),
        ],
    )
    def test_confidence_is_never_raised_by_grounding(self, current, ceiling, expected):
        assert lower_confidence(current, ceiling) == expected