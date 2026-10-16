"""Writes a sandbox scan payload into the FalkorDB property graph.

Writes are issued as ``UNWIND``-batched parameterised queries rather than one
statement per record. Ingesting 600 commits produces thousands of nodes and
edges; sending them individually means thousands of network round-trips to the
graph host, which dominates wall-clock time. Batching turns that into a couple
of dozen queries.

Every statement is idempotent (``MERGE``), so a re-ingest fills gaps left by an
interrupted run instead of duplicating history.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings
from app.graph.connection import graph_manager
from app.ingestion.git_history_parser import is_automation_author
from app.ingestion.identity_resolver import external_identity_id
from app.ingestion.sandbox_client import ScanRequest, run_scan

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

UPSERT_REPOSITORY = """
UNWIND $rows AS row
MERGE (r:Repository {id: row.id})
SET r.name = row.name,
    r.url = row.url,
    r.source = row.source,
    r.ingested_at = row.ingested_at,
    r.declared_in = row.declared_in
"""

UPSERT_EXTERNAL_IDENTITY = """
UNWIND $rows AS row
MERGE (i:ExternalIdentity {id: row.id})
SET i.username = row.username,
    i.email = row.email,
    i.provider = row.provider
"""

LINK_PERSON_IDENTITY = """
UNWIND $rows AS row
MATCH (p:Person {id: row.person_id})
MERGE (i:ExternalIdentity {id: row.identity_id})
MERGE (p)-[:HAS_IDENTITY]->(i)
"""

UPSERT_MODULE = """
UNWIND $rows AS row
MERGE (m:Module {id: row.id})
SET m.path = row.path,
    m.name = row.name,
    m.repository_id = row.repository_id
"""

UPSERT_COMMIT = """
UNWIND $rows AS row
MERGE (c:Commit {id: row.id})
SET c.message = row.message,
    c.author_name = row.author_name,
    c.authored_at = row.authored_at,
    c.is_merge = row.is_merge,
    c.pr_number = row.pr_number,
    c.repository_id = row.repository_id
"""

UPSERT_FILE = """
UNWIND $rows AS row
MERGE (f:File {id: row.id})
SET f.path = row.path,
    f.name = row.name,
    f.language = row.language,
    f.is_test = row.is_test,
    f.repository_id = row.repository_id
"""

UPSERT_CODEOWNER_PATH = """
UNWIND $rows AS row
MERGE (p:Path {id: row.id})
SET p.path = row.path
"""

LINK_REPO_COMMIT = """
UNWIND $rows AS row
MATCH (r:Repository {id: row.repository_id})
MATCH (c:Commit {id: row.commit_id})
MERGE (r)-[:HAS_COMMIT]->(c)
"""

LINK_AUTHORED = """
UNWIND $rows AS row
MATCH (a {id: row.author_id})
MATCH (c:Commit {id: row.commit_id})
MERGE (a)-[:AUTHORED]->(c)
"""

LINK_MODULE_FILE = """
UNWIND $rows AS row
MATCH (m:Module {id: row.module_id})
MATCH (f:File {id: row.file_id})
MERGE (m)-[:CONTAINS]->(f)
"""

LINK_MODIFIES = """
UNWIND $rows AS row
MATCH (c:Commit {id: row.commit_id})
MATCH (f:File {id: row.file_id})
MERGE (c)-[:MODIFIES]->(f)
"""

LINK_DEPENDS_ON_REPO = """
UNWIND $rows AS row
MATCH (r:Repository {id: row.repository_id})
MATCH (d:Repository {id: row.dependency_id})
MERGE (r)-[:DEPENDS_ON_REPO]->(d)
"""

LINK_CODEOWNERS_PATH = """
UNWIND $rows AS row
MATCH (r:Repository {id: row.repository_id})
MATCH (p:Path {id: row.path_id})
MERGE (r)-[:CODEOWNERS_PATH]->(p)
"""


def repository_id_for(url: str) -> str:
    """Stable id for a repository, derived from its slug."""
    trimmed = url.strip().rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[: -len(".git")]
    parts = [part for part in trimmed.replace(":", "/").split("/") if part]
    owner = parts[-2] if len(parts) >= 2 else "unknown"
    name = parts[-1] if parts else "unknown"
    slug = "".join(
        char if char.isalnum() else "_" for char in f"{owner}_{name}".lower()
    )
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"repo_{slug.strip('_')}"


def batched(rows: list[dict[str, Any]], size: int = BATCH_SIZE) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def seeded_people_by_email() -> dict[str, str]:
    """Map seeded employee email to Person id, for author attribution."""
    try:
        graph = graph_manager.get_graph()
        rows = graph.query("MATCH (p:Person) RETURN p.email AS email, p.id AS id").result_set
    except Exception as exc:
        logger.warning("Unable to read seeded people for identity resolution: %s", exc)
        return {}

    mapping: dict[str, str] = {}
    for row in rows:
        email, person_id = row[0], row[1]
        if email:
            mapping[str(email).strip().lower()] = str(person_id)
    return mapping


def build_batches(payload: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Turn a scan payload into ordered ``(query, rows)`` batches.

    Commits are emitted before files so that an interrupted run still leaves the
    history that answers "who changed this" intact.
    """
    url = payload["repository_url"]
    repository_id = repository_id_for(url)
    repo_name = url.rstrip("/").split("/")[-1]
    ingested_at = payload.get("scanned_at") or ""

    repositories: list[dict[str, Any]] = [
        {
            "id": repository_id,
            "name": repo_name,
            "url": url,
            "source": "github",
            "ingested_at": ingested_at,
            "declared_in": "",
        }
    ]

    people = seeded_people_by_email()
    author_to_identity: dict[str, str] = {}
    external_rows: list[dict[str, Any]] = []

    for author in payload.get("authors", []):
        name = (author.get("name") or "").strip()
        email = (author.get("email") or "").strip()
        if not email or is_automation_author(email, name):
            continue

        person_id = people.get(email.lower())
        if person_id:
            author_to_identity[email.lower()] = person_id
            continue

        identity_id = external_identity_id(email)
        author_to_identity[email.lower()] = identity_id
        external_rows.append(
            {
                "id": identity_id,
                "username": name or email,
                "email": email,
                "provider": "github",
            }
        )

    dependency_rows = [
        {
            "id": dependency["repository_id"],
            "name": dependency["slug"],
            "url": dependency["url"],
            "source": "github",
            "ingested_at": ingested_at,
            "declared_in": dependency.get("declared_in") or "",
        }
        for dependency in payload.get("dependencies", [])
    ]

    module_rows: list[dict[str, Any]] = []
    module_seen: set[str] = set()
    file_rows: list[dict[str, Any]] = []
    module_file_rows: list[dict[str, Any]] = []

    for record in payload.get("files", []):
        path = record["path"]
        file_id = f"{repository_id}::{path}"
        file_rows.append(
            {
                "id": file_id,
                "path": path,
                "name": path.rsplit("/", 1)[-1],
                "language": record.get("language") or "Other",
                "is_test": bool(record.get("is_test")),
                "repository_id": repository_id,
            }
        )

        module_path = record.get("module")
        if module_path:
            module_id = f"{repository_id}__{module_path.replace('/', '__')}"
            if module_id not in module_seen:
                module_seen.add(module_id)
                module_rows.append(
                    {
                        "id": module_id,
                        "path": module_path,
                        "name": module_path.rsplit("/", 1)[-1],
                        "repository_id": repository_id,
                    }
                )
            module_file_rows.append({"module_id": module_id, "file_id": file_id})

    commit_rows: list[dict[str, Any]] = []
    repo_commit_rows: list[dict[str, Any]] = []
    authored_rows: list[dict[str, Any]] = []
    modifies_rows: list[dict[str, Any]] = []

    for commit in payload.get("commits", []):
        commit_rows.append(
            {
                "id": commit["sha"],
                "message": commit.get("subject") or "",
                "author_name": commit.get("author_name") or "",
                "authored_at": commit.get("authored_at") or "",
                "is_merge": bool(commit.get("is_merge")),
                "pr_number": commit.get("pr_number"),
                "repository_id": repository_id,
            }
        )
        repo_commit_rows.append({"repository_id": repository_id, "commit_id": commit["sha"]})

        author_id = author_to_identity.get((commit.get("author_email") or "").lower())
        if author_id:
            authored_rows.append({"author_id": author_id, "commit_id": commit["sha"]})

        for path in commit.get("files", []):
            modifies_rows.append(
                {"commit_id": commit["sha"], "file_id": f"{repository_id}::{path}"}
            )

    codeowner_rows = [
        {"id": owner_path, "path": owner_path}
        for owner_path in payload.get("codeowners_paths", [])
    ]
    codeowner_link_rows = [
        {"repository_id": repository_id, "path_id": owner_path}
        for owner_path in payload.get("codeowners_paths", [])
    ]
    dependency_link_rows = [
        {"repository_id": repository_id, "dependency_id": dependency["repository_id"]}
        for dependency in payload.get("dependencies", [])
    ]

    plan: list[tuple[str, list[dict[str, Any]]]] = [
        (UPSERT_REPOSITORY, repositories),
        (UPSERT_REPOSITORY, dependency_rows),
        (UPSERT_EXTERNAL_IDENTITY, external_rows),
        (UPSERT_MODULE, module_rows),
        (UPSERT_COMMIT, commit_rows),
        (UPSERT_FILE, file_rows),
        (UPSERT_CODEOWNER_PATH, codeowner_rows),
        (LINK_REPO_COMMIT, repo_commit_rows),
        (LINK_AUTHORED, authored_rows),
        (LINK_MODULE_FILE, module_file_rows),
        (LINK_MODIFIES, modifies_rows),
        (LINK_DEPENDS_ON_REPO, dependency_link_rows),
        (LINK_CODEOWNERS_PATH, codeowner_link_rows),
    ]
    return [(query, rows) for query, rows in plan if rows]


def write_payload(payload: dict[str, Any], on_stage=None) -> dict[str, Any]:
    """Apply a scan payload to the graph using batched writes."""

    def stage(message: str) -> None:
        logger.info("[ingest] %s", message)
        if on_stage is not None:
            on_stage(message)

    plan = build_batches(payload)
    graph = graph_manager.get_or_create_graph()

    executed = 0
    rows_written = 0
    for index, (query, rows) in enumerate(plan, start=1):
        label = query.strip().splitlines()[1].strip() if len(query.strip().splitlines()) > 1 else "query"
        for batch in batched(rows):
            graph.query(query, {"rows": batch})
            rows_written += len(batch)
            executed += 1
        stage(f"batch {index}/{len(plan)} {label}: {len(rows)} rows")

    stage(f"complete: {executed} queries, {rows_written} rows")

    return {
        "queries_executed": executed,
        "rows_written": rows_written,
        "commits": len(payload.get("commits", [])),
        "files": len(payload.get("files", [])),
        "dependencies": len(payload.get("dependencies", [])),
    }


def cache_payload(payload: dict[str, Any]) -> Path | None:
    """Persist the extracted payload locally so a re-ingest skips re-cloning."""
    directory = settings.INGEST_CACHE_DIR
    if not directory:
        return None

    cache_dir = Path(directory)
    if not cache_dir.is_absolute():
        cache_dir = Path(__file__).resolve().parents[3] / cache_dir

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{repository_id_for(payload['repository_url'])}.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target
    except OSError as exc:
        logger.warning("Unable to cache payload: %s", exc)
        return None


def ingest_repository(url: str, on_stage=None) -> dict[str, Any]:
    """Run the full pipeline: sandbox scan, then batched graph write."""
    request = ScanRequest(
        repository_url=url,
        commit_depth=int(settings.INGEST_COMMIT_DEPTH or 0),
    )
    result = run_scan(request, on_stage=on_stage)
    cache_payload(result.payload)
    summary = write_payload(result.payload, on_stage=on_stage)
    summary["sandbox_id"] = result.sandbox_id
    return summary