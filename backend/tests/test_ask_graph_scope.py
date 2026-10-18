"""A resolved entity must be read back from the graph it came from.

With one graph per repository, resolution and retrieval have to agree. The
failure this guards against is quiet and looks like a missing feature: the term
resolves against a repository's graph, the retrieval then reads the org graph,
finds nothing there, and /ask reports "insufficient evidence" for an entity it
had just located.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.ask_service import AskService
from app.services.question_resolution import (
    INTENT_FILE,
    INTENT_SYMBOL,
    ResolvedEntity,
    Route,
)


def _entity(label="CodeSymbol", name="open_payload", graph="code_repo_a"):
    return ResolvedEntity(
        term=name,
        entity_id=f"{label}:{name}",
        label=label,
        name=name,
        quality=0,
        graph_name=graph,
    )


@pytest.fixture()
def gateway():
    g = MagicMock()
    g.get_code_symbol.return_value = []
    g.search_code_symbols.return_value = []
    g.get_symbol_file.return_value = None
    g.get_file_description.return_value = None
    return g


def test_term_resolution_reads_every_graph(gateway):
    service = AskService(gateway=gateway)

    service.resolve_question("Where is open_payload defined?")

    # No explicit list: the gateway decides, and the default is every graph.
    assert gateway.search_entities_by_terms.called


def test_a_symbol_is_read_from_the_repository_graph_it_resolved_in(gateway):
    gateway.get_code_symbol.return_value = [
        {
            "id": "s1",
            "name": "open_payload",
            "kind": "function",
            "signature": "def open_payload()",
            "doc_comment": "Open a batch.",
            "documented": True,
            "container": "",
            "file_id": "repo::parser.py",
            "language": "Python",
            "line": 10,
            "visibility": "public",
            "changes_since_docs": 0,
        }
    ]
    service = AskService(gateway=gateway)
    service.resolve_question = lambda _q: (
        Route(intent=INTENT_SYMBOL, entity=_entity()),
        [_entity()],
    )

    service.retrieve("Where is open_payload defined?", None)

    assert gateway.get_code_symbol.call_args.kwargs["graph_name"] == "code_repo_a"


def test_a_file_is_read_from_its_own_repository_graph(gateway):
    gateway.get_file_description.return_value = {
        "path": "backend/parser.py",
        "name": "parser.py",
        "language": "Python",
        "summary": "Parses batches.",
        "symbols": "[]",
        "docs_source": "authored",
        "docs_at_sha": "abc",
        "repository_id": "repo_a",
    }
    service = AskService(gateway=gateway)
    service.resolve_question = lambda _q: (
        Route(
            intent=INTENT_FILE,
            entity=ResolvedEntity(
                term="parser.py",
                entity_id="repo_a::backend/parser.py",
                label="File",
                name="parser.py",
                quality=0,
                graph_name="code_repo_b",
            ),
        ),
        [],
    )

    # The graph that answered is not the graph the repository is named for,
    # which is exactly the case a hardcoded name would get wrong.
    service.retrieve("Describe the parser.py file", None)

    assert gateway.get_file_description.call_args.kwargs["graph_name"] == "code_repo_b"


def test_an_organisation_entity_is_read_from_the_org_graph(gateway):
    gateway.get_repository_language_mix.return_value = [{"language": "Python", "files": 3}]
    gateway.get_repository_files.return_value = []
    service = AskService(gateway=gateway)
    service.resolve_question = lambda _q: (
        Route(
            intent=INTENT_FILE,
            entity=ResolvedEntity(
                term="checkout",
                entity_id="repo_checkout",
                label="Repository",
                name="checkout",
                quality=0,
                graph_name="orgatlas_dev",
            ),
        ),
        [],
    )

    service.retrieve("What is the tech stack of checkout", None)

    assert gateway.get_repository_language_mix.call_args.kwargs["graph_name"] == "orgatlas_dev"


def test_an_entity_with_no_graph_still_reads_the_org_graph(gateway):
    """An entity built before this change has no graph_name, and must not break."""
    legacy = ResolvedEntity(
        term="legacy", entity_id="CodeSymbol:legacy", label="CodeSymbol", name="legacy"
    )
    assert legacy.graph_name == ""

    gateway.get_code_symbol.return_value = []
    service = AskService(gateway=gateway)
    service.resolve_question = lambda _q: (
        Route(intent=INTENT_SYMBOL, entity=legacy),
        [legacy],
    )

    service.retrieve("What does legacy do?", None)

    assert gateway.get_code_symbol.call_args.kwargs["graph_name"] == ""