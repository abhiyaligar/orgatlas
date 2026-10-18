"""Which graph holds a repository's code, and how to find it from a caller.

Both the REST routes and the MCP tools need this. It started life as two
helpers inside the routes module, and the MCP handlers grew their own copies by
not growing any -- so ``describe_file`` returned "no ingested history" for a
file the REST route described perfectly. Seven tools were quietly answering
from the organisation graph, where no File or Commit node exists.

Keeping one implementation is the point of this module. A caller that holds a
repository id or a file id can name the graph without asking the caller to pass
one, because both already contain it.

Both helpers raise rather than guessing. A silent fallback to the organisation
graph returns an empty result instead of a failure, which is the specific
mistake this module exists to prevent.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.graph.connection import org_graph_name, repository_graph_name
from app.core.errors import GraphNotFoundError

logger = logging.getLogger(__name__)


class UnknownRepository(Exception):
    """No ingested repository carries this id."""

    def __init__(self, repository_id: str):
        self.repository_id = repository_id
        super().__init__(
            f"Repository '{repository_id}' is not in the knowledge graph. "
            "Ingest it first via POST /api/repos/ingest."
        )


class InvalidFileId(Exception):
    """A file id that cannot name a graph, because it has no repository in it."""

    def __init__(self, file_id: str):
        self.file_id = file_id
        super().__init__(
            f"file_id '{file_id}' is not a node id. Expected "
            "'{repository_id}::{path}', e.g. repo_name::src/main.rs."
        )


def repository_graph(repository_id: str) -> str:
    """The graph holding this repository's code.

    Tries ``code_{repository_id}`` first, then the organisation graph. The
    fallback exists for repositories ingested before the split, when everything
    lived in one graph; an installation that has never split behaves correctly
    without a migration.
    """
    from app.graph.gateway import graph_gateway

    org = org_graph_name()
    for candidate in (repository_graph_name(repository_id), org):
        try:
            if graph_gateway.repository_exists(repository_id, graph_name=candidate):
                return candidate
        except GraphNotFoundError:
            # No graph for this repository yet. That is the expected answer for
            # anything not ingested, not a fault.
            continue

    raise UnknownRepository(repository_id)


def graph_for_file(file_id: str) -> str:
    """The graph holding a file, derived from the file's own id.

    A file id is ``{repository_id}::{path}``, so a caller holding one already
    holds the repository id. The graph is derived rather than verified here:
    asking whether the file exists would double the round trips on every file
    lookup, and an unknown file resolves to an empty result from the query
    itself, which is reported honestly by the caller.
    """
    if "::" not in file_id:
        raise InvalidFileId(file_id)
    return repository_graph_name(file_id.split("::", 1)[0])


def find_commit_graph(commit_id: str) -> Optional[str]:
    """Which repository graph holds a commit, if any.

    A commit id names no repository, and a commit cannot be found without
    knowing where to look, so the graphs this instance created are searched in
    turn. Bounded by the number of ingested repositories, not by the data.
    """
    from app.graph.connection import graph_manager
    from app.graph.gateway import graph_gateway

    for name in graph_manager.list_repository_graphs():
        try:
            if graph_gateway.get_commit_detail(commit_id, graph_name=name):
                return name
        except Exception:
            logger.error("Failed to search graph '%s' for commit", name, exc_info=True)
    return None