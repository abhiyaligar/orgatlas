"""Tests for the repository forensics services.

Retrieval is mocked so the suite runs offline against no graph.
"""

from unittest.mock import MagicMock

import pytest

from app.services.change_forensics_service import ChangeForensicsService, repository_id_for_path
from app.services.commit_provenance_service import CommitProvenanceService


@pytest.fixture
def gateway():
    g = MagicMock()
    g.get_file_history.return_value = []
    g.get_file_churn.return_value = []
    g.get_files_changed_since.return_value = []
    g.get_path_contributors.return_value = []
    g.get_commits_for_path.return_value = []
    g.get_dependency_impact.return_value = []
    g.get_change_coupling.return_value = []
    g.get_commit_detail.return_value = None
    return g


class TestRepositoryIdHelper:
    def test_splits_on_the_node_separator(self):
        assert repository_id_for_path("repo_a::src/main.rs") == "repo_a"

    def test_passes_through_a_plain_id(self):
        assert repository_id_for_path("repo_a") == "repo_a"


class TestFileTimeline:
    def test_returns_none_without_history(self, gateway):
        service = ChangeForensicsService(gateway=gateway)
        assert service.file_timeline("repo_a::src/main.rs") is None

    def test_builds_nodes_edges_and_citations(self, gateway):
        gateway.get_file_history.return_value = [
            {
                "sha": "a" * 40,
                "message": "fix: guard against empty graph",
                "authored_at": "2025-01-02T00:00:00Z",
                "pr_number": 101,
                "author_id": "eid_github_abc",
                "author": "Alex",
            }
        ]
        service = ChangeForensicsService(gateway=gateway)
        result = service.file_timeline("repo_a::src/main.rs")

        assert result is not None
        assert result["change_count"] == 1
        assert result["path"] == "src/main.rs"
        assert result["repository_id"] == "repo_a"
        assert len(result["graph"].nodes) == 3
        assert {e.type for e in result["graph"].edges} == {"MODIFIES", "AUTHORED"}
        assert result["citations"][0].source_id == "a" * 40
        assert result["graph"].paths


class TestChurnRanking:
    def test_separates_test_files_from_hotspots(self, gateway):
        gateway.get_file_churn.return_value = [
            {"file_id": "a", "path": "src/a.rs", "is_test": False, "changes": 10},
            {"file_id": "b", "path": "tests/a.rs", "is_test": True, "changes": 30},
        ]
        result = ChangeForensicsService(gateway=gateway).churn_ranking("repo_a")

        assert len(result["files"]) == 2
        assert [f["path"] for f in result["hotspots"]] == ["src/a.rs"]


class TestCoupling:
    def test_reports_no_coupling_when_nothing_matches(self, gateway):
        result = ChangeForensicsService(gateway=gateway).coupled_files("repo_a::src/main.rs")
        assert result["coupled"] == []
        assert "No co-changing files" in result["advice"]

    def test_advises_treating_coupled_files_as_one_unit(self, gateway):
        gateway.get_change_coupling.return_value = [
            {"file_id": "b", "path": "src/lib.rs", "shared_commits": 4}
        ]
        result = ChangeForensicsService(gateway=gateway).coupled_files("repo_a::src/main.rs")
        assert "one unit" in result["advice"]


class TestInvestigationBrief:
    def test_flags_the_hottest_file_and_its_owners(self, gateway):
        gateway.get_file_churn.return_value = [
            {"file_id": "a", "path": "src/core.rs", "is_test": False, "changes": 12}
        ]
        gateway.get_path_contributors.return_value = [
            {"author_id": "eid_x", "author": "Alex", "commits": 30}
        ]
        gateway.get_dependency_impact.return_value = [
            {"id": "repo_dep", "name": "org/dep", "url": "https://github.com/org/dep"}
        ]

        brief = ChangeForensicsService(gateway=gateway).investigation_brief("repo_a")

        assert any("src/core.rs" in g for g in brief["guidance"])
        assert any("Alex" in g for g in brief["guidance"])
        assert any("dependent repositories" in g for g in brief["guidance"])

    def test_states_when_no_history_was_ingested(self, gateway):
        brief = ChangeForensicsService(gateway=gateway).investigation_brief("repo_a")
        assert brief["hotspots"] == []
        assert any("No ingested history" in g for g in brief["guidance"])


class TestChangesSince:
    def test_reports_the_window_and_file_count(self, gateway):
        gateway.get_files_changed_since.return_value = [
            {"file_id": "a", "path": "src/a.rs", "changes": 3},
            {"file_id": "b", "path": "src/b.rs", "changes": 1},
        ]
        result = ChangeForensicsService(gateway=gateway).changes_since("repo_a", "2025-01-01")
        assert result["file_count"] == 2
        assert result["since"] == "2025-01-01"


class TestCommitProvenance:
    def test_returns_none_for_unknown_commit(self, gateway):
        assert CommitProvenanceService(gateway=gateway).trace("deadbeef") is None

    def test_records_explicit_gaps_when_nothing_explains_the_change(self, gateway):
        gateway.get_commit_detail.return_value = {
            "sha": "a" * 40,
            "message": "chore: bump",
            "authored_at": "2025-01-01T00:00:00Z",
            "pr_number": None,
            "author_id": "",
            "author": "",
            "repository_id": "repo_a",
        }
        gateway._execute.return_value = []

        result = CommitProvenanceService(gateway=gateway).trace("a" * 40)

        assert result is not None
        assert result["confidence"] in {"partial", "insufficient"}
        assert len(result["gaps"]) == 3
        assert any("No architecture decision" in gap for gap in result["gaps"])
        assert any("pull-request reference" in gap for gap in result["gaps"])
        assert any("attributed author" in gap for gap in result["gaps"])

    def test_links_decisions_and_their_sources_when_present(self, gateway):
        gateway.get_commit_detail.return_value = {
            "sha": "a" * 40,
            "message": "feat: adopt caching",
            "authored_at": "2025-01-01T00:00:00Z",
            "pr_number": 7,
            "author_id": "eid_x",
            "author": "Alex",
            "repository_id": "repo_a",
        }

        calls = {"n": 0}

        def execute(query, params, *_args, **_kwargs):
            calls["n"] += 1
            if "Decision {id: $decision_id}" in query:
                return [["doc_1", "RFC-042", "Document", "https://x/doc_1"]]
            return [["dec_1", "Adopt caching", "Because latency."]]

        gateway._execute.side_effect = execute

        result = CommitProvenanceService(gateway=gateway).trace("a" * 40)

        assert result["decisions"][0]["id"] == "dec_1"
        assert len(result["citations"]) == 2
        assert result["confidence"] == "supported"
        assert "IMPLEMENTS" in {e.type for e in result["graph"].edges}
        assert "SUPPORTED_BY" in {e.type for e in result["graph"].edges}