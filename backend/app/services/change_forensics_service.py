"""Change forensics over ingested repository history.

Answers questions a developer hits mid-task:

* which files are most volatile in an area of the code
* who has touched this file, and when
* what changed around the time something broke
* which files tend to change together as a unit
* what else across repositories is affected by a change here

This service only ever reads. It produces evidence and suggested next steps; it
does not modify the repository or the graph.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import Citation, EvidenceSubgraph, GraphEdge, GraphNode
from app.evidence.formatter import build_graph_edge, build_graph_node, render_path, safe_str
from app.evidence.service import EvidenceService
from app.graph.gateway import GraphGateway, graph_gateway
from app.services.onboarding_service import parse_stored_list

logger = logging.getLogger(__name__)

# docs_source values produced by extracting what the file's authors wrote.
AUTHORED_SOURCES = frozenset({"module", "item", "declaration", "heading", "key"})


def _parse_usage(value: Any) -> Dict[str, Any]:
    """Read the token-usage object FalkorDB stored as a JSON string."""
    if isinstance(value, dict):
        return value
    if not value or not str(value).strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def repository_id_for_path(path: str) -> str:
    """Derive the owning repository id from a node id of the form ``repo_x::path``."""
    if "::" not in path:
        return path
    return path.split("::", 1)[0]


class ChangeForensicsService:
    """Evidence-backed answers about change history in a repository."""

    def __init__(
        self,
        gateway: GraphGateway = graph_gateway,
        evidence: Optional[EvidenceService] = None,
    ) -> None:
        self.gateway = gateway
        self.evidence = evidence or EvidenceService()

    def file_timeline(self, file_id: str, limit: int = 50, graph_name: str = "") -> Optional[Dict[str, Any]]:
        """Who changed a file, when, and through which pull request."""
        history = self.gateway.get_file_history(file_id, limit=limit, graph_name=graph_name)
        if not history:
            logger.info("No history found for file %s", file_id)
            return None

        file_node = build_graph_node({"id": file_id, "name": file_id.split("::")[-1]}, label="File")
        if file_node is None:
            return None

        nodes: List[GraphNode] = [file_node]
        edges: List[GraphEdge] = []
        paths: List[str] = []
        seen_authors: Dict[str, GraphNode] = {}

        for entry in history:
            commit_node = build_graph_node(
                {
                    "id": entry["sha"],
                    "name": entry["message"][:60],
                    "authored_at": entry["authored_at"],
                    "pr_number": entry["pr_number"],
                },
                label="Commit",
            )
            if commit_node is None:
                continue
            nodes.append(commit_node)
            edges.append(
                build_graph_edge(
                    f"modifies_{commit_node.id}",
                    commit_node.id,
                    file_node.id,
                    "MODIFIES",
                )
            )

            author_id = entry.get("author_id") or ""
            if author_id and author_id not in seen_authors:
                author_node = build_graph_node(
                    {"id": author_id, "name": entry.get("author") or author_id},
                    label="ExternalIdentity",
                )
                if author_node is not None:
                    seen_authors[author_id] = author_node
                    nodes.append(author_node)
                    edges.append(
                        build_graph_edge(
                            f"authored_{author_id}_{commit_node.id}",
                            author_id,
                            commit_node.id,
                            "AUTHORED",
                        )
                    )
            if entry.get("author_id"):
                paths.append(
                    render_path(
                        seen_authors[entry["author_id"]].name
                        if entry["author_id"] in seen_authors
                        else entry.get("author", "unknown"),
                        "ExternalIdentity",
                        [("AUTHORED", commit_node.name, "Commit")],
                    )
                )

        contributors = self.gateway.get_path_contributors(
            repository_id_for_path(file_id), path_prefix=file_id.split("::")[-1], limit=25, graph_name=graph_name
        )

        citations = [
            Citation(
                source_id=entry["sha"],
                title=f"{entry['message'][:70]} ({entry['authored_at'][:10]})",
                type="commit",
                author=entry.get("author") or None,
                url=f"https://github.com/commit/{entry['sha']}" if entry.get("author_id") else None,
            )
            for entry in history[:20]
        ]

        return {
            "file_id": file_id,
            "path": file_id.split("::")[-1],
            "repository_id": repository_id_for_path(file_id),
            "change_count": len(history),
            "history": history,
            "contributors": contributors,
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths),
        }

    def churn_ranking(
        self,
        repository_id: str,
        path_prefix: str = "",
        limit: int = 25,
        graph_name: str = "",
    ) -> Dict[str, Any]:
        """Which files change most, so a newcomer knows where the risk is."""
        rows = self.gateway.get_file_churn(
            repository_id, path_prefix=path_prefix, limit=limit, graph_name=graph_name
        )
        return {
            "repository_id": repository_id,
            "path_prefix": path_prefix,
            "files": rows,
            "hotspots": [row for row in rows if not row.get("is_test")][:10],
        }

    def changes_since(
        self, repository_id: str, since: str, limit: int = 100,
        graph_name: str = ""
    ) -> Dict[str, Any]:
        """Files touched in a time window, for correlating with an incident."""
        rows = self.gateway.get_files_changed_since(repository_id, since=since, limit=limit, graph_name=graph_name)
        return {
            "repository_id": repository_id,
            "since": since,
            "files": rows,
            "file_count": len(rows),
        }

    def coupled_files(self, file_id: str, limit: int = 15, graph_name: str = "") -> Dict[str, Any]:
        """Files that historically change in the same commits as this one."""
        rows = self.gateway.get_change_coupling(file_id, limit=limit, graph_name=graph_name)
        return {
            "file_id": file_id,
            "path": file_id.split("::")[-1],
            "coupled": rows,
            "advice": (
                "These files change together. Read and change them as one unit, "
                "and expect a test to cover both."
                if rows
                else "No co-changing files were found within the ingested history."
            ),
        }

    def module_history(
        self,
        repository_id: str,
        path_prefix: str,
        limit: int = 50,
        graph_name: str = "",
    ) -> Dict[str, Any]:
        """Recent commits touching a module or directory."""
        commits = self.gateway.get_commits_for_path(
            repository_id, path_prefix=path_prefix, limit=limit, graph_name=graph_name
        )
        return {
            "repository_id": repository_id,
            "path_prefix": path_prefix,
            "commits": commits,
            "contributors": self.gateway.get_path_contributors(
                repository_id, path_prefix=path_prefix, limit=15, graph_name=graph_name
            ),
        }

    def investigation_brief(
        self,
        repository_id: str,
        path_prefix: str = "",
        file_id: Optional[str] = None,
        graph_name: str = "",
    ) -> Dict[str, Any]:
        """Assemble a starting brief for someone new to an area of the code.

        This is the "where do I start" entry point: volatile files, who owns
        the area, and what to read before editing.
        """
        churn = self.churn_ranking(repository_id, path_prefix=path_prefix, limit=20, graph_name=graph_name)
        contributors = self.gateway.get_path_contributors(
            repository_id, path_prefix=path_prefix or "", limit=10, graph_name=graph_name
        )
        dependencies = self.gateway.get_dependency_impact(
            repository_id, limit=25, graph_name=graph_name
        )

        brief: Dict[str, Any] = {
            "repository_id": repository_id,
            "path_prefix": path_prefix,
            "hotspots": churn["hotspots"],
            "contributors": contributors,
            "dependency_blast_radius": dependencies,
            "guidance": [],
        }

        guidance: List[str] = []
        if churn["hotspots"]:
            hottest = churn["hotspots"][0]
            guidance.append(
                f"Most-changed file in this area is '{hottest['path']}' "
                f"({hottest['changes']} changes). Expect it to be the highest-risk edit."
            )
        if contributors:
            people = ", ".join(
                f"{c['author']} ({c['commits']} commits)"
                for c in contributors[:3]
                if c.get("author")
            )
            guidance.append(f"Most experienced here: {people}. Review their prior changes first.")
        if dependencies:
            guidance.append(
                f"This repository declares {len(dependencies)} dependent repositories. "
                "Check them before changing a public interface."
            )
        if not guidance:
            guidance.append(
                "No ingested history matched this area. Ingest the repository before "
                "relying on forensics for it."
            )

        brief["guidance"] = guidance
        return brief
    def describe_file(self, file_id: str, graph_name: str = "") -> Optional[Dict[str, Any]]:
        """Describe a file from the documentation its authors wrote.

        The summary and symbols are read from the file's own source text at
        ingest time. This method reports what that text said and whether the
        file has since changed in ingested history, rather than regenerating a
        description and presenting it as current.
        """
        record = self.gateway.get_file_description(file_id, graph_name=graph_name)
        if record is None:
            return None

        symbols = parse_stored_list(record["symbols"])
        docs_at_sha = record["docs_at_sha"] or ""

        result: Dict[str, Any] = {
            "file_id": file_id,
            "path": record["path"],
            "name": record["name"],
            "language": record["language"],
            "is_test": bool(record["is_test"]),
            "repository_id": record["repository_id"],
            "summary": record["summary"],
            "symbols": symbols,
            "docs_source": record["docs_source"] or "none",
            "docs_at_sha": docs_at_sha,
            "stale": False,
            "changes_since_docs": 0,
            "recent_shas": [],
            "provenance": {
                "origin": "authored" if record["docs_source"] in AUTHORED_SOURCES else "model"
                if record["docs_source"] == "model"
                else "none",
                "model": record.get("docs_model") or "",
                "generated_at": record.get("docs_generated_at") or "",
                "input_sha": record.get("docs_input_sha") or "",
                "trigger": record.get("docs_trigger") or "",
                "prompt_version": record.get("docs_prompt_version") or "",
                "usage": _parse_usage(record.get("docs_usage")),
                "error": record.get("docs_error") or "",
            },
            "raw_response": record.get("docs_raw_response") or "",
        }

        if not docs_at_sha:
            result["stale"] = True
            result["staleness_reason"] = (
                "No description was recorded for this file during ingestion."
            )
            return result

        authored_at = self.gateway.get_commit_authored_at(docs_at_sha, graph_name=graph_name)
        if authored_at is None:
            result["stale"] = True
            result["staleness_reason"] = (
                f"Commit {docs_at_sha} is not in the ingested history, so the "
                "description cannot be placed in time."
            )
            return result

        changes = self.gateway.get_file_changes_after(file_id, authored_at, graph_name=graph_name)
        result["changes_since_docs"] = changes["changes"]
        result["recent_shas"] = changes["recent_shas"]
        if changes["changes"]:
            result["stale"] = True
            result["staleness_reason"] = (
                f"{changes['changes']} ingested commit(s) changed this file after "
                f"the description was written at {docs_at_sha[:8]}. The description "
                "reflects that revision, not the newest one."
            )
        else:
            result["staleness_reason"] = (
                f"Description matches the file as of {docs_at_sha[:8]}; no later "
                "ingested commit changed it."
            )
        return result
    def describe_symbol(
        self, name: str, file_id: str = "", limit: int = 10,
        graph_name: str = ""
    ) -> Dict[str, Any]:
        """Explain one declaration from the documentation its authors wrote.

        Returns every match when a name is ambiguous rather than silently
        choosing one, because picking the wrong overload would be worse than
        reporting that the name is shared.
        """
        if graph_name:
            matches = self.gateway.get_code_symbol(
                name, file_id=file_id, limit=limit, graph_name=graph_name
            )
        else:
            # No file and no graph: the name alone cannot say which
            # repository it belongs to, so every repository graph is
            # searched rather than the organisation graph, which holds no
            # declarations and would answer "no declaration named".
            matches = self.gateway.search_code_symbols_in_every_graph(
                name, limit=limit
            )

        if not matches:
            return {
                "query": name,
                "file_id": file_id,
                "match_count": 0,
                "matches": [],
                "guidance": [],
                "notes": [
                    "No ingested declaration matches that name. Ingest the repository, "
                    "or check the spelling; only exported declarations are recorded."
                ],
            }

        results = []
        for match in matches:
            owner = self.gateway.get_symbol_file(match["id"], graph_name=graph_name) or {}
            file_history: Dict[str, Any] = {}
            if owner.get("file_id"):
                file_history = self.file_timeline(
                    owner["file_id"], limit=5, graph_name=graph_name
                ) or {}

            results.append(
                {
                    "symbol_id": match["id"],
                    "name": match["name"],
                    "kind": match["kind"],
                    "signature": match["signature"],
                    "doc_comment": match["doc_comment"],
                    "documented": match["documented"],
                    "line": match["line"],
                    "visibility": match["visibility"],
                    "container": match["container"],
                    "language": match["language"],
                    "file_id": owner.get("file_id", ""),
                    "path": owner.get("path", ""),
                    "repository_id": owner.get("repository_id", ""),
                    "is_test": bool(owner.get("is_test")),
                    "changes_since_docs": self._file_changes_after(
                        owner.get("file_id", ""),
                        match["docs_at_sha"],
                        graph_name=graph_name,
                    ),
                    "recent_history": [
                        {
                            "sha": entry.get("sha"),
                            "subject": entry.get("message"),
                            "authored_at": entry.get("authored_at"),
                        }
                        for entry in file_history.get("history", [])[:5]
                    ],
                }
            )

        guidance = []
        documented = sum(1 for item in results if item["documented"])
        if documented == 0:
            guidance.append(
                "None of these declarations carries a doc comment. Read the source "
                "before relying on its behaviour."
            )
        elif documented < len(results):
            guidance.append(
                f"{documented} of {len(results)} matches are documented; the rest are not."
            )
        guidance.append(
            "This is context only. Open the file and read the implementation before "
            "changing behaviour."
        )

        notes = []
        if len(results) > 1:
            notes.append(
                f"'{name}' matches {len(results)} declarations; each is listed with "
                "its container, so pick the one you actually mean."
            )
        stale = [item for item in results if item["changes_since_docs"] > 0]
        if stale:
            notes.append(
                f"{len(stale)} declaration(s) sit in files that changed after they "
                "were scanned, so their line numbers may have moved."
            )

        return {
            "query": name,
            "file_id": file_id,
            "match_count": len(results),
            "matches": results,
            "guidance": guidance,
            "notes": notes,
        }

    def _file_changes_after(self, file_id: str, docs_at_sha: str, graph_name: str = "") -> int:
        """How many ingested commits touched a file after it was scanned.

        Used to say whether a recorded line number might have moved. Returns 0
        when the scan point is unknown, which reads as "no evidence of drift"
        rather than asserting the file is unchanged.
        """
        if not file_id or not docs_at_sha:
            return 0
        authored_at = self.gateway.get_commit_authored_at(docs_at_sha, graph_name=graph_name)
        if authored_at is None:
            return 0
        return self.gateway.get_file_changes_after(file_id, authored_at, graph_name=graph_name)["changes"]
