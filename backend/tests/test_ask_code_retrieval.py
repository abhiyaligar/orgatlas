"""Ask retrieval for questions about the ingested repository.

Covers the graph-driven routing in ``AskService.retrieve`` and the three code
retrievers it can now reach. A fake gateway stands in for FalkorDB so the
assertions are about routing and assembly, not about live data.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.services.ask_service import AskService
from app.services.question_resolution import ResolvedEntity


def make_service(hits=None, symbol=None, symbol_file=None, description=None, history=None):
    gateway = MagicMock()
    # The decision-evidence read is a separate concern; these tests are about
    # routing and assembly, so it reports no evidence and the path under test
    # is the one that was asked for.
    gateway.get_decision_evidence.return_value = None
    # Coverage ranking is the primary path for a decision question. These tests
    # are about routing and about the incident-to-decision hop, so coverage
    # reports nothing and the hop is what gets exercised.
    gateway.rank_decisions_by_coverage.return_value = []
    gateway.search_entities_by_terms.return_value = hits or []
    gateway.get_code_symbol.return_value = symbol if symbol is not None else []
    gateway.get_symbol_file.return_value = symbol_file
    gateway.get_file_description.return_value = description
    gateway.get_file_history.return_value = history if history is not None else []
    gateway.find_related_decisions.return_value = []
    return AskService(gateway=gateway), gateway


def declaration(name="open_payload"):
    return {
        "id": "s1",
        "name": name,
        "kind": "function",
        "signature": f"fn {name}()",
        "doc_comment": "Docs.",
        "documented": True,
        "line": 10,
        "visibility": "pub",
        "container": "",
        "language": "Rust",
        "repository_id": "repo_x",
    }


def hit(label, name, term, quality=0):
    return {"term": term, "id": f"{label}:{name}", "label": label, "name": name, "quality": quality}


# --- routing ----------------------------------------------------------------


def test_a_symbol_question_retrieves_a_declaration():
    service, gateway = make_service(
        hits=[hit("CodeSymbol", "open_payload", "open", quality=1)],
        symbol=[declaration()],
    )
    package = service.retrieve("What does the open function do?", None)

    assert package is not None
    assert package["intent"] == "symbol"
    gateway.get_code_symbol.assert_called_once()
    assert gateway.get_code_symbol.call_args.kwargs == {
        "file_id": "",
        "limit": 6,
    } or gateway.get_code_symbol.call_args[0][0] == "open"


def test_a_file_question_retrieves_its_description():
    service, gateway = make_service(
        hits=[hit("File", "graph.rs", "graph.rs")],
        description={
            "path": "graph/src/graph/graph.rs",
            "name": "graph.rs",
            "language": "Rust",
            "is_test": False,
            "summary": "Core graph data structure.",
            "symbols": ["Graph", "add_edge"],
            "docs_source": "module",
            "repository_id": "repo_falkordb",
            "docs_model": "",
            "docs_trigger": "",
        },
    )
    package = service.retrieve("Describe the graph.rs module", None)

    assert package is not None
    assert package["intent"] == "file"
    assert "Core graph data structure." in package["answer"]
    assert package["graph"] is not None


def test_a_history_question_retrieves_commits():
    service, gateway = make_service(
        hits=[hit("File", "graph.rs", "graph.rs")],
        history=[
            {"sha": "a" * 40, "message": "fix: edge type", "authored_at": "2024-01-01", "author": "Avi"},
            {"sha": "b" * 40, "message": "perf: writes", "authored_at": "2024-02-01", "author": "Dvir"},
        ],
    )
    package = service.retrieve("What has changed recently in graph.rs?", None)

    assert package is not None
    assert package["intent"] == "commit_history"
    assert "fix: edge type" in package["answer"]


def test_history_on_a_symbol_resolves_through_its_file():
    service, gateway = make_service(
        hits=[hit("CodeSymbol", "Graph", "Graph")],
        symbol_file={"file_id": "f1", "path": "graph.rs"},
        history=[{"sha": "c" * 40, "message": "chore: bump", "authored_at": "2024-03-01", "author": "Avi"}],
    )
    package = service.retrieve("How often has the Graph struct changed recently?", None)

    assert package is not None
    assert package["intent"] == "commit_history"
    gateway.get_symbol_file.assert_called_once_with("CodeSymbol:Graph", graph_name="")


def test_an_unresolvable_question_retrieves_nothing():
    service, gateway = make_service(hits=[])
    assert service.retrieve("How many teams does the organization have?", None) is None


def test_a_decision_question_follows_the_incident_to_the_decision():
    service, gateway = make_service(hits=[hit("Incident", "Checkout Cascade", "Checkout", quality=1)])
    gateway.find_related_decisions.return_value = [{"id": "dec_kafka_async", "title": "Kafka", "via": "LED_TO"}]

    traced = MagicMock(
        return_value={
            "title": "Adopt Kafka",
            "summary": "Decoupled payments.",
            "alternatives": "synchronous REST",
            "status": "accepted",
            "decided_at": "2024-04-02T00:00:00Z",
            "citations": [],
            "graph": None,
        }
    )
    service.decisions.trace_decision = traced

    package = service.retrieve("Why does Checkout use Kafka instead of synchronous calls?", None)

    gateway.find_related_decisions.assert_called_once_with("Incident:Checkout Cascade")
    traced.assert_called_once_with("dec_kafka_async")


# --- declaration answer assembly -------------------------------------------


def test_an_undocumented_symbol_says_so():
    service, _ = make_service(
        hits=[hit("CodeSymbol", "helper", "helper")],
        symbol=[
            {
                "id": "s1",
                "name": "helper",
                "kind": "function",
                "signature": "fn helper()",
                "doc_comment": "",
                "documented": False,
                "line": 42,
                "visibility": "pub(crate)",
                "container": "",
                "language": "Rust",
                "repository_id": "repo_x",
            }
        ],
        symbol_file={"file_id": "f1", "path": "src/lib.rs", "language": "Rust", "is_test": False},
    )
    package = service.retrieve("What does the helper function do?", None)

    assert package is not None
    assert "No authored documentation" in package["answer"]
    assert "no authored documentation" in package["answer"]


def test_a_symbol_citation_carries_the_file_and_line():
    service, _ = make_service(
        hits=[hit("CodeSymbol", "RedisModule_OpenKey", "RedisModule_OpenKey")],
        symbol=[
            {
                "id": "s1",
                "name": "RedisModule_OpenKey",
                "kind": "function",
                "signature": "fn RedisModule_OpenKey()",
                "doc_comment": "Opens a key.",
                "documented": True,
                "line": 1063,
                "visibility": "pub",
                "container": "",
                "language": "Rust",
                "repository_id": "repo_x",
            }
        ],
        symbol_file={"file_id": "f1", "path": "src/redis.rs", "language": "Rust", "is_test": False},
    )
    package = service.retrieve("What does the RedisModule_OpenKey function do?", None)

    assert package["citations"], "a code answer must cite something"
    assert package["citations"][0].title == "src/redis.rs:1063"
    assert package["citations"][0].type == "code"


def test_symbol_subgraph_links_the_declaration_to_its_file():
    service, _ = make_service(
        hits=[hit("CodeSymbol", "RedisModule_OpenKey", "RedisModule_OpenKey")],
        symbol=[
            {
                "id": "s1",
                "name": "RedisModule_OpenKey",
                "kind": "function",
                "signature": "fn f()",
                "doc_comment": "docs",
                "documented": True,
                "line": 1,
                "visibility": "pub",
                "container": "",
                "language": "Rust",
                "repository_id": "repo_x",
            }
        ],
        symbol_file={"file_id": "f1", "path": "src/redis.rs", "language": "Rust", "is_test": False},
    )
    package = service.retrieve("What does the RedisModule_OpenKey function do?", None)

    labels = {node.label for node in package["graph"].nodes}
    assert {"CodeSymbol", "File"} <= labels


# --- response assembly ------------------------------------------------------


def test_a_package_without_a_subgraph_still_builds_a_response():
    """A code retrieval that matched nothing renderable must not 500."""
    service, _ = make_service(hits=[hit("CodeSymbol", "x", "x")], symbol=[])
    package = service.retrieve("What does the x function do?", None)
    assert package is None, "no declaration means no package"

    empty = {
        "intent": "symbol",
        "entity_id": "s1",
        "answer": "text",
        "evidence_summary": "summary",
        "citations": [],
        "graph": None,
    }
    response = service.build_response("q", empty)
    assert response.graph.nodes == []
    assert response.answer == "text"


@pytest.mark.parametrize(
    "question",
    [
        "What does the open function do?",
        "Describe the graph.rs module",
        "What has changed recently in graph.rs?",
    ],
)
def test_resolution_is_one_graph_round_trip(question):
    """Ask latency depends on this staying constant as questions get longer."""
    service, gateway = make_service(hits=[hit("CodeSymbol", "x", "x")])
    service.resolve_question(question)
    assert gateway.search_entities_by_terms.call_count == 1
    assert gateway.search_code_symbols_by_terms.call_count == 0


def test_synthesis_still_falls_back_when_no_provider_is_available():
    service, _ = make_service(hits=[hit("CodeSymbol", "x", "x")])
    package = {
        "intent": "symbol",
        "entity_id": "s1",
        "answer": "grounded answer",
        "evidence_summary": "s",
        "citations": [],
        "graph": None,
    }
    result = asyncio.run(service.synthesize("q", package))
    assert result["answer"] == "grounded answer"


def test_a_symbol_with_no_exact_match_falls_back_to_near_matches():
    """Resolution matches a prefix; retrieval must not then find nothing.

    "the open function" resolves to open_payload, but an exact-name lookup for
    "open" is empty. Reporting insufficient evidence there would be wrong, so
    the near matches are returned and the answer says they are not an exact hit.
    """
    gateway = MagicMock()
    gateway.search_entities_by_terms.return_value = [
        hit("CodeSymbol", "open_payload", "open", quality=1)
    ]
    gateway.get_code_symbol.side_effect = (
        lambda name, file_id="", limit=6, graph_name="": (
            [declaration("open_payload")] if name == "open_payload" else []
        )
    )
    gateway.search_code_symbols.return_value = [
        {"name": "open_payload", "id": "s1", "kind": "function", "container": "", "documented": True}
    ]
    gateway.get_symbol_file.return_value = None
    service = AskService(gateway=gateway)

    package = service.retrieve("What does the open function do?", None)

    assert package is not None
    assert "No declaration is named exactly `open`" in package["answer"]
    assert "open_payload" in package["answer"]


def test_an_exact_symbol_match_does_not_claim_to_be_near():
    gateway = MagicMock()
    gateway.search_entities_by_terms.return_value = [
        hit("CodeSymbol", "open_payload", "open_payload")
    ]
    gateway.get_code_symbol.return_value = [declaration("open_payload")]
    gateway.get_symbol_file.return_value = {
        "file_id": "f1",
        "path": "src/records.rs",
        "language": "Rust",
        "is_test": False,
    }
    service = AskService(gateway=gateway)

    package = service.retrieve("What does the open_payload function do?", None)

    assert package is not None
    assert "No declaration is named exactly" not in package["answer"]
    assert package["answer"].startswith("**Declarations matching")
