"""The graph connection has to survive a long model pass.

The client is a process-wide singleton. A repository ingest opens it early, then
spends minutes calling the model provider before writing anything back, by which
time the server has closed the connection that was handed to the caller. The
first write then failed with a socket timeout, and every generated description
was lost with it.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_the_client_is_given_timeouts_and_a_retry():
    """A bulk write over hundreds of rows outlasts any default read timeout."""
    from app.graph import connection

    with patch.object(connection, "FalkorDB") as fake:
        connection.FalkorDBManager.__new__(connection.FalkorDBManager)
        manager = connection.FalkorDBManager()
        manager._client = None
        manager.get_client()

    kwargs = fake.call_args.kwargs
    assert kwargs["socket_timeout"] >= 60, "a fallback write can be large"
    assert kwargs["socket_connect_timeout"] <= 30, "a bad host should fail fast"
    assert kwargs["socket_keepalive"] is True
    assert kwargs["retry"] is not None, "a transient timeout must be retried"
    assert kwargs["health_check_interval"] > 0


def test_a_stale_connection_can_be_discarded_and_rebuilt():
    from app.graph.connection import graph_manager

    first = graph_manager.get_client()
    graph_manager.reset_client()
    second = graph_manager.get_client()

    assert second is not first, "reset must not hand back the dead connection"


def test_resetting_when_nothing_is_open_is_harmless():
    from app.graph.connection import graph_manager

    graph_manager.reset_client()  # primed by the previous test
    graph_manager.reset_client()  # a second reset must not raise

    assert graph_manager.check_health()


def test_a_chunk_write_retries_once_after_a_stale_connection():
    """The expensive work is the model call; losing it to a stale socket is not recoverable."""
    from app.services import file_describer

    dead = MagicMock()
    dead.query.side_effect = ConnectionError("connection already closed")

    alive = MagicMock()
    alive.query.return_value.result_set = [[2]]

    manager = MagicMock()
    manager.get_or_create_graph.return_value = alive

    with patch.object(file_describer, "graph_manager", manager):
        written = file_describer._write_chunk(dead, [{"id": "a"}, {"id": "b"}])

    assert written == 2, "the retry must return the rows it actually wrote"
    manager.reset_client.assert_called_once(), "a dead client must be discarded"
    assert dead.query.call_count == 1
    alive.query.assert_called_once()


def test_a_chunk_write_does_not_retry_a_query_error():
    """A bad query must surface, not be retried into a second identical failure."""
    from app.services import file_describer

    graph = MagicMock()
    graph.query.side_effect = ValueError("invalid query")

    manager = MagicMock()
    with patch.object(file_describer, "graph_manager", manager):
        with pytest.raises(ValueError):
            file_describer._write_chunk(graph, [{"id": "a"}])

    manager.reset_client.assert_not_called()


def test_a_chunk_write_sums_every_row_it_updated():
    from app.services import file_describer

    graph = MagicMock()
    graph.query.return_value.result_set = [[1], [1], [], [1]]

    with patch.object(file_describer, "graph_manager", MagicMock()):
        assert file_describer._write_chunk(graph, [{"id": "a"}]) == 3