"""Move a repository's code out of the organisation graph and into its own.

Repository graphs arrived after the EstateX ingest had already written its 215
files, 347 symbols and 163 commits into the shared graph. This moves the code
nodes and the relationships between them, and leaves organisation data where it
belongs: teams, people, services, decisions, documents and Slack history.

    python -m scripts.split_repository_graph repo_abhiyaligar_estatex

The move is idempotent. Running it twice moves nothing the second time, because
the nodes are found by id and a node already present in the target is skipped.

What is deliberately not moved: anything whose label is not code. A Repository
node describes the repository itself and stays in the org graph, because that is
where a question about the repository as a whole resolves it.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.connection import (  # noqa: E402
    graph_manager,
    org_graph_name,
    repository_graph_name,
)
from app.graph.gateway import graph_gateway  # noqa: E402

logger = logging.getLogger("split_repository_graph")

# Labels that describe code and belong in a repository's own graph.
#
# Repository is in the list because it is the node a code question resolves
# to. Left behind in the org graph, "what is the tech stack of EstateX" would
# resolve there and then look for files that had moved, and answer "insufficient
# evidence" about a repository it had just found.
CODE_LABELS = (
    "Repository",
    "File",
    "Commit",
    "CodeSymbol",
    "Module",
    "Path",
    "ExternalIdentity",
)

# Relationships that only ever connect code to code.
CODE_EDGES = (
    "HAS_COMMIT",
    "DECLARES",
    "MODIFIES",
    "CONTAINS",
    "AUTHORED",
)


def _rows(graph, query, params):
    return graph.query(query, params or {}).result_set



def _nodes_for(source, label: str, repository_id: str):
    """Find a repository's nodes of one label, however they are identified.

    Almost everything carries a repository_id property. An ExternalIdentity
    does not: it is shared across repositories and is reached through the
    commits it authored, so it is looked up by relationship instead.
    """
    if label == "ExternalIdentity":
        return _rows(
            source,
            """MATCH (n:ExternalIdentity)-[:AUTHORED]->(c:Commit {repository_id: $repository_id})
               RETURN DISTINCT n.id, properties(n)""",
            {"repository_id": repository_id},
        )
    if label == "Repository":
        return _rows(
            source,
            "MATCH (n:Repository {id: $repository_id}) RETURN n.id, properties(n)",
            {"repository_id": repository_id},
        )
    return _rows(
        source,
        f"MATCH (n:{label}) WHERE n.repository_id = $repository_id RETURN n.id, properties(n)",
        {"repository_id": repository_id},
    )

def move_repository(repository_id: str, dry_run: bool = False) -> dict:
    """Move one repository's code into its own graph."""
    target = repository_graph_name(repository_id)
    org = org_graph_name()
    source = graph_manager.get_graph(org)
    destination = graph_manager.get_or_create_graph(target)

    counts: dict[str, int] = {}

    for label in CODE_LABELS:
        nodes = _nodes_for(source, label, repository_id)
        if not nodes:
            counts[label] = 0
            continue
        for node_id, properties in nodes:
            if _rows(destination, "MATCH (n {id: $id}) RETURN count(n)", {"id": node_id})[0][0]:
                continue  # already moved by an earlier run
            if dry_run:
                counts[label] = counts.get(label, 0) + 1
                continue
            destination.query(
                f"MERGE (n:{label} {{id: $id}}) SET n += $properties",
                {"id": node_id, "properties": _stringify(properties)},
            )
            counts[label] = counts.get(label, 0) + 1
        if not dry_run and counts.get(label):
            logger.info("moved %d %s node(s)", counts[label], label)

    moved_edges = 0
    edge_counts: dict[str, int] = {}
    for edge in CODE_EDGES:
        moved_for_edge = 0
        edges = _rows(
            source,
            f"""MATCH (a)-[r:{edge}]->(b)
                WHERE any(l IN labels(a) WHERE l IN $labels)
                  AND any(l IN labels(b) WHERE l IN $labels)
                  AND ($repository_id IN [a.repository_id, b.repository_id, a.id, b.id])
                RETURN a.id, type(r), properties(r), b.id""",
            {"repository_id": repository_id, "labels": list(CODE_LABELS)},
        )
        for source_id, edge_type, properties, target_id in edges:
            if _rows(
                destination,
                """MATCH (a {id: $a})-[r]->(b {id: $b})
                   WHERE type(r) = $type RETURN count(r)""",
                {"a": source_id, "b": target_id, "type": edge_type},
            )[0][0]:
                continue
            if dry_run:
                moved_for_edge += 1
                continue
            destination.query(
                f"""MATCH (a {{id: $a}}), (b {{id: $b}})
                    MERGE (a)-[r:{edge_type}]->(b)
                    SET r += $properties""",
                {
                    "a": source_id,
                    "b": target_id,
                    "properties": _stringify(properties or {}),
                },
            )
            moved_for_edge += 1
        edge_counts[edge] = moved_for_edge
        moved_edges += moved_for_edge
        logger.info("%s: %d edge(s) moved", edge, moved_for_edge)

    # Remove from the organisation graph last, so a failure part way through
    # leaves the data readable rather than half moved.
    if not dry_run and (sum(counts.values()) or moved_edges):
        for label in CODE_LABELS:
            source.query(
                f"MATCH (n:{label}) WHERE n.repository_id = $repository_id DETACH DELETE n",
                {"repository_id": repository_id},
            )
        # A Repository is identified by its own id rather than by a
        # repository_id property, so the loop above cannot reach it. Its copy
        # has to go too: left behind, "what is the tech stack" resolves the
        # stale one in the org graph and then looks for files that have moved.
        source.query(
            "MATCH (n:Repository {id: $repository_id}) DETACH DELETE n",
            {"repository_id": repository_id},
        )

    summary = {
        "repository_id": repository_id,
        "graph": target,
        "nodes": counts,
        "edges": moved_edges,
        "edges_by_type": edge_counts,
    }
    logger.info("%s", summary)
    return summary


def _stringify(properties: dict) -> dict:
    """FalkorDB will not accept a list or a map as a property value."""
    import json

    out = {}
    for key, value in (properties or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = json.dumps(value)
    return out


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not argv:
        print(__doc__)
        return 1
    dry_run = "--dry-run" in argv
    ids = [arg for arg in argv if not arg.startswith("--")]
    for repository_id in ids:
        move_repository(repository_id, dry_run=dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))