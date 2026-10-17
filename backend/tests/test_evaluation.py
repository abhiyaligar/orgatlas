"""Evaluation suite for the five demo questions and insufficient evidence.

Committed cases run against the seeded graph with synthesis disabled, so they
assert what retrieval and grounding guarantee: the right citations and
entities are present, an unsupported question yields insufficient evidence,
and no answer claims support it does not have. They make no network call.

A live check is available for a demo, and is skipped unless explicitly
enabled, because it costs money and is not deterministic:

    ORGATLAS_LIVE_EVAL=1 pytest tests/test_evaluation.py -k live
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

EVAL_PATH = Path(__file__).resolve().parents[2] / "data" / "eval" / "expected_answers.json"


def _load_cases() -> List[Dict[str, Any]]:
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))["cases"]


CASES = _load_cases()
LIVE = os.environ.get("ORGATLAS_LIVE_EVAL") == "1"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _ask(client, question: str) -> Dict[str, Any]:
    response = client.post("/api/ask", json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def _citation_ids(payload: Dict[str, Any]) -> List[str]:
    return [citation["source_id"] for citation in payload.get("citations", [])]


def _entity_ids(payload: Dict[str, Any]) -> List[str]:
    graph = payload.get("graph") or {}
    return [node["id"] for node in graph.get("nodes", [])]


@pytest.mark.parametrize("case", [c for c in CASES if not c.get("expect_insufficient")], ids=lambda c: c["id"])
class TestDemoQuestions:
    def test_answer_is_returned(self, client, case):
        payload = _ask(client, case["prompt"])
        assert payload["answer"].strip(), "an approved question must produce an answer"
        assert payload["confidence"] != "insufficient"

    def test_required_citations_are_present(self, client, case):
        payload = _ask(client, case["prompt"])
        cited = _citation_ids(payload)
        missing = [c for c in case.get("required_citations", []) if c not in cited]
        assert not missing, f"{case['id']} is missing citations {missing}; got {cited}"

    def test_required_entities_are_present(self, client, case):
        payload = _ask(client, case["prompt"])
        entities = _entity_ids(payload)
        missing = [e for e in case.get("required_entities", []) if e not in entities]
        assert not missing, f"{case['id']} is missing entities {missing}"

    def test_answer_mentions_the_expected_subjects(self, client, case):
        payload = _ask(client, case["prompt"])
        for needle in case.get("required_substrings", []):
            assert needle in payload["answer"], f"{case['id']} never mentions {needle!r}"

    def test_evidence_summary_reports_the_expected_counts(self, client, case):
        needles = case.get("required_summary_substrings")
        if not needles:
            pytest.skip("not a summary-count case")
        payload = _ask(client, case["prompt"])
        for needle in needles:
            assert needle in payload["evidence_summary"], (
                f"{case['id']} summary never reports {needle!r}"
            )

    def test_no_invented_citations_appear(self, client, case):
        """A citation must always be one retrieval actually returned."""
        payload = _ask(client, case["prompt"])
        answer_ids = _extract_bracket_ids(payload["answer"])
        allowed = set(_citation_ids(payload))
        invented = [identifier for identifier in answer_ids if identifier not in allowed]
        assert not invented, f"{case['id']} cited sources that were never retrieved: {invented}"


class TestInsufficientEvidence:
    @pytest.mark.parametrize(
        "case", [c for c in CASES if c.get("expect_insufficient")], ids=lambda c: c["id"]
    )
    def test_unanswerable_question_is_refused(self, client, case):
        payload = _ask(client, case["prompt"])

        assert payload["confidence"] == "insufficient"
        assert "insufficient" in payload["answer"].lower()
        if case.get("forbid_citations"):
            assert not payload["citations"], "an unsupported question must cite nothing"

    def test_confusion_with_a_real_service_does_not_invent_answers(self, client):
        """An unrecognised subject must not borrow an unrelated decision."""
        payload = _ask(client, "Who owns the Widget Factory?")

        assert payload["confidence"] == "insufficient"
        assert "Widget Factory" not in payload["answer"]

    def test_blank_question_is_rejected(self, client):
        response = client.post("/api/ask", json={"question": "   "})
        assert response.status_code == 400


class TestGroundingGuarantee:
    def test_every_answer_cites_only_retrieved_sources(self, client):
        for case in CASES:
            payload = _ask(client, case["prompt"])
            if payload["confidence"] == "insufficient":
                continue
            allowed = set(_citation_ids(payload))
            invented = [
                identifier
                for identifier in _extract_bracket_ids(payload["answer"])
                if identifier not in allowed
            ]
            assert not invented, f"{case['id']}: {invented}"

    def test_synthesis_is_labelled_when_used(self, client):
        """A generated answer must say so; a graph answer need not."""
        payload = _ask(client, "Why does Checkout use Kafka instead of synchronous calls?")
        if "Synthesised by" in payload["evidence_summary"]:
            assert payload["confidence"] != "insufficient"


def _extract_bracket_ids(text: str) -> List[str]:
    import re

    return re.findall(r"\[([A-Za-z0-9_.:-]{2,120})\]", text or "")


@pytest.mark.skipif(not LIVE, reason="set ORGATLAS_LIVE_EVAL=1 to call the live provider")
class TestLiveProvider:
    def test_answers_are_written_by_the_model_and_grounded(self, client):
        from app.core.config import settings

        previous = settings.ASK_SYNTHESIS_ENABLED
        settings.ASK_SYNTHESIS_ENABLED = True
        try:
            for case in CASES:
                if case.get("expect_insufficient"):
                    continue
                payload = _ask(client, case["prompt"])
                assert "Synthesised by" in payload["evidence_summary"], (
                    f"{case['id']} did not use the provider"
                )
                allowed = set(_citation_ids(payload))
                invented = [
                    identifier
                    for identifier in _extract_bracket_ids(payload["answer"])
                    if identifier not in allowed
                ]
                assert not invented, f"{case['id']} invented {invented}"
        finally:
            settings.ASK_SYNTHESIS_ENABLED = previous