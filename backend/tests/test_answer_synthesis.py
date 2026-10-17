"""Tests for answer synthesis and its degradation paths.

The provider is always a stub, so these run offline with no inference cost.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.schemas import Citation, EvidenceSubgraph
from app.llm.client import SynthesisFailure, SynthesisSuccess
from app.services.ask_service import AskService


def _run(coro):
    """Drive one coroutine to completion.

    The suite deliberately avoids an async pytest plugin, so async paths are
    executed explicitly here.
    """
    return asyncio.run(coro)


QUESTION = "Why does Checkout use Kafka instead of synchronous calls?"

CITATIONS = [
    Citation(
        source_id="doc_rfp_kafka",
        title="RFC-042: Asynchronous Event-Driven Checkout",
        type="design_doc",
        excerpt="Adopt an event-driven pipeline.",
    ),
    Citation(
        source_id="inc_2024_03_black_friday",
        title="SEV-1 Checkout Outage",
        type="incident",
        excerpt="Synchronous settlement failed under load.",
    ),
]


def _package():
    return {
        "intent": "decision",
        "entity_id": "dec_kafka_async",
        "answer": "**Decision: Asynchronous checkout**",
        "evidence_summary": "Retrieved from the graph.",
        "citations": CITATIONS,
        "graph": EvidenceSubgraph(paths=["Checkout -> Kafka -> incident"]),
        "suggested_questions": ["next?"],
    }


def _service(provider):
    return AskService(provider=provider)


def _stub(result, available=True):
    provider = MagicMock()
    provider.available = available
    provider.generate_synthesis = AsyncMock(return_value=result)
    return provider


class TestSynthesisSucceeds:
    def test_grounded_answer_replaces_the_deterministic_one(self):
        provider = _stub(
            SynthesisSuccess(
                answer="Checkout uses Kafka [doc_rfp_kafka] after the outage "
                "[inc_2024_03_black_friday].",
                model="zai-org/GLM-5.3-Flash",
                usage={"total_tokens": 500},
            )
        )
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))

        assert package["answer"].startswith("Checkout uses Kafka")
        assert package["synthesis"]["model"] == "zai-org/GLM-5.3-Flash"
        assert "Synthesised by" in package["evidence_summary"]
        assert "fallback_reason" not in package

    def test_confidence_is_capped_only_when_grounding_requires_it(self):
        provider = _stub(
            SynthesisSuccess(
                answer="Real [doc_rfp_kafka].", model="m", usage={}
            )
        )
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))
        package["confidence"] = "supported"
        response = service.build_response(QUESTION, package)

        assert response.confidence == "supported"

    def test_mixed_citations_are_stripped_and_downgraded(self):
        provider = _stub(
            SynthesisSuccess(
                answer="Kafka [doc_rfp_kafka] and invented [doc_made_up].",
                model="m",
                usage={},
            )
        )
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))
        package["confidence"] = "supported"
        response = service.build_response(QUESTION, package)

        assert "doc_made_up" not in response.answer
        assert response.confidence == "partial"
        assert "doc_made_up" in response.evidence_summary


class TestDegradation:
    def test_provider_failure_falls_back_to_graph_facts(self):
        provider = _stub(SynthesisFailure(reason="provider_error", detail="503"))
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))

        assert package["answer"] == "**Decision: Asynchronous checkout**"
        assert "Answered from graph facts" in package["evidence_summary"]
        assert "provider_error" in package["fallback_reason"]

    def test_uncited_answer_is_discarded(self):
        provider = _stub(
            SynthesisSuccess(answer="Kafka was a good idea for scale.", model="m", usage={})
        )
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))

        assert package["answer"] == "**Decision: Asynchronous checkout**"
        assert "discarded" in package["fallback_reason"]

    def test_fully_invented_citations_are_discarded(self):
        provider = _stub(
            SynthesisSuccess(
                answer="Claim [doc_other] and [inc_other].", model="m", usage={}
            )
        )
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))

        assert package["answer"] == "**Decision: Asynchronous checkout**"

    def test_missing_provider_key_falls_back(self):
        provider = _stub(None, available=False)
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))

        assert package["answer"] == "**Decision: Asynchronous checkout**"
        assert "no provider is configured" in package["fallback_reason"]
        provider.generate_synthesis.assert_not_called()

    def test_fallback_without_a_narrative_uses_the_evidence_listing(self):
        provider = _stub(SynthesisFailure(reason="provider_error"))
        service = _service(provider)
        package = _run(service.synthesize(QUESTION, _package()))
        response = service.build_response(QUESTION, package)

        assert len(response.citations) == 2
        assert response.graph.paths == ["Checkout -> Kafka -> incident"]


class TestFactsPassedToTheProvider:
    def test_provider_receives_the_graph_facts_and_sources(self):
        provider = _stub(SynthesisSuccess(answer="x [doc_rfp_kafka]", model="m", usage={}))
        service = _service(provider)
        _run(service.synthesize(QUESTION, _package()))

        request = provider.generate_synthesis.call_args.args[0]
        assert request.question == QUESTION
        assert "Checkout -> Kafka -> incident" in request.facts
        assert [c["source_id"] for c in request.citations] == [
            "doc_rfp_kafka",
            "inc_2024_03_black_friday",
        ]
        assert request.intent == "decision"
        assert request.entity_id == "dec_kafka_async"