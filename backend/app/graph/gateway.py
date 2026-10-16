import logging
from typing import Any, Dict, List, Optional

from app.graph.connection import graph_manager
from app.graph import queries
from app.core.errors import GraphQueryError, OrgAtlasError

logger = logging.getLogger(__name__)

MAX_LIMIT = 200


def clamp_limit(limit: int | None, ceiling: int = MAX_LIMIT) -> int:
    """Clamp a caller-supplied limit into a safe range before it reaches Cypher."""
    try:
        value = int(limit) if limit is not None else ceiling
    except (TypeError, ValueError):
        return ceiling
    return max(1, min(value, ceiling))


_BOT_MARKERS = ("[bot]", "dependabot", "renovate", "github-actions")


def _is_automation(name: str) -> bool:
    lowered = (name or "").lower()
    return any(marker in lowered for marker in _BOT_MARKERS)


class GraphGateway:
    """Gateway for executing parameterized and bounded OpenCypher queries on FalkorDB."""

    def __init__(self, manager=graph_manager):
        self.manager = manager

    def _execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """Run a parameterized query and return raw rows.

        Failures propagate rather than collapsing into an empty result: an
        unreachable graph or a mistyped graph name is an operational fault, and
        reporting it as "no evidence found" would misdescribe it to the user.
        """
        try:
            graph = self.manager.get_graph()
            result = graph.query(query, params or {})
            return result.result_set
        except (GraphQueryError, OrgAtlasError):
            raise
        except Exception as e:
            logger.error("FalkorDB query failed (%s...): %s", query[:60], str(e))
            raise GraphQueryError(f"Knowledge graph query failed: {str(e)}") from e

    def get_onboarding_context(self, team_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_ONBOARDING_TOPICS_BY_TEAM, {"team_id": team_id})
        if not rows or not rows[0]:
            return None
        row = rows[0]
        return {
            "team_id": row[0],
            "team_name": row[1],
            "team_mission": row[2],
            "topics": row[3] or [],
            "services": row[4] or [],
            "people": row[5] or [],
        }

    def get_decision_trace(self, decision_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_DECISION_TRACE, {"decision_id": decision_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "decision": row[0],
            "people": row[1] or [],
            "teams": row[2] or [],
            "services": row[3] or [],
            "documents": row[4] or [],
            "incidents": row[5] or [],
            "pull_requests": row[6] or [],
            "tickets": row[7] or [],
        }

    def get_change_impact(self, service_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_CHANGE_IMPACT, {"service_id": service_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "target_service": row[0],
            "owner_team": row[1],
            "downstream_services": row[2] or [],
            "upstream_services": row[3] or [],
            "incidents": row[4] or [],
            "decisions": row[5] or [],
        }

    def get_service_ownership(self, service_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_SERVICE_OWNERSHIP, {"service_id": service_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "service": row[0],
            "team": row[1],
            "team_members": row[2] or [],
            "contributors": row[3] or [],
            "repository": row[4],
            "documents": row[5] or [],
        }

    def get_documents_by_ids(self, doc_ids: List[str]) -> List[Any]:
        """Resolve a list of stable document ids to Document nodes."""
        if not doc_ids:
            return []
        rows = self._execute(queries.GET_DOCUMENTS_BY_IDS, {"doc_ids": list(doc_ids)})
        return [row[0] for row in rows if row and row[0] is not None]

    # --- Repository forensics -------------------------------------------------

    def get_file_history(self, file_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_FILE_HISTORY, {"file_id": file_id, "limit": clamp_limit(limit)}
        )
        return [
            {
                "sha": row[0],
                "message": row[1],
                "authored_at": row[2],
                "pr_number": row[3],
                "author_id": row[4],
                "author": row[5],
            }
            for row in rows
            if not _is_automation(row[5])
        ]

    def get_file_churn(
        self, repository_id: str, path_prefix: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_FILE_CHURN,
            {
                "repository_id": repository_id,
                "path_prefix": path_prefix or "",
                "limit": clamp_limit(limit),
            },
        )
        return [
            {"file_id": row[0], "path": row[1], "is_test": row[2], "changes": row[3]}
            for row in rows
        ]

    def get_files_changed_since(
        self, repository_id: str, since: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_FILES_CHANGED_SINCE,
            {"repository_id": repository_id, "since": since, "limit": clamp_limit(limit)},
        )
        return [{"file_id": row[0], "path": row[1], "changes": row[2]} for row in rows]

    def get_path_contributors(
        self, repository_id: str, path_prefix: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_PATH_CONTRIBUTORS,
            {
                "repository_id": repository_id,
                "path_prefix": path_prefix,
                "limit": clamp_limit(limit),
            },
        )
        return [
            {"author_id": row[0], "author": row[1], "commits": row[2]}
            for row in rows
            if not _is_automation(row[1])
        ]

    def get_commits_for_path(
        self, repository_id: str, path_prefix: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_COMMITS_FOR_PATH,
            {
                "repository_id": repository_id,
                "path_prefix": path_prefix,
                "limit": clamp_limit(limit),
            },
        )
        return [
            {
                "sha": row[0],
                "message": row[1],
                "authored_at": row[2],
                "pr_number": row[3],
                "paths": row[4] or [],
            }
            for row in rows
        ]

    def get_dependency_impact(
        self, repository_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DEPENDENCY_IMPACT,
            {"repository_id": repository_id, "limit": clamp_limit(limit)},
        )
        return [{"id": row[0], "name": row[1], "url": row[2]} for row in rows]

    def get_commit_detail(self, commit_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_COMMIT_DETAIL, {"commit_id": commit_id})
        if not rows:
            return None
        row = rows[0]
        return {
            "sha": row[0],
            "message": row[1],
            "authored_at": row[2],
            "pr_number": row[3],
            "author_id": row[4],
            "author": row[5],
            "repository_id": row[6],
        }

    def get_change_coupling(
        self, file_id: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_CHANGE_COUPLING, {"file_id": file_id, "limit": clamp_limit(limit)}
        )
        return [
            {"file_id": row[0], "path": row[1], "shared_commits": row[2]}
            for row in rows
        ]

    def repository_exists(self, repository_id: str) -> bool:
        rows = self._execute(queries.GET_REPOSITORY, {"repository_id": repository_id})
        return bool(rows)

    def list_repositories(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._execute(queries.LIST_REPOSITORIES, {"limit": clamp_limit(limit)})
        return [
            {
                "id": row[0],
                "name": row[1],
                "url": row[2],
                "source": row[3],
                "commit_count": row[4],
                "file_count": row[5],
            }
            for row in rows
        ]

    def get_entity_detail(self, entity_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_ENTITY_DETAIL, {"entity_id": entity_id})
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        row = rows[0]
        return {
            "entity": row[0],
            "outgoing": row[1] or [],
            "incoming": row[2] or [],
        }

    def search_entities(self, query_str: str) -> List[Dict[str, Any]]:
        rows = self._execute(queries.SEARCH_ENTITIES, {"query": query_str})
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "label": row[1],
                "name": row[2],
                "properties": row[3] or {},
            })
        return results

    # --- Authored file descriptions -------------------------------------------

    def get_file_description(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return the description extracted from the file's own source text."""
        rows = self._execute(queries.GET_FILE_DESCRIPTION, {"file_id": file_id})
        if not rows:
            return None
        row = rows[0]
        return {
            "path": row[0],
            "name": row[1],
            "language": row[2],
            "is_test": row[3],
            "summary": row[4],
            "symbols": row[5],
            "docs_source": row[6],
            "docs_at_sha": row[7],
            "repository_id": row[8],
            "docs_model": row[9],
            "docs_generated_at": row[10],
            "docs_input_sha": row[11],
            "docs_trigger": row[12],
            "docs_usage": row[13],
            "docs_raw_response": row[14],
            "docs_prompt_version": row[15],
            "docs_error": row[16],
        }

    def get_commit_authored_at(self, sha: str) -> Optional[str]:
        rows = self._execute(queries.GET_COMMIT_AUTHORED_AT, {"sha": sha})
        if not rows or not rows[0]:
            return None
        return rows[0][0] or None

    def get_file_changes_after(self, file_id: str, since: str) -> Dict[str, Any]:
        rows = self._execute(
            queries.GET_FILE_CHANGES_AFTER, {"file_id": file_id, "since": since}
        )
        if not rows:
            return {"changes": 0, "recent_shas": []}
        return {"changes": rows[0][0] or 0, "recent_shas": rows[0][1] or []}

    # --- Code declarations ----------------------------------------------------

    def get_code_symbol(
        self, name: str, file_id: str = "", limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Look up declarations by name, most documented first."""
        rows = self._execute(
            queries.GET_CODE_SYMBOL,
            {"name": name, "file_id": file_id or "", "limit": clamp_limit(limit)},
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "kind": row[2],
                "signature": row[3],
                "doc_comment": row[4],
                "documented": row[5],
                "line": row[6],
                "visibility": row[7],
                "container": row[8],
                "language": row[9],
                "repository_id": row[10],
                "docs_at_sha": row[11],
            }
            for row in rows
        ]

    def search_code_symbols(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.SEARCH_CODE_SYMBOLS,
            {"query": query, "limit": clamp_limit(limit)},
        )
        return [
            {
                "name": row[0],
                "id": row[1],
                "kind": row[2],
                "container": row[3],
                "documented": row[4],
            }
            for row in rows
        ]

    def get_symbol_file(self, symbol_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute(queries.GET_SYMBOL_FILE, {"symbol_id": symbol_id})
        if not rows:
            return None
        row = rows[0]
        return {
            "file_id": row[0],
            "path": row[1],
            "repository_id": row[2],
            "language": row[3],
            "is_test": row[4],
        }

graph_gateway = GraphGateway()

