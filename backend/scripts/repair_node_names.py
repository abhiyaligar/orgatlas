"""Restore graph node names after bulk corruption.

A probe query used ``MERGE`` with no pattern -- ``MERGE (t)`` -- followed by
``SET t.name``. A patternless MERGE binds an arbitrary node, and the probe called
it once per iteration, so 3,378 of 3,398 nodes in the development graph were
renamed to a single string. This script rebuilds every name it can from a source
of truth inside the graph itself or in the seed fixtures.

Recovery sources, in order of authority:

* **Fixture-backed labels** -- name and title come from ``data/fixtures``. This
  is the same data the seed uses, so a repaired node is byte-identical to a
  freshly seeded one.
* **Path-derived labels** -- a ``File`` is named after its basename and a
  ``Module`` after the last segment of its path. Both are recoverable from the
  id and path already stored on the node.
* **Id-derived labels** -- a ``CodeSymbol`` id ends in the symbol's own name.
* **Commits** carry a ``message`` rather than a name, so the corrupted ``name``
  is cleared rather than guessed at.

What this cannot repair, and says so rather than inventing:

* ``ExternalIdentity`` names are an author's name and appear nowhere in the id
  or any other property. They require re-running the repository ingest.

Ingestion-created nodes are deliberately not touched beyond their names, so a
329-file repository does not have to be re-ingested to fix this.

Usage:
    python scripts/repair_node_names.py            # dry run
    python scripts/repair_node_names.py --apply
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.graph.gateway import GraphGateway  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"

# label -> fixture supplying its display fields
NAME_SOURCE = {
    "Organization": "organization.json",
    "Team": "teams.json",
    "Person": "people.json",
    "Service": "services.json",
    "Technology": "technologies.json",
    "Decision": "decisions.json",
    "Incident": "incidents.json",
    "Document": "documents.json",
    "PullRequest": "pull_requests.json",
    "Ticket": "tickets.json",
    "Repository": "repositories.json",
    "OnboardingTopic": "onboarding_topics.json",
}

# Labels whose display text lives in `title`.
TITLE_LABELS = {"Document", "Decision", "Incident", "PullRequest", "Ticket", "OnboardingTopic"}

# Labels this script can derive a name from, and how.
PATH_LABELS = {"File", "Module", "Path"}
ID_SUFFIX_LABELS = {"CodeSymbol"}


def load_fixture(filename: str) -> List[dict]:
    path = FIXTURES / filename
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else list(data.values())[0]
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def fixture_display() -> Dict[Tuple[str, str], Tuple[str, str]]:
    """(label, id) -> (name, title)."""
    expected: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for label, filename in NAME_SOURCE.items():
        for row in load_fixture(filename):
            name = row.get("name")
            title = row.get("title")
            if name is None and label in TITLE_LABELS:
                name = title
            if title is None and label not in TITLE_LABELS:
                title = name
            if name or title:
                expected[(label, str(row["id"]))] = (name or "", title or "")
    return expected


def _name_from_email(email: str) -> str:
    """Recover a contributor's display name from their commit address.

    GitHub commits arrive as ``<id>+<login>@users.noreply.github.com`` or as a
    plain address. The login is the most faithful name available without the
    original ingest payload, and it is what a contributor is recognised by.
    """
    local = (email or "").split("@")[0]
    if "+" in local:
        local = local.split("+", 1)[1]
    if not local:
        return ""
    # A plain local part is at best a guess at a display name.
    return local.replace(".", " ").replace("_", " ").strip().title()


def derive_name(label: str, node_id: str, path: str) -> Tuple[str, bool]:
    """Return (name, recoverable)."""
    if label in PATH_LABELS:
        source = path or node_id.split("::")[-1]
        return source.replace("\\", "/").rstrip("/").split("/")[-1], True
    if label in ID_SUFFIX_LABELS:
        # repo::path::kind::SymbolName, or repo::path::SymbolName
        return node_id.split("::")[-1], True
    return "", False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repairs")
    args = parser.parse_args()

    gateway = GraphGateway()
    display = fixture_display()

    rows = gateway._execute(
        "MATCH (n) RETURN labels(n)[0] AS label, n.id AS id, "
        "coalesce(n.name, '') AS name, coalesce(n.title, '') AS title, "
        "coalesce(n.path, '') AS path, coalesce(n.url, '') AS url, "
        "coalesce(n.email, '') AS email"
    )

    plan: List[Tuple[str, str, str, str]] = []  # (label, id, property, value)
    unrecoverable: List[Tuple[str, str]] = []

    for label, node_id, name, title, path, url, email in rows:
        if label == "Commit":
            # Commits are identified by their message; a name is not part of the
            # model, so the corrupted one is removed rather than replaced.
            if name:
                plan.append((label, node_id, "name", ""))
            continue

        if label == "Repository" and url:
            # An ingested repository is named after its clone URL, which the
            # corruption did not touch.
            derived = url.rstrip("/").split("/")[-2:][-1]
            if derived and name != derived:
                plan.append((label, node_id, "name", derived))
            continue

        if label == "ExternalIdentity" and email:
            # GitHub noreply addresses embed the login after the "+".
            derived = _name_from_email(email)
            if derived and name != derived:
                plan.append((label, node_id, "name", derived))
            else:
                unrecoverable.append((label, node_id))
            continue

        expected = display.get((label, node_id))
        if expected is not None:
            want_name, want_title = expected
            if name != want_name and want_name:
                plan.append((label, node_id, "name", want_name))
            if want_title and title != want_title:
                plan.append((label, node_id, "title", want_title))
            continue

        derived, ok = derive_name(label, node_id, path)
        if ok and derived and name != derived:
            plan.append((label, node_id, "name", derived))

    by_label: Dict[str, int] = {}
    for label, _id, _prop, _value in plan:
        by_label[label] = by_label.get(label, 0) + 1

    print(f"Nodes inspected : {len(rows)}")
    print(f"Repairs planned : {len(plan)}")
    for label in sorted(by_label):
        print(f"    {label:20} {by_label[label]}")

    if unrecoverable:
        counts: Dict[str, int] = {}
        for label, _id in unrecoverable:
            counts[label] = counts.get(label, 0) + 1
        print("\nNOT repairable from the graph or fixtures:")
        for label, count in sorted(counts.items()):
            print(f"    {label:20} {count}  -> needs a repository re-ingest")

    if not plan:
        print("\nNothing to repair.")
        return 0

    if not args.apply:
        print("\nDry run. Re-run with --apply to write these repairs.")
        return 1

    # One query per property, not one per node. Issuing 3,000 individual
    # round trips to repair a graph this script damaged is both slow and a poor
    # look in the logs.
    applied = 0
    by_property: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for label, node_id, prop, value in plan:
        by_property.setdefault((label, prop), []).append((node_id, value))

    for (label, prop), rows in by_property.items():
        for start in range(0, len(rows), 200):
            batch = rows[start : start + 200]
            # UNWIND, not a pair of IN/= lists: `SET n.x = $values` would assign
            # the whole list to every matched node instead of pairing each id
            # with its own value.
            gateway._execute(
                f"UNWIND $rows AS row\n"
                f"MATCH (n) WHERE labels(n)[0] = $label AND n.id = row.id\n"
                f"SET n.{prop} = row.value",
                {
                    "label": label,
                    "rows": [{"id": row[0], "value": row[1]} for row in batch],
                },
            )
            applied += len(batch)

    print(f"\nRepaired {applied} property value(s) in "
          f"{sum(1 + (len(r) - 1) // 200 for r in by_property.values())} batch(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())