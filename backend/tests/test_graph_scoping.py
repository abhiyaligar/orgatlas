"""Repository graphs are named, derived, and never silently empty.

The graph name used to be read from one global setting, which meant every
repository shared one graph. Now there are two kinds of graph: one holding the
organisation, and one per repository holding that repository's code.

The naming has to be derived rather than stored, or a lost registry row would
orphan data that is still on the instance.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.graph import connection
from app.graph.connection import (
    org_graph_name,
    repository_graph_name,
)


class TestRepositoryGraphNaming:
    def test_a_repository_id_becomes_its_own_graph(self):
        assert repository_graph_name("repo_abhiyaligar_estatex") == (
            "code_repo_abhiyaligar_estatex"
        )

    def test_the_same_repository_always_resolves_to_the_same_graph(self):
        """Derived, not stored, so a re-ingest cannot orphan its own data."""
        first = repository_graph_name("repo_owner_name")
        second = repository_graph_name("repo_owner_name")

        assert first == second

    def test_different_repositories_get_different_graphs(self):
        assert repository_graph_name("repo_a") != repository_graph_name("repo_b")

    def test_characters_a_graph_name_may_not_take_are_replaced(self):
        assert "/" not in repository_graph_name("repo/owner/name")
        assert "." not in repository_graph_name("repo.owner.name")

    def test_an_empty_repository_id_is_refused(self):
        with pytest.raises(ValueError):
            repository_graph_name("")

    def test_a_blank_repository_id_is_refused(self):
        with pytest.raises(ValueError):
            repository_graph_name("   ")

    def test_the_two_graph_families_cannot_collide(self):
        """A repository called org must not land in the organisation graph."""
        assert repository_graph_name("org") != org_graph_name()


class TestGraphListing:
    def _manager(self, graphs):
        manager = connection.FalkorDBManager()
        manager._client = MagicMock()
        manager._client.list_graphs.return_value = graphs
        return manager

    def test_repository_graphs_are_listed_apart_from_the_org_graph(self):
        manager = self._manager(["orgatlas_dev", "code_repo_a", "code_repo_b"])

        assert manager.list_repository_graphs() == ["code_repo_a", "code_repo_b"]

    def test_a_graph_without_the_prefix_is_not_treated_as_a_repository(self):
        manager = self._manager(["orgatlas_dev", "scratch", "code_repo_a"])

        assert manager.list_repository_graphs() == ["code_repo_a"]

    def test_search_order_puts_the_org_graph_first(self):
        manager = self._manager(["code_repo_a", "orgatlas_dev", "code_repo_b"])

        assert manager.search_graphs() == [
            "orgatlas_dev",
            "code_repo_a",
            "code_repo_b",
        ]

    def test_a_missing_org_graph_is_not_searched_rather_than_failing(self):
        manager = self._manager(["code_repo_a"])

        assert manager.search_graphs() == ["code_repo_a"]

    def test_status_reports_the_repository_graphs(self):
        manager = self._manager(["orgatlas_dev", "code_repo_a"])
        with patch.object(connection.FalkorDBManager, "check_health", return_value=True):
            status = manager.graph_status()

        assert status["repository_graphs"] == ["code_repo_a"]
        assert status["graph_exists"] is True


class TestSchemaBootstrap:
    def test_a_new_graph_receives_the_project_indexes(self):
        manager = connection.FalkorDBManager()
        manager._client = MagicMock()
        graph = MagicMock()
        manager._client.select_graph.return_value = graph

        with patch(
            "app.graph.schema.get_graph_index_statements",
            return_value=["CREATE INDEX FOR (n:Team) ON (n.id)"],
        ):
            applied = manager.ensure_schema("code_repo_a")

        assert applied == 1
        assert "code_repo_a" in manager._client.select_graph.call_args[0]

    def test_an_index_that_will_not_apply_does_not_raise(self):
        """An ingest must not die because one index already exists."""
        manager = connection.FalkorDBManager()
        manager._client = MagicMock()
        graph = MagicMock()
        graph.query.side_effect = Exception("index already exists")
        manager._client.select_graph.return_value = graph

        with patch(
            "app.graph.schema.get_graph_index_statements",
            return_value=["CREATE INDEX FOR (n:Team) ON (n.id)"],
        ):
            assert manager.ensure_schema("code_repo_a") == 0

    def test_the_graph_being_bootstrapped_is_the_one_named(self):
        """Creating indexes on the org graph by mistake is the failure to avoid."""
        manager = connection.FalkorDBManager()
        manager._client = MagicMock()

        with patch("app.graph.schema.get_graph_index_statements", return_value=[]):
            manager.ensure_schema("code_repo_specific")

        assert manager._client.select_graph.call_args[0][0] == "code_repo_specific"