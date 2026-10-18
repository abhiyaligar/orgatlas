"""Repository-scoped MCP tools must read the repository's graph.

This is the same defect as the REST routing fix, in the surface that matters
more: these are the tools a coding agent calls. Seven of the eleven read tools
answered from the organisation graph, where no File, Commit or Repository node
exists, and returned a refusal reading "no ingested history" for repositories
whose history was sitting in their own graph the whole time.

The refusals were indistinguishable from genuinely undocumented code, so a
caller could not tell a missing graph from a missing fact.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.graph.repository_scope import (
    InvalidFileId,
    UnknownRepository,
    graph_for_file,
    repository_graph,
)
from app.mcp import tools

ORG = "orgatlas_dev"
REPO_GRAPH = "code_repo_x"
REPO = "repo_x"


class FakeForensics:
    """Records the graph every read was issued against."""

    def __init__(self) -> None:
        self.reads: List[str] = []

    def _record(self, graph_name: str) -> None:
        self.reads.append(graph_name or ORG)

    def investigation_brief(self, repository_id: str, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {
            "repository_id": repository_id,
            "hotspots": [
                {"file_id": f"{REPO}::src/a.rs", "path": "src/a.rs", "changes": 3}
            ],
            "dependency_blast_radius": [],
            "contributors": [{"author_id": "a@x", "author": "A", "commits": 3}],
            "guidance": [],
        }

    def churn_ranking(self, repository_id: str, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {
            "files": [{"file_id": f"{REPO}::src/a.rs", "path": "src/a.rs",
                       "changes": 3, "last_author": "A", "is_test": False}],
            "hotspots": [{"file_id": f"{REPO}::src/a.rs", "path": "src/a.rs",
                          "changes": 3}],
        }

    def module_history(self, repository_id: str, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {"commits": [], "contributors": []}

    def file_timeline(self, file_id: str, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {
            "history": [],
            "citations": [],
            "path": "src/a.rs",
            "change_count": 4,
            "graph": {"nodes": [], "edges": [], "paths": []},
        }

    def coupled_files(self, file_id: str, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {
            "advice": "nothing else changes with it",
            "coupled": [{"file_id": f"{REPO}::src/b.rs", "path": "src/b.rs",
                         "shared_commits": 3}],
        }

    def describe_file(self, file_id: str, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {
            "file_id": file_id,
            "path": "a",
            "language": "Rust",
            "summary": "does a thing",
            "symbols": ["one", "two"],
            "docs_source": "module_docs",
            "provenance": {"origin": "authored", "model": ""},
            "staleness_reason": "",
            "stale": False,
            "docs_at_sha": "abc",
            "recent_shas": [],
            "changes_since_docs": 0,
            "is_test": False,
        }

    def describe_symbol(self, name: str, file_id: str = "", **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return {"match_count": 0, "matches": []}

    def get_code_symbol(self, name: str, file_id: str = "", limit: int = 10, graph_name: str = ""):
        self._record(graph_name)
        return []

    def get_code_symbol(self, name: str, file_id: str = "", limit: int = 10, **kwargs):
        self._record(kwargs.get("graph_name", ""))
        return []

    def search_code_symbols_in_every_graph(self, name: str, limit: int = 10):
        self._record("*")
        return []


@pytest.fixture()
def wired(monkeypatch):
    """Point the tools at a fake forensics service and a known repository."""
    fake = FakeForensics()
    monkeypatch.setattr(tools, "_forensics", fake, raising=False)

    monkeypatch.setattr(
        "app.graph.gateway.graph_gateway.repository_exists",
        lambda repository_id, graph_name="": graph_name == REPO_GRAPH,
        raising=False,
    )
    return fake


class TestResolution:
    def test_a_known_repository_resolves_to_its_graph(self, wired):
        assert repository_graph(REPO) == REPO_GRAPH

    def test_an_unknown_repository_raises_rather_than_guessing(self, wired):
        with pytest.raises(UnknownRepository):
            repository_graph("repo_nope")

    def test_a_legacy_repository_falls_back_to_the_org_graph(self, monkeypatch):
        monkeypatch.setattr(
            "app.graph.gateway.graph_gateway.repository_exists",
            lambda repository_id, graph_name="": graph_name == ORG,
            raising=False,
        )
        assert repository_graph("repo_old") == ORG

    def test_a_file_id_names_its_graph(self, wired):
        assert graph_for_file(f"{REPO}::src/a.rs") == REPO_GRAPH

    def test_a_file_id_without_a_repository_is_rejected(self, wired):
        with pytest.raises(InvalidFileId):
            graph_for_file("src/a.rs")


class TestToolsUseTheGraph:
    """Each tool must reach the right graph, not merely not crash."""

    def test_describe_file(self, wired):
        result = tools.describe_file(f"{REPO}::src/a.rs")

        assert REPO_GRAPH in wired.reads
        assert "does a thing" in str(result)

    def test_trace_change_origin(self, wired):
        tools.trace_change_origin(f"{REPO}::src/a.rs")

        assert REPO_GRAPH in wired.reads

    def test_assess_file_risk(self, wired):
        tools.assess_file_risk(file_path="src", repository_id=REPO)

        assert wired.reads.count(REPO_GRAPH) >= 2

    def test_get_architecture_context(self, wired):
        tools.get_architecture_context(REPO)

        assert REPO_GRAPH in wired.reads

    def test_get_repo_dependency_impact(self, wired):
        tools.get_repo_dependency_impact(REPO)

        assert REPO_GRAPH in wired.reads

    def test_find_owner_and_expertise(self, wired, monkeypatch):
        monkeypatch.setattr(tools._ownership, "get_ownership", lambda target: None)

        tools.find_owner_and_expertise(REPO)

        assert REPO_GRAPH in wired.reads

    def test_no_tool_reads_the_org_graph_for_a_known_repository(self, wired, monkeypatch):
        """The regression in one assertion."""
        monkeypatch.setattr(tools._ownership, "get_ownership", lambda target: None)
        before = len(wired.reads)
        for call in (
            lambda: tools.describe_file(f"{REPO}::src/a.rs"),
            lambda: tools.trace_change_origin(f"{REPO}::src/a.rs"),
            lambda: tools.assess_file_risk(file_path="src", repository_id=REPO),
            lambda: tools.get_architecture_context(REPO),
            lambda: tools.get_repo_dependency_impact(REPO),
            lambda: tools.find_owner_and_expertise(REPO),
        ):
            call()

        used = wired.reads[before:]
        assert used, "no reads happened"
        assert ORG not in used, f"read the org graph: {used}"


class TestUnscopedSymbolLookup:
    """A symbol name carries no repository, so it cannot pick one graph.

    The branch lives in the service, not the tool: the tool cannot know whether
    a caller meant "this file" or "anywhere". So this drives the real service
    with a fake gateway rather than faking the service itself.
    """

    def test_a_name_alone_searches_every_repository_graph(self):
        from app.services.change_forensics_service import ChangeForensicsService

        gateway = FakeForensics()
        service = ChangeForensicsService(gateway=gateway)

        service.describe_symbol("register")

        assert "*" in gateway.reads, "the cross-graph search was not used"

    def test_a_file_id_still_scopes_to_one_graph(self):
        from app.services.change_forensics_service import ChangeForensicsService

        gateway = FakeForensics()
        service = ChangeForensicsService(gateway=gateway)

        service.describe_symbol("register", file_id="repo_x::src/a.rs", graph_name=REPO_GRAPH)

        assert "*" not in gateway.reads
        assert gateway.reads == [REPO_GRAPH]

    def test_an_explicit_graph_is_never_reinterpreted(self):
        from app.services.change_forensics_service import ChangeForensicsService

        gateway = FakeForensics()
        service = ChangeForensicsService(gateway=gateway)

        service.describe_symbol("register", graph_name="code_somewhere_else")

        assert gateway.reads == ["code_somewhere_else"]


class TestUnresolvableIdsRefuseCleanly:
    """A bad id must produce a refusal with a reason, not "Error executing tool"."""

    def test_describe_file_with_a_bad_file_id(self, wired):
        result = tools.describe_file("not-a-file-id")

        assert "not a node id" in str(result).lower()
        assert "::" in str(result)

    def test_assess_file_risk_with_an_unknown_repository(self, wired):
        result = tools.assess_file_risk(file_path="src", repository_id="repo_nope")

        assert "not in the knowledge graph" in str(result).lower()
        assert wired.reads == []

    def test_a_refusal_still_names_the_remedy(self, wired):
        result = tools.assess_file_risk(file_path="src", repository_id="repo_nope")

        assert "ingest_repository" in str(result)


class TestNoSilentFallbacks:
    def test_every_graph_aware_service_call_in_mcp_forwards_the_graph(self):
        """The structural guard that would have caught this before release."""
        import ast
        from pathlib import Path

        def top(path):
            return next(
                n
                for n in ast.parse(Path(path).read_text(encoding="utf-8")).body
                if isinstance(n, ast.ClassDef)
            )

        needs = {
            f.name
            for f in top("app/services/change_forensics_service.py").body
            if isinstance(f, ast.FunctionDef)
            and any(a.arg == "graph_name" for a in f.args.args)
        }

        dropped = []
        for fn in ast.parse(Path("app/mcp/tools.py").read_text(encoding="utf-8")).body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in needs
                    and not any(k.arg == "graph_name" for k in node.keywords)
                ):
                    dropped.append(f"{fn.name} -> {node.func.attr} (line {node.lineno})")

        assert not dropped, dropped