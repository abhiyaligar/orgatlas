"""Tests for the model fallback pass and its stored audit trail.

The provider and the graph are both mocked; no network and no database.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services import file_describer
from app.services.file_describer import (
    DOCS_SOURCE_MODEL,
    estimate_calls,
    gap_records,
    needs_model,
    run_fallback,
)
from app.services.llm_client import ModelDescription, ModelFailure

REAL_KEY = "sk-test-not-a-placeholder"


def _record(path, docs_source, excerpt=None, sha="a" * 40):
    return {
        "path": path,
        "language": "Rust",
        "docs_source": docs_source,
        "docs_at_sha": sha,
        "excerpt": excerpt,
    }


def _payload(records):
    return {"files": records, "repository_url": "https://github.com/FalkorDB/FalkorDB"}


@pytest.fixture(autouse=True)
def real_key():
    with patch.object(file_describer.settings, "NEBIUS_API_KEY", REAL_KEY):
        yield


@pytest.fixture
def graph():
    g = MagicMock()
    result = MagicMock()
    result.result_set = [[3]]
    g.query.return_value = result
    with patch.object(file_describer.graph_manager, "get_or_create_graph", return_value=g):
        yield g


class TestTriggerRule:
    @pytest.mark.parametrize(
        "docs_source",
        ["module", "item", "declaration", "heading", "key"],
    )
    def test_authored_descriptions_are_never_sent_to_the_model(self, docs_source):
        assert needs_model(_record("src/a.rs", docs_source, excerpt="body")) is False

    def test_gap_file_with_an_excerpt_triggers(self):
        assert needs_model(_record("src/a.rs", "none", excerpt="fn x() {}")) is True

    def test_gap_file_without_an_excerpt_does_not_trigger(self):
        assert needs_model(_record("src/a.rs", "none", excerpt=None)) is False

    @pytest.mark.parametrize("docs_source", ["skipped_large", "skipped_unreadable"])
    def test_binary_and_oversized_files_are_excluded(self, docs_source):
        assert needs_model(_record("src/a.bin", docs_source, excerpt="...")) is False

    def test_gap_records_filters_the_payload(self):
        payload = _payload(
            [
                _record("a.rs", "module", excerpt="x"),
                _record("b.rs", "none", excerpt="y"),
                _record("c.rs", "none", excerpt=None),
            ]
        )
        assert [r["path"] for r in gap_records(payload)] == ["b.rs"]


class TestCostEstimate:
    def test_reports_the_gap_size_before_spending(self):
        payload = _payload(
            [
                _record("a.rs", "module"),
                _record("b.rs", "none", excerpt="x" * 4000),
                _record("c.rs", "none", excerpt="y" * 4000),
            ]
        )
        estimate = estimate_calls(payload)

        assert estimate["total_files"] == 3
        assert estimate["already_described"] == 1
        assert estimate["gap_files"] == 2
        assert estimate["approx_calls"] == 2
        assert estimate["approx_prompt_tokens"] == 2000

    def test_dry_run_makes_no_provider_call(self, graph):
        payload = _payload([_record("b.rs", "none", excerpt="fn x() {}")])
        result = run_fallback(
            payload, "repo_x", dry_run=True, describe=lambda *a, **k: pytest.fail("called")
        )

        assert result["dry_run"] is True
        assert result["approx_calls"] == 1
        graph.query.assert_not_called()


class TestFallbackPass:
    def _success(self, summary="A module.", symbols=("A",)):
        return ModelDescription(
            summary=summary,
            symbols=list(symbols),
            model="zai-org/GLM-5.3-Flash",
            raw_response='{"summary": "A module."}',
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            input_chars=42,
        )

    def test_writes_full_provenance_for_a_described_file(self, graph):
        payload = _payload([_record("src/a.rs", "none", excerpt="fn x() {}")])
        result = run_fallback(payload, "repo_x", describe=lambda *a, **k: self._success())

        assert result["described"] == 1
        assert result["failed"] == 0
        rows = graph.query.call_args.args[1]["rows"]
        row = rows[0]

        assert row["id"] == "repo_x::src/a.rs"
        assert row["docs_source"] == DOCS_SOURCE_MODEL
        assert row["docs_model"] == "zai-org/GLM-5.3-Flash"
        assert row["docs_trigger"] == "missing_docs"
        assert row["docs_input_sha"] == "a" * 40
        assert json.loads(row["symbols"]) == ["A"]
        assert json.loads(row["docs_usage"])["total_tokens"] == 120
        assert row["docs_raw_response"] == '{"summary": "A module."}'
        assert row["docs_prompt_version"]
        assert row["docs_error"] == ""

    def test_failure_leaves_the_file_undescribed_with_a_reason(self, graph):
        payload = _payload([_record("src/a.rs", "none", excerpt="fn x() {}")])
        result = run_fallback(
            payload,
            "repo_x",
            describe=lambda *a, **k: ModelFailure("provider_error", "503"),
        )

        assert result["described"] == 0
        assert result["failed"] == 1
        row = graph.query.call_args.args[1]["rows"][0]
        assert row["docs_source"] == "none", "a failure must not mark the file described"
        assert row["summary"] == ""
        assert "provider_error" in row["docs_error"]

    def test_never_overwrites_an_authored_description(self, graph):
        payload = _payload([_record("src/a.rs", "module", excerpt="fn x() {}")])
        result = run_fallback(payload, "repo_x", describe=lambda *a, **k: self._success())

        assert result["approx_calls"] == 0
        graph.query.assert_not_called()

    def test_placeholder_key_skips_entirely(self, graph):
        payload = _payload([_record("src/a.rs", "none", excerpt="fn x() {}")])
        with patch.object(file_describer.settings, "NEBIUS_API_KEY", "your_nebius_api_key"):
            result = run_fallback(payload, "repo_x", describe=lambda *a, **k: pytest.fail("called"))

        assert result["skipped"] is True
        assert result["reason"] == "no_provider_key"
        graph.query.assert_not_called()

    def test_a_provider_outage_does_not_raise(self, graph):
        payload = _payload([_record("src/a.rs", "none", excerpt="fn x() {}")])

        def explode(*_a, **_k):
            raise RuntimeError("provider down")

        result = run_fallback(payload, "repo_x", describe=explode)

        assert result["described"] == 0
        assert result["failed"] == 1
        row = graph.query.call_args.args[1]["rows"][0]
        assert row["docs_source"] == "none"
        assert "describer_error" in row["docs_error"]

    def test_usage_totals_are_accumulated(self, graph):
        payload = _payload(
            [
                _record("a.rs", "none", excerpt="x"),
                _record("b.rs", "none", excerpt="y"),
            ]
        )
        result = run_fallback(payload, "repo_x", describe=lambda *a, **k: self._success())

        assert result["usage"]["total_tokens"] == 240
        assert result["usage"]["prompt_tokens"] == 200

    def test_batches_are_written_in_chunks(self, graph):
        from app.services.file_describer import BATCH

        payload = _payload(
            [_record(f"f{i}.rs", "none", excerpt="x") for i in range(BATCH + 5)]
        )
        run_fallback(payload, "repo_x", describe=lambda *a, **k: self._success())

        assert graph.query.call_count == 2
        sizes = [len(call.args[1]["rows"]) for call in graph.query.call_args_list]
        assert sizes == [BATCH, 5]