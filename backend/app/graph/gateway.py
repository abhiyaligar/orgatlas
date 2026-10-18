import logging
from typing import Any, Dict, List, Optional, Sequence

from app.graph.connection import graph_manager, org_graph_name
from app.graph import queries
from app.core.errors import GraphNotFoundError, GraphQueryError, OrgAtlasError

logger = logging.getLogger(__name__)

MAX_LIMIT = 200
# Question resolution returns everything that matched a handful of terms, so it
# needs a wider ceiling than a single paginated listing.
MAX_TERM_RESULTS = 60


def _dedupe_terms(terms: Sequence[str]) -> List[str]:
    """Strip and de-duplicate candidate terms, keeping the caller's order.

    Order is meaningful: the caller offers the most likely subject first, and a
    stable de-duplication preserves that ranking instead of reshuffling it.
    """
    cleaned: List[str] = []
    for raw in terms:
        token = raw.strip()
        if token and token not in cleaned:
            cleaned.append(token)
    return cleaned


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

    def _execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        graph_name: str = "",
    ) -> List[Any]:
        """Run a parameterized query and return raw rows.

        ``graph_name`` selects which graph to read. Empty means the
        organisation graph, which is where non-code entities live. Callers that
        already know which graph an entity was resolved from pass it, so a
        symbol read goes to the repository graph rather than to org.

        Failures propagate rather than collapsing into an empty result: an
        unreachable graph or a mistyped graph name is an operational fault, and
        reporting it as "no evidence found" would misdescribe it to the user.
        """
        try:
            graph = self.manager.get_graph(graph_name)
            result = graph.query(query, params or {})
            return result.result_set
        except (GraphQueryError, OrgAtlasError):
            raise
        except Exception as e:
            logger.error(
                "FalkorDB query failed on %s (%s...): %s",
                graph_name or "(org)",
                query[:60],
                str(e),
            )
            raise GraphQueryError(f"Knowledge graph query failed: {str(e)}") from e

    def search_entities_by_terms(
        self, terms: Sequence[str], graph_names: Optional[Sequence[str]] = None
    ) -> List[Dict[str, Any]]:
        """Resolve several candidate terms, across every graph a question may reach.

        Ask latency is dominated by round trips, and a question can mention a
        dozen words, so resolution is a single UNWIND per graph rather than a
        lookup per term. Each row reports the term and the graph that produced
        it, so the caller can send the follow-up retrieval to the same graph.

        A graph that cannot be read is logged and skipped rather than failing
        the question, because one unreachable repository should not stop an
        answer the organisation graph can give. If every graph fails, that is an
        operational fault and it propagates.
        """
        cleaned = _dedupe_terms(terms)
        if not cleaned:
            return []

        targets = list(graph_names) if graph_names else self.manager.search_graphs()
        found: List[Dict[str, Any]] = []
        failures: List[str] = []
        for name in targets:
            try:
                rows = self._execute(
                    queries.SEARCH_ENTITIES_BY_TERMS,
                    {"terms": cleaned, "limit": MAX_TERM_RESULTS},
                    graph_name=name,
                )
            except Exception as exc:
                logger.warning("term resolution skipped graph %s: %s", name, exc)
                failures.append(name)
                continue
            for row in rows:
                found.append(
                    {
                        "term": row[0],
                        "id": row[1],
                        "label": row[2],
                        "name": row[3],
                        "quality": row[4],
                        "graph_name": name,
                    }
                )

        if failures and len(failures) == len(targets):
            raise GraphQueryError(
                "No knowledge graph could be read: " + ", ".join(failures)
            )
        return found

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

    def get_file_history(
        self, file_id: str, limit: int = 50, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_FILE_HISTORY,
            {"file_id": file_id, "limit": clamp_limit(limit)},
            graph_name,
        )
        return [
            {
                "sha": row[0],
                "message": row[1],
                "authored_at": row[2],
                "pr_number": row[3],
                "author_id": row[4],
                # CommitSummary declares author as a non-null string, and a
                # commit whose author was never captured would otherwise fail
                # response validation and surface as a 500.
                "author": row[5] or "",
            }
            for row in rows
            if not _is_automation(row[5])
        ]

    def get_file_churn(
        self, repository_id: str, path_prefix: str = "", limit: int = 50,
    graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_FILE_CHURN,
            {
                "repository_id": repository_id,
                "path_prefix": path_prefix or "",
                "limit": clamp_limit(limit),
            },
        graph_name=graph_name
        )
        return [
            {"file_id": row[0], "path": row[1], "is_test": row[2], "changes": row[3]}
            for row in rows
        ]

    def get_files_changed_since(
        self, repository_id: str, since: str, limit: int = 100,
    graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_FILES_CHANGED_SINCE,
            {"repository_id": repository_id, "since": since, "limit": clamp_limit(limit)},
        graph_name=graph_name
        )
        return [{"file_id": row[0], "path": row[1], "changes": row[2]} for row in rows]

    def get_path_contributors(
        self, repository_id: str, path_prefix: str, limit: int = 25,
    graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_PATH_CONTRIBUTORS,
            {
                "repository_id": repository_id,
                "path_prefix": path_prefix,
                "limit": clamp_limit(limit),
            },
        graph_name=graph_name
        )
        return [
            {"author_id": row[0], "author": row[1], "commits": row[2]}
            for row in rows
            if not _is_automation(row[1])
        ]

    def get_commits_for_path(
        self, repository_id: str, path_prefix: str, limit: int = 50,
    graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_COMMITS_FOR_PATH,
            {
                "repository_id": repository_id,
                "path_prefix": path_prefix,
                "limit": clamp_limit(limit),
            },
        graph_name=graph_name
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
        self, repository_id: str, limit: int = 50,
    graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DEPENDENCY_IMPACT,
            {"repository_id": repository_id, "limit": clamp_limit(limit)},
        graph_name=graph_name
        )
        return [{"id": row[0], "name": row[1], "url": row[2]} for row in rows]

    def get_commit_detail(
        self, commit_id: str, graph_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_COMMIT_DETAIL, {"commit_id": commit_id}, graph_name=graph_name
        )
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
        self, file_id: str, limit: int = 25,
    graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_CHANGE_COUPLING, {"file_id": file_id, "limit": clamp_limit(limit)},
        graph_name=graph_name
        )
        return [
            {"file_id": row[0], "path": row[1], "shared_commits": row[2]}
            for row in rows
        ]

    def repository_exists(self, repository_id: str, graph_name: str = "") -> bool:
        rows = self._execute(
            queries.GET_REPOSITORY, {"repository_id": repository_id}, graph_name=graph_name
        )
        return bool(rows)

    def list_repositories(self, limit: int = 50, graph_name: str = "") -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.LIST_REPOSITORIES,
            {"limit": clamp_limit(limit)},
            graph_name=graph_name,
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "url": row[2],
                "source": row[3],
                "commit_count": row[4],
                "file_count": row[5],
                "graph_name": graph_name,
            }
            for row in rows
        ]

    def list_all_repositories(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Every ingested repository, wherever its code graph lives.

        Each repository owns one graph named ``code_{repository_id}``, so the
        organisation graph no longer knows they exist and a query against it
        returns nothing. Reading them means visiting each graph, which is a
        round trip per repository -- acceptable because this is a list page
        with tens of entries at most, and an index in the org graph would be a
        second copy to keep in step with the authoritative one.

        The organisation graph is read too, and its entries win on a duplicate
        id. That costs one extra query and means the endpoint is correct both
        before and after an existing installation is split, rather than only on
        a fresh one.
        """
        found: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []

        for name in [org_graph_name()] + graph_manager.list_repository_graphs():
            try:
                rows = self.list_repositories(limit=limit, graph_name=name)
            except GraphNotFoundError:
                # A graph listed a moment ago can be gone; that is not a reason
                # to fail the whole listing.
                logger.warning("Skipping unavailable repository graph '%s'", name)
                continue
            except Exception:
                # One unreadable repository must not blank the entire list. It
                # is logged, so the omission is visible rather than silent.
                logger.error("Failed to list repositories in graph '%s'", name, exc_info=True)
                continue

            for row in rows:
                if row["id"] not in found:
                    order.append(row["id"])
                found[row["id"]] = row

        return [found[rid] for rid in order]

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

    def get_repository_files(
        self, repository_id: str, per_language: int = 4, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        """Return a repository's languages, each with a few example files.

        A repository asks about its own shape ("what is the tech stack"), which
        is a question about the files rather than about any one of them. There
        is no Cypher edge from a file to its repository, so this reads the
        ``repository_id`` property the scanner stamped on every file.

        The examples are sampled per language rather than taken as one long
        list, because forty files of whichever language sorts first would answer
        a question about the whole repository with one language.
        """
        rows = self._execute(
            queries.GET_REPOSITORY_FILES,
            {"repository_id": repository_id, "per_language": per_language},
            graph_name,
        )
        return [
            {
                "language": row[0],
                "files": int(row[1] or 0),
                "samples": [dict(sample) for sample in (row[2] or [])],
            }
            for row in rows
        ]

    def get_repository_language_mix(
        self, repository_id: str, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        """Count the files a repository has in each language, tests excluded."""
        return [
            {"language": entry["language"], "files": entry["files"]}
            for entry in self.get_repository_files(
                repository_id, per_language=0, graph_name=graph_name
            )
            if entry["language"] and str(entry["language"]).lower() != "unknown"
        ]

    def get_file_description(
        self, file_id: str, graph_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Return the description extracted from the file's own source text."""
        rows = self._execute(
            queries.GET_FILE_DESCRIPTION, {"file_id": file_id}, graph_name
        )
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

    def get_commit_authored_at(self, sha: str, graph_name: str = "") -> Optional[str]:
        rows = self._execute(queries.GET_COMMIT_AUTHORED_AT, {"sha": sha}, graph_name=graph_name)
        if not rows or not rows[0]:
            return None
        return rows[0][0] or None

    def get_file_changes_after(self, file_id: str, since: str, graph_name: str = "") -> Dict[str, Any]:
        rows = self._execute(
            queries.GET_FILE_CHANGES_AFTER, {"file_id": file_id, "since": since},
        graph_name=graph_name
        )
        if not rows:
            return {"changes": 0, "recent_shas": []}
        return {"changes": rows[0][0] or 0, "recent_shas": rows[0][1] or []}

    # --- Code declarations ----------------------------------------------------

    def get_code_symbol(
        self, name: str, file_id: str = "", limit: int = 10, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        """Look up declarations by name, most documented first."""
        rows = self._execute(
            queries.GET_CODE_SYMBOL,
            {
                "name": name,
                "file_id": file_id or "",
                # Built here rather than concatenated in the query: a
                # parameter inside `STARTS WITH $x + '::'` makes FalkorDB reject
                # the whole statement with "expected Boolean but was String".
                "file_prefix": f"{file_id}::" if file_id else "",
                "limit": clamp_limit(limit),
            },
            graph_name,
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

    def search_code_symbols_in_every_graph(
        self, name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Find a declaration when the caller does not say which file it is in.

        A symbol name carries no repository, and a name like ``register`` exists
        in more than one of them, so an unscoped lookup has to visit each
        repository graph rather than default to the organisation graph -- which
        holds no declarations at all, and therefore reports "no declaration
        named" for a declaration that is sitting right there.

        Each result carries the graph it came from, so a caller can tell two
        same-named declarations apart instead of receiving an arbitrary one.
        """
        found: List[Dict[str, Any]] = []
        for candidate in [org_graph_name()] + graph_manager.list_repository_graphs():
            try:
                matches = self.get_code_symbol(name, limit=limit, graph_name=candidate)
            except GraphNotFoundError:
                continue
            except Exception:
                logger.error(
                    "Failed to search graph '%s' for symbol", candidate, exc_info=True
                )
                continue
            for match in matches:
                match["graph_name"] = candidate
                found.append(match)
        return found

    def search_code_symbols(
        self, query: str, limit: int = 20, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.SEARCH_CODE_SYMBOLS,
            {"query": query, "limit": clamp_limit(limit)},
            graph_name,
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

    # --- Document, Slack and Metric writes --------------------------------------

    # --- Decision evidence reads -----------------------------------------------

    def rank_decisions_by_coverage(
        self, terms: Sequence[str], limit: int = 8
    ) -> List[Dict[str, Any]]:
        """Decisions covering the most of a question's terms.

        Returns each candidate with the terms it matched and how many, so a
        caller can see not only which decision fits best but whether it leaves
        part of the question unaccounted for.
        """
        cleaned = _dedupe_terms(terms)
        if not cleaned:
            return []
        rows = self._execute(
            queries.GET_DECISIONS_BY_TERM_COVERAGE,
            {"terms": cleaned, "limit": clamp_limit(limit)},
        )
        return [
            {"id": r[0], "title": r[1], "coverage": r[2], "terms": list(r[3] or [])}
            for r in rows
        ]

    def get_decision_evidence(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """The decision itself, with its documents and the incidents behind it."""
        rows = self._execute(queries.GET_DECISION_EVIDENCE, {"decision_id": decision_id})
        if not rows:
            return None
        row = rows[0]
        return {
            "decision_id": row[0],
            "title": row[1],
            "summary": row[2],
            "rationale": row[3],
            "alternatives": row[4],
            "status": row[5],
            "decided_at": row[6] or None,
            "quote": row[7],
        }

    def get_decision_documents(self, decision_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DECISION_DOCUMENTS,
            {"decision_id": decision_id, "limit": clamp_limit(limit)},
        )
        return [
            {"id": r[0], "title": r[1], "uri": r[2] or None, "author": r[3], "excerpt": r[4]}
            for r in rows
        ]

    def get_decision_incidents(self, decision_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DECISION_INCIDENTS,
            {"decision_id": decision_id, "limit": clamp_limit(limit)},
        )
        return [{"id": r[0], "title": r[1], "uri": r[2] or None, "severity": r[3]} for r in rows]

    def get_decision_people(self, decision_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DECISION_PEOPLE,
            {"decision_id": decision_id, "limit": clamp_limit(limit)},
        )
        return [
            {"person_id": r[0], "name": r[1], "involvement": r[2], "role": r[3], "quote": r[4]}
            for r in rows
        ]

    def get_decision_discussion(
        self, decision_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DECISION_DISCUSSION,
            {"decision_id": decision_id, "limit": clamp_limit(limit)},
        )
        return [
            {
                "source_id": r[0],
                "speaker": r[1],
                "text": r[2],
                "channel": r[3],
                "posted_at": r[4],
                "permalink": r[5] or None,
            }
            for r in rows
        ]

    def get_decision_metrics(
        self, decision_id: str, limit: int = 15
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_DECISION_METRICS,
            {"decision_id": decision_id, "limit": clamp_limit(limit)},
        )
        return [
            {
                "id": r[0],
                "name": r[1],
                "value": r[2],
                "unit": r[3],
                "baseline": r[4] or None,
                "direction": r[5],
                "quote": r[6],
                "document_id": r[7] or None,
            }
            for r in rows
        ]

    def get_decision_migration(self, decision_id: str) -> Dict[str, List[str]]:
        rows = self._execute(queries.GET_DECISION_MIGRATION, {"decision_id": decision_id, "limit": 20})
        from_tech: List[str] = []
        to_tech: List[str] = []
        for direction, name in rows:
            (from_tech if direction == "MIGRATED_FROM" else to_tech).append(name)
        return {"from": from_tech, "to": to_tech}

    def get_people_commits(
        self, person_ids: List[str], limit: int = 25
    ) -> List[Dict[str, Any]]:
        """Commits authored by the people involved, newest first."""
        person_ids = [pid for pid in person_ids if pid]
        if not person_ids:
            return []
        rows = self._execute(
            queries.GET_PEOPLE_COMMITS,
            {"person_ids": person_ids, "limit": clamp_limit(limit)},
        )
        return [
            {
                "sha": r[0],
                "message": r[1],
                "authored_at": r[2],
                "pr_number": int(r[3]) if r[3] else None,
                "author": r[4],
                "repository_id": r[5],
            }
            for r in rows
        ]

    def upsert_document(self, record: Dict[str, Any]) -> None:
        self._execute(queries.UPSERT_DOCUMENT, record)

    def link_document(self, document_id: str, edges: List[Dict[str, Any]]) -> int:
        """Link a document to the nodes it talks about."""
        if not edges:
            return 0
        rows = self._execute(
            queries.UPSERT_DOCUMENT_EDGES,
            {"document_id": document_id, "edges": edges},
        )
        return rows[0][0] if rows else 0

    def upsert_extracted_decisions(
        self, document_id: str, decisions: List[Dict[str, Any]]
    ) -> List[str]:
        """Write decisions extracted from a document and return their ids."""
        if not decisions:
            return []
        rows = self._execute(
            queries.UPSERT_EXTRACTED_DECISIONS,
            {"document_id": document_id, "decisions": decisions},
        )
        return [row[0] for row in rows]

    def upsert_decision_people(
        self, decision_id: str, people: List[Dict[str, Any]]
    ) -> int:
        """Attribute people to a decision, grouped by how they were involved."""
        if not people:
            return 0

        by_involvement: Dict[str, List[Dict[str, Any]]] = {}
        for person in people:
            by_involvement.setdefault(person.get("involvement") or "unknown", []).append(person)

        queries_by_involvement = {
            "proposed": queries.UPSERT_DECISION_PROPOSERS,
            "approved": queries.UPSERT_DECISION_APPROVERS,
            "objected": queries.UPSERT_DECISION_OBJECTORS,
            "discussed": queries.UPSERT_DECISION_DISCUSSANTS,
            "implemented": queries.UPSERT_DECISION_IMPLEMENTERS,
        }

        written = 0
        for involvement, rows in by_involvement.items():
            query = queries_by_involvement.get(involvement)
            if query is None:
                continue
            result = self._execute(query, {"decision_id": decision_id, "people": rows})
            written += result[0][0] if result else 0
        return written

    def upsert_metrics(
        self, document_id: str, metrics: List[Dict[str, Any]]
    ) -> List[str]:
        if not metrics:
            return []
        rows = self._execute(
            queries.UPSERT_METRICS,
            {"document_id": document_id, "metrics": metrics},
        )
        return [row[0] for row in rows]

    def record_migration(
        self, decision_id: str, migrations: List[Dict[str, Any]]
    ) -> int:
        """Record the technology a decision moved away from."""
        if not migrations:
            return 0
        rows = self._execute(
            queries.UPSERT_MIGRATION,
            {"decision_id": decision_id, "migrations": migrations},
        )
        return rows[0][0] if rows else 0

    def record_migration_to(
        self, decision_id: str, migrations: List[Dict[str, Any]]
    ) -> int:
        """Record the technology a decision moved to.

        Kept separate from :meth:`record_migration` because the two ends of a
        migration mean opposite things, and collapsing them into one type would
        read as "moved away from" for both.
        """
        if not migrations:
            return 0
        rows = self._execute(
            queries.UPSERT_MIGRATION_TO,
            {"decision_id": decision_id, "migrations": migrations},
        )
        return rows[0][0] if rows else 0

    def upsert_slack_message(self, record: Dict[str, Any]) -> None:
        self._execute(queries.UPSERT_SLACK_MESSAGE, record)

    def link_slack_message(
        self, message_id: str, edges: List[Dict[str, Any]]
    ) -> int:
        if not edges:
            return 0
        rows = self._execute(
            queries.UPSERT_SLACK_MESSAGE_EDGES,
            {"message_id": message_id, "edges": edges},
        )
        return rows[0][0] if rows else 0

    def link_slack_author(
        self, message_id: str, person_ids: List[str]
    ) -> int:
        """Attribute a message to a person already in the graph."""
        person_ids = [pid for pid in person_ids if pid]
        if not person_ids:
            return 0
        rows = self._execute(
            queries.LINK_SLACK_AUTHOR,
            {"message_id": message_id, "person_ids": person_ids},
        )
        return rows[0][0] if rows else 0

    def find_related_decisions(self, node_id: str) -> List[Dict[str, Any]]:
        """Decisions directly connected to a node, for "why" questions.

        Resolving "why did this happen" usually lands on the incident or the
        ticket rather than the decision, and tracing an incident id as if it
        were a decision id returns nothing. The decision is one hop away, so it
        is looked up rather than guessed.
        """
        if not node_id:
            return []
        rows = self._execute(queries.FIND_RELATED_DECISIONS, {"node_id": node_id})
        return [{"id": row[0], "title": row[1], "via": row[2]} for row in rows]

    def search_code_symbols_by_terms(
        self, terms: Sequence[str], limit: int = 12, graph_name: str = ""
    ) -> List[Dict[str, Any]]:
        """Resolve candidate terms to declarations, with file and line attached."""
        cleaned = _dedupe_terms(terms)
        if not cleaned:
            return []

        rows = self._execute(
            queries.SEARCH_CODE_SYMBOLS_BY_TERMS,
            {"terms": cleaned, "limit": clamp_limit(limit)},
            graph_name,
        )
        return [
            {
                "term": row[0],
                "name": row[1],
                "id": row[2],
                "kind": row[3],
                "signature": row[4],
                "doc_comment": row[5],
                "documented": row[6],
                "line": row[7],
                "visibility": row[8],
                "container": row[9],
                "language": row[10],
                "path": row[11],
                "file_id": row[12],
                "is_test": row[13],
            }
            for row in rows
        ]

    def get_symbol_file(
        self, symbol_id: str, graph_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        rows = self._execute(
            queries.GET_SYMBOL_FILE, {"symbol_id": symbol_id}, graph_name
        )
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

