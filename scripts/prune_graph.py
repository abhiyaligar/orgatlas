#!/usr/bin/env python
"""Remove File nodes that the current repository filters exclude.

The graph still holds files ingested before the include/exclude filters were
enforced, so forensics queries return paths that a fresh scan would never
produce. This removes exactly the nodes the scanner would not have created.

Design notes:

* Dry-run is the default. Deletion requires both ``--apply`` and ``--yes``.
* Paths are read with keyset pagination instead of a single query, because
  FalkorDB caps a result set at 10,000 rows and the graph holds more files
  than that.
* The keep/delete decision uses the *same* :class:`FileFilter` the scanner
  uses, so the pruned set cannot drift from what a fresh scan would ingest.
* Deletes are batched by node id and run as ``DETACH DELETE``, so a stale
  MODIFIES edge is removed with its file rather than left dangling.

Usage:
    python scripts/prune_graph.py
    python scripts/prune_graph.py --apply --yes
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.graph.connection import graph_manager  # noqa: E402
from app.ingestion.repo_scanner import (  # noqa: E402
    FileFilter,
    load_repository_config,
)

PAGE_SIZE = 1000
DELETE_BATCH = 500

READ_PATHS = """
MATCH (f:File)
WHERE f.path > $after
RETURN f.path AS path, f.id AS id, f.repository_id AS repository_id
ORDER BY f.path
LIMIT $limit
"""

DELETE_FILES = """
UNWIND $ids AS id
MATCH (f:File {id: id})
DETACH DELETE f
RETURN count(*) AS deleted
"""


def iter_files(graph):
    """Yield (path, id, repository_id) for every File node, in pages.

    Keyset pagination on ``path`` keeps each query far below the 10,000 row
    cap and avoids the cost of a growing OFFSET.
    """
    after = ""
    while True:
        result = graph.query(READ_PATHS, {"after": after, "limit": PAGE_SIZE})
        rows = result.result_set
        if not rows:
            return
        for path, node_id, repository_id in rows:
            yield path or "", node_id, repository_id or ""
        after = rows[-1][0]
        if len(rows) < PAGE_SIZE:
            return


def build_filters():
    """Resolve include/exclude filters per repository from data/repos.json."""
    manifest_path = REPO_ROOT / "data" / "repos.json"
    if not manifest_path.is_file():
        return {}

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filters = {}
    for entry in manifest.get("repositories", []):
        url = entry.get("url")
        if not url:
            continue
        if not entry.get("include_globs") and not entry.get("exclude_paths"):
            continue
        filters[url] = FileFilter.from_config(entry)
    return filters


def repository_id_for(url: str) -> str:
    """Mirror the id scheme used at ingest time."""
    from app.ingestion.seed_repo import repository_id_for as build_id

    return build_id(url)


def collect() -> dict:
    """Classify every File node as keep or delete without mutating anything."""
    graph = graph_manager.get_or_create_graph()
    filters = build_filters()

    kept, deleted = [], []
    unfiltered = 0

    for path, node_id, repository_id in iter_files(graph):
        if not path:
            deleted.append((node_id, path, repository_id, "empty path"))
            continue

        file_filter = filters.get(_url_for(filters, repository_id))
        if file_filter is None:
            unfiltered += 1
            kept.append((node_id, path, repository_id, "no configured filters"))
            continue

        if file_filter.keep(path):
            kept.append((node_id, path, repository_id, "matches filters"))
        else:
            deleted.append((node_id, path, repository_id, "excluded by filters"))

    return {
        "kept": kept,
        "deleted": deleted,
        "unfiltered": unfiltered,
        "filters": filters,
    }


def _url_for(filters: dict, repository_id: str) -> str:
    """Map a graph repository_id back to its manifest url."""
    if not repository_id:
        return ""
    for url in filters:
        if repository_id_for(url) == repository_id:
            return url
    return ""


def delete_files(graph, ids: list) -> int:
    total = 0
    for start in range(0, len(ids), DELETE_BATCH):
        chunk = ids[start:start + DELETE_BATCH]
        result = graph.query(DELETE_FILES, {"ids": chunk})
        for row in result.result_set:
            total += row[0] if row else 0
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove File nodes excluded by the current repository filters."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete. Without this flag the script only reports.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required together with --apply to skip the confirmation prompt.",
    )
    parser.add_argument(
        "--limit-report",
        type=int,
        default=15,
        help="How many example paths to print per side.",
    )
    args = parser.parse_args()

    print("Classifying File nodes against data/repos.json filters...")
    result = collect()

    kept = result["kept"]
    deleted = result["deleted"]

    print(f"  total File nodes : {len(kept) + len(deleted)}")
    print(f"  keep             : {len(kept)}")
    print(f"  delete           : {len(deleted)}")
    if result["unfiltered"]:
        print(
            f"  note             : {result['unfiltered']} file(s) belong to a "
            "repository with no configured filters and were kept"
        )

    if not deleted:
        print("\nNothing to prune.")
        return 0

    print(f"\nExamples that would be deleted:")
    for node_id, path, _repo, reason in deleted[: args.limit_report]:
        print(f"  - {path}  ({reason})")
    if len(deleted) > args.limit_report:
        print(f"  ... and {len(deleted) - args.limit_report} more")

    if not args.apply:
        print("\nDry run only. Re-run with --apply --yes to delete these nodes.")
        return 0

    if not args.yes:
        answer = input(f"\nDelete {len(deleted)} File nodes? Type 'yes' to confirm: ")
        if answer.strip().lower() != "yes":
            print("Aborted.")
            return 1

    print("\nDeleting...")
    graph = graph_manager.get_or_create_graph()
    total = delete_files(graph, [node_id for node_id, _p, _r, _x in deleted])
    print(f"  deleted {total} File node(s)")

    remaining = sum(1 for _ in iter_files(graph))
    print(f"  File nodes remaining: {remaining}")

    if total != len(deleted):
        print(
            f"  WARNING: expected to delete {len(deleted)} but removed {total}; "
            "re-run to reconcile.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())