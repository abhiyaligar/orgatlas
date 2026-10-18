"""Repository-scoped routes must read the repository's own graph.

Ingestion moved every repository into a graph named ``code_{repository_id}``,
so a route that still queries the organisation graph returns nothing at all --
not an error, just an empty result, which is the failure this split created.

These use fakes rather than the live graph. The assertion that matters is which
graph name reached the gateway, not what FalkorDB returned.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from starlette.testclient import TestClient

from app.core.errors import GraphNotFoundError
from app.main import create_app


def org_name() -> str:
    from app.graph.connection import org_graph_name

    return org_graph_name()


class FakeGateway:
    """Records the graph every read was issued against."""

    def __init__(self, repositories: Dict[str, str], commits: Dict[str, str] = None):
        # repository_id -> graph that holds it
        self.repositories = repositories
        self.commits = commits or {}
        self.reads: List[str] = []

    def _record(self, graph_name: str) -> None:
        self.reads.append(graph_name or "org")

    def repository_exists(self, repository_id: str, graph_name: str = "") -> bool:
        self._record(graph_name)
        held = self.repositories.get(repository_id)
        if held is None:
            return False
        if graph_name and graph_name != held:
            # A graph that was never created raises rather than answering False,
            # which is how a missing repository became a 503.
            if graph_name.startswith("code_"):
                raise GraphNotFoundError(graph_name, [org_name()])
            return False
        return True

    def get_commit_detail(self, commit_id: str, graph_name: str = "") -> Any:
        self._record(graph_name)
        if self.commits.get(commit_id) != (graph_name or org_name()):
            return None
        return {
            "sha": commit_id,
            "message": "a change",
            "authored_at": "2024-01-01",
            "pr_number": None,
            "author_id": None,
            "author": "dev",
            "repository_id": "repo_x",
        }

    def list_repositories(self, limit: int = 50, graph_name: str = "") -> List[Dict[str, Any]]:
        self._record(graph_name)
        if graph_name == "code_repo_x":
            return [
                {
                    "id": "repo_x",
                    "name": "repo_x",
                    "url": "https://example.com/x",
                    "source": "ingest",
                    "commit_count": 12,
                    "file_count": 34,
                    "graph_name": graph_name,
                }
            ]
        return []

    def get_file_history(self, file_id: str, limit: int = 50, graph_name: str = ""):
        self._record(graph_name)
        return []

    def get_file_description(self, file_id: str, graph_name: str = ""):
        self._record(graph_name)
        return None

    def get_change_coupling(self, file_id: str, limit: int = 15, graph_name: str = ""):
        self._record(graph_name)
        return []

    def __getattr__(self, name: str):
        def _noop(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
            self._record(kwargs.get("graph_name", ""))
            return []

        return _noop


@pytest.fixture()
def wired(monkeypatch):
    """Point the routes at a fake gateway holding one repository."""
    from app.api.routes import repos as repos_module
    from app.graph import gateway as gateway_module

    fake = FakeGateway(
        repositories={"repo_x": "code_repo_x"},
        commits={"abc123": "code_repo_x"},
    )
    monkeypatch.setattr(gateway_module.graph_gateway, "repository_exists", fake.repository_exists)
    monkeypatch.setattr(gateway_module.graph_gateway, "get_commit_detail", fake.get_commit_detail)
    monkeypatch.setattr(gateway_module.graph_gateway, "list_repositories", fake.list_repositories)
    monkeypatch.setattr(
        repos_module._forensics, "gateway", fake, raising=False
    )
    monkeypatch.setattr(
        repos_module._provenance, "gateway", fake, raising=False
    )

    class FakeManager:
        def list_repository_graphs(self):
            return ["code_repo_x"]

    monkeypatch.setattr(gateway_module, "graph_manager", FakeManager(), raising=False)
    monkeypatch.setattr(
        "app.graph.connection.graph_manager", FakeManager(), raising=False
    )
    return fake, TestClient(create_app())


class TestGraphResolution:
    def test_a_repository_routes_to_its_own_graph(self, wired):
        fake, client = wired
        client.get("/api/repos/repo_x/commits")

        assert "code_repo_x" in fake.reads
        assert fake.reads[-1] == "code_repo_x"

    def test_an_unknown_repository_is_404_not_503(self, wired):
        """A graph that was never created must not surface as a server fault."""
        _, client = wired

        for suffix in ("commits", "churn", "brief"):
            response = client.get(f"/api/repos/repo_missing/{suffix}")
            assert response.status_code == 404, suffix

    def test_a_legacy_repository_in_the_org_graph_still_resolves(self, monkeypatch):
        """Before the split every repository lived in the org graph."""
        from app.api.routes import repos as repos_module
        from app.graph import gateway as gateway_module

        fake = FakeGateway(repositories={"repo_old": org_name()})
        monkeypatch.setattr(gateway_module.graph_gateway, "repository_exists", fake.repository_exists)
        monkeypatch.setattr(repos_module._forensics, "gateway", fake, raising=False)

        client = TestClient(create_app())
        assert client.get("/api/repos/repo_old/commits").status_code == 200
        assert org_name() in fake.reads


class TestListing:
    def test_the_list_visits_every_graph(self, wired):
        fake, client = wired
        response = client.get("/api/repos")

        assert response.status_code == 200
        assert "code_repo_x" in fake.reads

    def test_the_list_returns_repositories_from_code_graphs(self, wired):
        _, client = wired
        rows = client.get("/api/repos").json()

        assert [row["id"] for row in rows] == ["repo_x"]
        assert rows[0]["commit_count"] == 12

    def test_one_unreadable_graph_does_not_blank_the_list(self, monkeypatch):
        """A broken repository must not cost us every other repository."""
        from app.graph import gateway as gateway_module

        good = {
            "id": "repo_x",
            "name": "repo_x",
            "url": "https://example.com/x",
            "source": "ingest",
            "commit_count": 1,
            "file_count": 1,
            "graph_name": "code_repo_x",
        }

        def flaky(limit: int = 50, graph_name: str = ""):
            if graph_name == "code_broken":
                raise RuntimeError("graph is unavailable")
            return [good] if graph_name == "code_repo_x" else []

        monkeypatch.setattr(gateway_module.graph_gateway, "list_repositories", flaky)

        class FakeManager:
            def list_repository_graphs(self):
                return ["code_repo_x", "code_broken"]

        monkeypatch.setattr(gateway_module, "graph_manager", FakeManager(), raising=False)
        monkeypatch.setattr(
            "app.graph.connection.graph_manager", FakeManager(), raising=False
        )

        client = TestClient(create_app())
        rows = client.get("/api/repos").json()

        assert [row["id"] for row in rows] == ["repo_x"]

    def test_an_empty_graph_contributes_nothing(self, wired):
        """A graph left behind by a test is invisible rather than listed empty."""
        fake, client = wired
        rows = client.get("/api/repos").json()

        assert all(row["id"] for row in rows)


class TestCommitProvenance:
    def test_a_commit_is_found_without_naming_its_repository(self, wired):
        fake, client = wired

        response = client.get("/api/repos/commit/abc123")

        assert response.status_code == 200
        assert "code_repo_x" in fake.reads

    def test_a_repository_id_skips_the_search(self, wired):
        fake, client = wired
        before = len(fake.reads)

        response = client.get("/api/repos/commit/abc123?repository_id=repo_x")

        assert response.status_code == 200
        assert set(fake.reads[before:]) == {"code_repo_x"}

    def test_the_optional_parameter_actually_parses(self, wired):
        """A query parameter that only breaks when supplied is the worst kind.

        `Optional` was not imported at module scope, so the route worked for
        every existing caller and raised a Pydantic forward-reference error the
        first time anyone passed a repository.
        """
        _, client = wired

        assert client.get("/api/repos/commit/abc123?repository_id=repo_x").status_code == 200

    def test_an_unknown_commit_is_404(self, wired):
        _, client = wired

        assert client.get("/api/repos/commit/nope").status_code == 404

    def test_a_commit_asked_for_in_the_wrong_repository_is_404(self, wired):
        _, client = wired

        response = client.get("/api/repos/commit/abc123?repository_id=repo_missing")
        assert response.status_code == 404

class TestFileScopedRoutes:
    """A file_id is `{repository_id}::{path}`, so it names its own graph."""

    def test_a_file_id_selects_the_repository_graph(self, wired):
        fake, client = wired

        client.get("/api/repos/file/timeline", params={"file_id": "repo_x::src/a.rs"})

        assert "code_repo_x" in fake.reads

    def test_a_file_id_without_the_prefix_is_400(self, wired):
        """Guessing the org graph would return an empty result, not an error."""
        _, client = wired

        for path in ("/api/repos/file/timeline", "/api/repos/file/describe",
                     "/api/repos/file/coupling"):
            response = client.get(path, params={"file_id": "notafile"})
            assert response.status_code == 400, path

    def test_describe_file_routes_to_the_repository_graph(self, wired):
        fake, client = wired

        client.get("/api/repos/file/describe", params={"file_id": "repo_x::src/a.rs"})

        assert "code_repo_x" in fake.reads


class TestNoSilentFallbacks:
    """A graph-aware method must never quietly read the org graph instead.

    The default of graph_name="" means "organisation graph", so a call site
    that forgets to forward it reads an empty graph and returns nothing at all
    -- no error, just a blank page. These assert the wiring rather than the
    output, because that is what regresses.
    """

    def test_every_graph_aware_service_method_forwards_the_graph(self):
        import ast
        from pathlib import Path as P

        service = P("app/services/change_forensics_service.py").read_text(encoding="utf-8")
        cls = next(
            n for n in ast.parse(service).body if isinstance(n, ast.ClassDef)
        )
        gateway = P("app/graph/gateway.py").read_text(encoding="utf-8")
        gw_cls = next(
            n for n in ast.parse(gateway).body if isinstance(n, ast.ClassDef)
        )
        aware = {
            f.name
            for f in gw_cls.body
            if isinstance(f, ast.FunctionDef)
            and any(a.arg == "graph_name" for a in f.args.args)
        } - {"_execute"}

        dropped = []
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name != "__init__"):
                continue
            if not any(a.arg == "graph_name" for a in fn.args.args):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in aware
                    and not any(k.arg == "graph_name" for k in node.keywords)
                ):
                    dropped.append(f"{fn.name} -> {node.func.attr} (line {node.lineno})")

        assert not dropped, dropped

    def test_a_graph_aware_method_never_calls_a_graph_aware_method_without_it(self):
        """investigation_brief called churn_ranking with no graph, which read org."""
        import ast
        from pathlib import Path as P

        service = P("app/services/change_forensics_service.py").read_text(encoding="utf-8")
        cls = next(
            n for n in ast.parse(service).body if isinstance(n, ast.ClassDef)
        )
        methods = {
            f.name
            for f in cls.body
            if isinstance(f, ast.FunctionDef)
            and any(a.arg == "graph_name" for a in f.args.args)
        }

        dropped = []
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name != "__init__"):
                continue
            if not any(a.arg == "graph_name" for a in fn.args.args):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in methods
                    and not any(k.arg == "graph_name" for k in node.keywords)
                ):
                    dropped.append(f"{fn.name} -> {node.func.attr} (line {node.lineno})")

        assert not dropped, dropped
