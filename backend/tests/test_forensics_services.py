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

class TestFileDescription:
    """describe_file reports authored text and whether it is still current."""

    def _record(self, **overrides):
        base = {
            "path": "src/graph.rs",
            "name": "graph.rs",
            "language": "Rust",
            "is_test": False,
            "summary": "Graph traversal over a property graph.",
            "symbols": '["Graph", "query"]',
            "docs_source": "module",
            "docs_at_sha": "abc1234def",
            "repository_id": "repo_falkordb_falkordb",
        }
        base.update(overrides)
        return base

    def test_returns_authored_summary_and_symbols(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = self._record()
        service.gateway.get_commit_authored_at.return_value = "2024-01-01T00:00:00Z"
        service.gateway.get_file_changes_after.return_value = {"changes": 0, "recent_shas": []}

        result = service.describe_file("repo_x::src/graph.rs")

        assert result["summary"] == "Graph traversal over a property graph."
        assert result["symbols"] == ["Graph", "query"]
        assert result["docs_source"] == "module"
        assert result["stale"] is False
        assert "matches the file as of" in result["staleness_reason"]

    def test_marks_stale_when_the_file_changed_after_the_docs(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = self._record()
        service.gateway.get_commit_authored_at.return_value = "2024-01-01T00:00:00Z"
        service.gateway.get_file_changes_after.return_value = {
            "changes": 3,
            "recent_shas": ["dead111"],
        }

        result = service.describe_file("repo_x::src/graph.rs")

        assert result["stale"] is True
        assert result["changes_since_docs"] == 3
        assert "abc1234" in result["staleness_reason"]
        assert "reflects that revision" in result["staleness_reason"]

    def test_marks_stale_when_no_description_was_recorded(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = self._record(
            summary="", symbols="[]", docs_source="none", docs_at_sha=""
        )

        result = service.describe_file("repo_x::src/thing.rs")

        assert result["stale"] is True
        assert "No description was recorded" in result["staleness_reason"]
        service.gateway.get_commit_authored_at.assert_not_called()

    def test_marks_stale_when_the_docs_commit_is_unknown(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = self._record()
        service.gateway.get_commit_authored_at.return_value = None

        result = service.describe_file("repo_x::src/graph.rs")

        assert result["stale"] is True
        assert "not in the ingested history" in result["staleness_reason"]

    def test_unknown_file_returns_none(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = None
        assert service.describe_file("repo_x::missing.rs") is None

    def test_unparsable_symbols_do_not_raise(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = self._record(symbols="not json")
        service.gateway.get_commit_authored_at.return_value = "2024-01-01T00:00:00Z"
        service.gateway.get_file_changes_after.return_value = {"changes": 0, "recent_shas": []}

        result = service.describe_file("repo_x::src/graph.rs")

        assert result["symbols"] == []

    def test_never_invents_a_summary(self):
        service = ChangeForensicsService(gateway=MagicMock())
        service.gateway.get_file_description.return_value = self._record(
            summary="", symbols="[]", docs_source="none", docs_at_sha="abc"
        )
        service.gateway.get_commit_authored_at.return_value = "2024-01-01T00:00:00Z"
        service.gateway.get_file_changes_after.return_value = {"changes": 0, "recent_shas": []}

        result = service.describe_file("repo_x::src/plain.rs")

        assert result["summary"] == ""

class TestDescribeSymbol:
    """Declaration lookup must never silently guess between matches."""

    def _gateway(self, matches, changes=0):
        from unittest.mock import MagicMock

        g = MagicMock()
        g.get_code_symbol.return_value = matches
        g.get_symbol_file.return_value = {
            "file_id": "repo_x::src/f.rs",
            "path": "src/f.rs",
            "repository_id": "repo_x",
            "language": "Rust",
            "is_test": False,
        }
        g.get_commit_authored_at.return_value = "2024-01-01T00:00:00Z"
        g.get_file_changes_after.return_value = {"changes": changes, "recent_shas": []}
        g.get_path_contributors.return_value = []
        g.get_file_history.return_value = [
            {
                "sha": "s1",
                "message": "init",
                "authored_at": "2024-01-01",
                "author": "dev",
                "author_id": "p1",
                "pr_number": 3,
                "short_sha": "s1",
                "is_merge": False,
                "repository_id": "repo_x",
            }
        ]
        return g

    def _match(self, **overrides):
        base = {
            "id": "repo_x::src/f.rs::function:C:new",
            "name": "new",
            "kind": "function",
            "signature": "pub fn new() -> Self",
            "doc_comment": "Builds it.",
            "documented": True,
            "line": 14,
            "visibility": "pub",
            "container": "Default for Widget",
            "language": "Rust",
            "repository_id": "repo_x",
            "docs_at_sha": "abc1234def",
        }
        base.update(overrides)
        return base

    def test_returns_documented_symbol_with_its_file_and_line(self):
        service = ChangeForensicsService(gateway=self._gateway([self._match()]))
        result = service.describe_symbol("new")

        assert result["match_count"] == 1
        match = result["matches"][0]
        assert match["doc_comment"] == "Builds it."
        assert match["path"] == "src/f.rs"
        assert match["line"] == 14
        assert match["signature"].startswith("pub fn new")

    def test_ambiguous_name_returns_every_match_with_its_container(self):
        gateway = self._gateway(
            [
                self._match(),
                self._match(
                    id="repo_x::src/f.rs::function:Widget:new",
                    container="Widget",
                    doc_comment="",
                    documented=False,
                    line=20,
                ),
            ]
        )
        result = ChangeForensicsService(gateway=gateway).describe_symbol("new")

        assert result["match_count"] == 2
        assert {m["container"] for m in result["matches"]} == {"Default for Widget", "Widget"}
        assert any("matches 2 declarations" in note for note in result["notes"])

    def test_undocumented_symbol_is_flagged_not_hidden(self):
        gateway = self._gateway([self._match(doc_comment="", documented=False)])
        result = ChangeForensicsService(gateway=gateway).describe_symbol("new")

        assert result["matches"][0]["documented"] is False
        assert any("None of these declarations" in g for g in result["guidance"])

    def test_drift_is_measured_against_the_owning_file(self):
        gateway = self._gateway([self._match()], changes=4)
        result = ChangeForensicsService(gateway=gateway).describe_symbol("new")

        assert result["matches"][0]["changes_since_docs"] == 4
        gateway.get_file_changes_after.assert_called_with("repo_x::src/f.rs", "2024-01-01T00:00:00Z")

    def test_unknown_scan_point_reports_no_drift_evidence(self):
        gateway = self._gateway([self._match(docs_at_sha="")])
        result = ChangeForensicsService(gateway=gateway).describe_symbol("new")

        assert result["matches"][0]["changes_since_docs"] == 0
        gateway.get_commit_authored_at.assert_not_called()

    def test_no_match_is_an_explicit_refusal(self):
        result = ChangeForensicsService(gateway=self._gateway([])).describe_symbol("nope")

        assert result["match_count"] == 0
        assert result["matches"] == []
        assert any(
            "exported declarations are recorded" in note for note in result["notes"]
        )

    def test_recent_history_is_attached(self):
        gateway = self._gateway([self._match()])
        result = ChangeForensicsService(gateway=gateway).describe_symbol("new")
        assert result["matches"][0]["recent_history"][0]["sha"] == "s1"