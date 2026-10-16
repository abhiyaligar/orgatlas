"""Tests for the model-provider fallback client.

The provider is always mocked; this suite makes no network call.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services import llm_client
from app.services.llm_client import (
    ModelDescription,
    ModelFailure,
    build_excerpt,
    build_prompt,
    describe_file,
    parse_response,
)

RUST_SOURCE = """//! Graph traversal over a property graph.
pub struct Graph;
pub fn query(&self) {}
"""

REAL_KEY = "sk-test-not-a-placeholder"


def _completion(content, usage=None):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


@pytest.fixture(autouse=True)
def real_key():
    with patch.object(llm_client.settings, "NEBIUS_API_KEY", REAL_KEY), patch.object(
        llm_client.settings, "NEBIUS_MODEL_NAME", "zai-org/GLM-5.3-Flash"
    ):
        yield


def _patched_chat(completion):
    return patch.object(llm_client, "_chat", return_value=completion)


class TestGate:
    def test_no_key_short_circuits_without_calling_provider(self):
        with patch.object(llm_client.settings, "NEBIUS_API_KEY", None):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert isinstance(result, ModelFailure)
        assert result.reason == "no_provider_key"

    def test_placeholder_key_short_circuits(self):
        with patch.object(llm_client.settings, "NEBIUS_API_KEY", "your_nebius_api_key"):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert isinstance(result, ModelFailure)
        assert result.reason == "no_provider_key"

    def test_empty_excerpt_short_circuits(self):
        with _patched_chat(_completion('{"summary": "x"}')) as chat:
            result = describe_file("   ", "src/empty.rs")
        assert isinstance(result, ModelFailure)
        assert result.reason == "empty_excerpt"
        chat.assert_not_called()


class TestSuccess:
    def test_returns_summary_symbols_model_and_raw_response(self):
        raw = '{"summary": "Graph traversal over a property graph.", "symbols": ["Graph", "query"]}'
        usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
        with _patched_chat(_completion(raw, usage)):
            result = describe_file(RUST_SOURCE, "src/graph.rs", "Rust")

        assert isinstance(result, ModelDescription)
        assert result.summary.startswith("Graph traversal")
        assert result.symbols == ["Graph", "query"]
        assert result.model == "zai-org/GLM-5.3-Flash"
        assert result.raw_response == raw
        assert result.usage["total_tokens"] == 150
        assert result.prompt_version == llm_client.PROMPT_VERSION

    def test_usage_is_captured_from_object_style_responses(self):
        usage = MagicMock()
        usage.model_dump.return_value = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        with _patched_chat(_completion('{"summary": "ok", "symbols": []}', usage)):
            result = describe_file(RUST_SOURCE, "src/graph.rs")

        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    def test_usage_absent_is_not_an_error(self):
        with _patched_chat(_completion('{"summary": "ok", "symbols": []}', None)):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert result.usage == {}

    def test_symbols_are_cleaned_deduplicated_and_capped(self):
        raw = (
            '{"summary": "ok", "symbols": [" a  b ", "a b", "", 5, null, '
            + ", ".join(f'"s{i}"' for i in range(40))
            + "]}"
        )
        with _patched_chat(_completion(raw)):
            result = describe_file(RUST_SOURCE, "src/graph.rs")

        assert result.symbols[0] == "a b"
        assert len(result.symbols) == llm_client.MAX_SYMBOLS

    def test_summary_is_length_bounded(self):
        raw = '{"summary": "' + ("word " * 400) + '", "symbols": []}'
        with _patched_chat(_completion(raw)):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert len(result.summary) <= llm_client.MAX_SUMMARY_CHARS


class TestDegradation:
    def test_provider_error_becomes_a_typed_failure(self):
        with patch.object(
            llm_client, "_chat", side_effect=llm_client.ModelCallError("502 upstream")
        ):
            result = describe_file(RUST_SOURCE, "src/graph.rs")

        assert isinstance(result, ModelFailure)
        assert result.reason == "provider_error"
        assert "502" in result.detail

    def test_no_choices_is_a_failure(self):
        completion = MagicMock()
        completion.choices = []
        with _patched_chat(completion):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert result.reason == "empty_response"

    def test_unparsable_reply_is_a_failure_not_an_exception(self):
        with _patched_chat(_completion("I'm sorry, I cannot help with that.")):
            result = describe_file(RUST_SOURCE, "src/graph.rs")

        assert isinstance(result, ModelFailure)
        assert result.reason == "unparsable_response"

    def test_blank_summary_is_rejected(self):
        with _patched_chat(_completion('{"summary": "   ", "symbols": ["a"]}')):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert result.reason == "empty_summary"

    def test_failure_never_raises(self):
        with patch.object(llm_client, "_chat", side_effect=RuntimeError("boom")):
            result = describe_file(RUST_SOURCE, "src/graph.rs")
        assert isinstance(result, ModelFailure)


class TestParsing:
    @pytest.mark.parametrize(
        "content",
        [
            '{"summary": "a", "symbols": []}',
            '```json\n{"summary": "a", "symbols": []}\n```',
            'Here you go:\n{"summary": "a", "symbols": []}\nHope that helps.',
            '  {"summary": "a", "symbols": []}  ',
        ],
    )
    def test_accepts_fenced_and_surrounded_json(self, content):
        parsed = parse_response(content)
        assert parsed is not None
        assert parsed["summary"] == "a"

    @pytest.mark.parametrize("content", ["", None, "not json", "[1, 2, 3]", "{}"])
    def test_rejects_unusable_content(self, content):
        assert parse_response(content) is None


class TestPromptAndBounds:
    def test_excerpt_is_truncated_with_a_marker(self):
        excerpt = build_excerpt("x" * (llm_client.MAX_EXCERPT_CHARS + 500))
        assert len(excerpt) < llm_client.MAX_EXCERPT_CHARS + 100
        assert "truncated for length" in excerpt

    def test_prompt_carries_path_language_and_bounds(self):
        prompt = build_prompt("BODY", "src/graph.rs", "Rust")
        assert "src/graph.rs" in prompt
        assert "Rust" in prompt
        assert "BODY" in prompt
        assert '"summary"' in prompt
        assert str(llm_client.MAX_SYMBOLS) in prompt

    def test_retry_wrapper_surfaces_a_typed_error(self):
        calls = []

        def boom(*_args, **_kwargs):
            calls.append(1)
            raise RuntimeError("down")

        with patch.dict("sys.modules"):
            with patch("openai.OpenAI", side_effect=boom):
                with pytest.raises(llm_client.ModelCallError):
                    llm_client._chat([{"role": "user", "content": "x"}], 5, 0)
        assert calls