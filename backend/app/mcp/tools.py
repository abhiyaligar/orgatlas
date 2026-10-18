"""Read-only MCP tools for architecture context and change forensics.

Handlers are module-level functions so they can be unit-tested directly. Each
one delegates to an existing application service; none of them opens a
connection, builds Cypher, or mutates anything.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.graph.gateway import graph_gateway
from app.mcp import (
    MAX_RECORDS,
    READ_ONLY,
    WRITES,
    ToolInputError,
    citations_to_sources,
    clamp,
    envelope,
    refusal,
    subgraph_payload,
    validate_identifier,
)
from app.services.change_forensics_service import ChangeForensicsService
from app.services.commit_provenance_service import CommitProvenanceService
from app.services.decision_service import DecisionTraceService
from app.services.impact_service import ChangeImpactService
from app.services.onboarding_service import OnboardingContextService
from app.services.ownership_service import OwnershipService

from app.mcp.write_tools import enqueue_repository_ingest, get_ingest_job

logger = logging.getLogger(__name__)

_decisions = DecisionTraceService()
_impact = ChangeImpactService()
_onboarding = OnboardingContextService()
_ownership = OwnershipService()
_forensics = ChangeForensicsService()
_provenance = CommitProvenanceService()

DEFAULT_REPOSITORY_ID = "repo_falkordb_falkordb"

# Required by Docs/MCP_SERVER.md: every tool description must disclose that the
# result is advisory context and not change approval.
ADVISORY_DISCLOSURE = (
    "Read-only. Returns advisory context, not change approval: it cannot edit "
    "code, open tickets or change the graph. Inspect the code and let a human "
    "approve any edit."
)


# A symbol doc comment is the answer to "what does this do", so it is carried in
# full rather than trimmed to a teaser line.
MAX_SYMBOL_DOC_CHARS = 2000


def _citation_dict(citation) -> Dict[str, Any]:
    """Kept for single-citation call sites; bulk conversion uses citations_to_sources."""
    return {
        "source_id": citation.source_id,
        "title": citation.title,
        "type": citation.type,
        "url": citation.url,
    }


# --- Graph resolution for repository-scoped tools ---------------------------
# Several tools below read repository data. Each has to name the graph first,
# or it answers from the organisation graph and reports "no history" for a
# repository whose history is sitting in its own graph. These two helpers keep
# that resolution in one place and fail as a refusal rather than an exception:
# a tool that raises is reported by the SDK as "Error executing tool" with no
# reason attached, which is the same trap the write tools had.


def _graph_for_repository(repository_id: str):
    """Return (graph_name, None), or (None, refusal) for an unknown repository."""
    from app.graph.repository_scope import UnknownRepository, repository_graph

    try:
        return repository_graph(repository_id), None
    except UnknownRepository as exc:
        return None, refusal(
            str(exc),
            notes=["Ingest it first with ingest_repository, then ask again."],
        )


def _graph_for_file_id(file_id: str):
    """Return (graph_name, None), or (None, refusal) for an unusable file id."""
    from app.graph.repository_scope import InvalidFileId, graph_for_file

    try:
        return graph_for_file(file_id), None
    except InvalidFileId as exc:
        return None, refusal(
            str(exc),
            notes=["A file id is the graph node id, e.g. repo_name::src/main.rs"],
        )


# --- Seeded organization ---------------------------------------------------


def get_architecture_context(identifier: str) -> Dict[str, Any]:
    """Summary of a service, repository or decision with its sources."""
    target = validate_identifier(identifier, "identifier")

    if target.startswith("repo_"):
        return _repository_architecture_context(target)

    trace = _decisions.trace_decision(target)
    if trace is not None:
        return envelope(
            summary=f"{trace['title']} — {trace['status']}.",
            entities=[
                {"type": "Decision", "id": trace["decision_id"], "name": trace["title"]}
            ],
            sources=[citations_to_sources(trace["citations"])],
            subgraph=subgraph_payload(trace["graph"]),
            notes=[f"Decided {trace['decided_at']}."] if trace["decided_at"] else [],
            actions=["Read the supporting documents before changing anything this constrains."],
            confidence="supported" if len(trace["citations"]) >= 2 else "partial",
        )

    ownership = _ownership.get_ownership(target)
    if ownership is not None:
        return envelope(
            summary=f"{ownership['service_name']} is owned by {ownership['owner_team']}.",
            entities=[
                {
                    "type": "Service",
                    "id": ownership["service_id"],
                    "name": ownership["service_name"],
                }
            ],
            sources=[citations_to_sources(ownership["citations"])],
            notes=[
                f"{len(ownership['team_members'])} team members, "
                f"{len(ownership['contributors'])} contributors."
            ],
            actions=["Coordinate with the owning team before changing this service."],
            confidence="supported" if len(ownership["citations"]) >= 2 else "partial",
        )

    return refusal(
        f"No architecture context found for '{target}'.",
        notes=[
            "Try a seeded service id (svc_...), a decision id (dec_...), "
            "or an ingested repository id (repo_...)."
        ],
    )


def _repository_architecture_context(repository_id: str) -> Dict[str, Any]:
    graph_name, denied = _graph_for_repository(repository_id)
    if denied is not None:
        return denied
    brief = _forensics.investigation_brief(repository_id, graph_name=graph_name)

    if not brief["hotspots"] and not brief["dependency_blast_radius"]:
        return refusal(
            f"No ingested history for '{repository_id}'.",
            notes=["Ingest the repository before relying on forensics for it."],
        )

    return envelope(
        summary=(
            f"{repository_id}: {len(brief['hotspots'])} high-churn areas, "
            f"{len(brief['dependency_blast_radius'])} declared dependent repositories."
        ),
        entities=[
            {"type": "Repository", "id": repository_id, "name": repository_id}
        ]
        + [
            {"type": "File", "id": item["file_id"], "name": item["path"]}
            for item in brief["hotspots"][:10]
        ],
        notes=brief["guidance"],
        actions=[
            "Read the highest-churn file before touching this area.",
            "Check the dependent repositories before changing a public interface.",
        ],
    )


def find_owner_and_expertise(system_identifier: str) -> Dict[str, Any]:
    """Accountable team, maintainers and experienced contributors."""
    target = validate_identifier(system_identifier, "system_identifier")
    ownership = _ownership.get_ownership(target)

    if ownership is None and target.startswith("repo_"):
        graph_name, denied = _graph_for_repository(target)
        if denied is not None:
            return denied
        contributors = _forensics.investigation_brief(
            target, graph_name=graph_name
        )["contributors"]
        if not contributors:
            return refusal(f"No ingested history for '{target}'.")
        return envelope(
            summary=f"Most active contributors in {target}.",
            entities=[
                {"type": "Person", "id": c["author_id"], "name": c["author"]}
                for c in contributors
            ],
            notes=["Derived from commit attribution, not an employment record."],
            actions=["Review their prior changes before editing unfamiliar code."],
        )

    if ownership is None:
        return refusal(f"No ownership recorded for '{target}'.")

    return envelope(
        summary=f"{ownership['service_name']} is owned by {ownership['owner_team']}.",
        entities=[
            {"type": "Person", "id": member["id"], "name": member["name"]}
            for member in ownership["team_members"]
        ]
        + [
            {"type": "Person", "id": person["id"], "name": person["name"]}
            for person in ownership["contributors"]
        ],
        notes=[
            f"Repository: {ownership['repository_url'] or 'not recorded'}.",
            "Commit contributors are inferred from history, not a responsibility roster.",
        ],
        actions=["Contact the owning team before changing this service."],
        confidence="supported" if len(ownership["citations"]) >= 2 else "partial",
    )


def trace_technical_decision(decision_id_or_topic: str) -> Dict[str, Any]:
    """Rationale, alternatives, deciders and evidence for a decision."""
    target = validate_identifier(decision_id_or_topic, "decision_id_or_topic")
    trace = _decisions.trace_decision(target)

    if trace is None:
        return refusal(
            f"No decision record found for '{target}'.",
            notes=["Seeded decisions: dec_kafka_async, dec_vault_transit_cache."],
        )

    return envelope(
        summary=f"{trace['title']} — {trace['status']}.",
        entities=[{"type": "Decision", "id": trace["decision_id"], "name": trace["title"]}],
        sources=[citations_to_sources(trace["citations"])],
        subgraph=subgraph_payload(trace["graph"]),
        notes=[f"Alternatives considered: {trace['alternatives'] or 'not recorded'}."],
        actions=["Respect the stated trade-offs when changing affected services."],
        confidence="supported" if len(trace["citations"]) >= 2 else "partial",
    )


def assess_change_impact(
    target_service: str, proposed_change: Optional[str] = None
) -> Dict[str, Any]:
    """Bounded two-hop dependency analysis for a service."""
    target = validate_identifier(target_service, "target_service")
    result = _impact.assess_impact(target)

    if result is None:
        return refusal(f"No change-impact record for '{target}'.")

    notes = [result["risk_notes"]]
    if proposed_change:
        notes.append(f"Stated change: {proposed_change[:200]}")
    notes.append(
        "Impact is computed from recorded graph edges only. Anything not modelled "
        "will not appear here."
    )

    return envelope(
        summary=(
            f"{result['service_name']} (owned by {result['owner_team'] or 'unknown team'}): "
            f"{result['downstream_count']} downstream, {result['upstream_count']} upstream."
        ),
        entities=[
            {"type": "Service", "id": result["service_id"], "name": result["service_name"]}
        ],
        sources=[citations_to_sources(result["citations"])],
        subgraph=subgraph_payload(result["graph"]),
        notes=notes,
        actions=[
            "Notify the owning team.",
            "Run the affected service's tests before deploying.",
        ],
        confidence="supported" if len(result["citations"]) >= 2 else "partial",
    )


def get_onboarding_context(team_id: str) -> Dict[str, Any]:
    """First-week learning path, owned systems, people and reading for a team."""
    target = validate_identifier(team_id, "team_id")
    result = _onboarding.get_onboarding_map(target)

    if result is None:
        return refusal(
            f"No onboarding data for '{target}'.",
            notes=["Seeded teams: team_payments, team_platform."],
        )

    return envelope(
        summary=f"Onboarding path for {result.team_name}.",
        entities=[
            {"type": "OnboardingTopic", "id": topic.id, "name": topic.title}
            for topic in result.topics
        ]
        + [
            {"type": "Service", "id": service.id, "name": service.name}
            for service in result.owned_services
        ]
        + [
            {"type": "Person", "id": person.id, "name": person.name}
            for person in result.people_to_meet
        ],
        sources=[citations_to_sources(result.reading_list)],
        notes=[result.mission] if result.mission else [],
        actions=["Read the linked handbook before making your first change."],
        confidence="supported" if len(result.reading_list) >= 2 else "partial",
    )


def search_architecture_evidence(
    query: str, entity_type: Optional[str] = None, limit: int = 20
) -> Dict[str, Any]:
    """Ranked graph entities matching a narrow text query."""
    text = validate_identifier(query, "query")
    if len(text) < 2:
        raise ToolInputError("query must be at least two characters")

    rows = graph_gateway.search_entities(text)
    matched = [
        row
        for row in rows
        if entity_type is None or row["label"].lower() == entity_type.lower()
    ]
    entities = [
        {"type": row["label"], "id": row["id"], "name": row["name"]}
        for row in matched[: clamp(limit)]
    ]

    if not entities:
        return refusal(
            f"No graph entities matched '{text}'.",
            notes=["Search covers the seeded organization and ingested repositories."],
        )

    return envelope(
        summary=f"{len(entities)} matching entities for '{text}'.",
        entities=entities,
        actions=["Inspect a matching entity before making a related change."],
    )


# --- Repository forensics --------------------------------------------------


def trace_change_origin(file_id: str, limit: int = 25) -> Dict[str, Any]:
    """Who changed a file, in which pull request, and what changes with it.

    ``file_id`` is the graph node id of the form ``repo_<name>::<path>``.
    """
    target = validate_identifier(file_id, "file_id")
    graph_name, denied = _graph_for_file_id(target)
    if denied is not None:
        return denied
    timeline = _forensics.file_timeline(target, limit=clamp(limit), graph_name=graph_name)

    if timeline is None:
        return refusal(
            f"No ingested history for '{target}'.",
            notes=[
                "file_id must be the graph node id, e.g. "
                "repo_falkordb_falkordb::src/redis/redis.c"
            ],
        )

    coupling = _forensics.coupled_files(target, limit=10, graph_name=graph_name)
    history = timeline["history"]
    notes = [coupling["advice"]]

    sources = [citations_to_sources(timeline["citations"])]
    entities = [
        {"type": "Commit", "id": entry["sha"], "name": entry["message"][:80]}
        for entry in history[:10]
    ]
    entities += [
        {"type": "File", "id": coupled["file_id"], "name": coupled["path"]}
        for coupled in coupling["coupled"]
    ]

    confidence = "supported" if len(timeline["citations"]) >= 2 else "partial"

    # Provenance for the most recent change: the pull request, any linked
    # decision, and an explicit list of what could not be resolved.
    origin = _provenance.trace(history[0]["sha"]) if history else None
    if origin is not None:
        commit = origin["commit"] or {}
        pr_number = commit.get("pr_number")
        notes.append(
            f"Most recent change {'landed via PR #' + str(pr_number) if pr_number else 'has no linked pull request'}."
        )
        for decision in origin["decisions"] or []:
            entities.append(
                {
                    "type": "Decision",
                    "id": decision.get("id"),
                    "name": decision.get("title"),
                }
            )
        sources.extend(citations_to_sources(origin["citations"]))
        notes.extend(origin["gaps"])
        confidence = origin["confidence"]

    return envelope(
        summary=(
            f"{timeline['path']} changed {timeline['change_count']} times; "
            f"{len(coupling['coupled'])} files change alongside it."
        ),
        entities=entities,
        sources=sources,
        subgraph=subgraph_payload(timeline["graph"]),
        notes=notes,
        actions=[
            "Review the most recent change before editing.",
            "Expect tests to cover the coupled files as a unit.",
        ],
        confidence=confidence,
    )


def assess_file_risk(
    file_path: str,
    repository_id: str = DEFAULT_REPOSITORY_ID,
    limit: int = 25,
) -> Dict[str, Any]:
    """Churn, contributors and coupled files for a path, to judge edit risk."""
    target = validate_identifier(file_path, "file_path")
    repository = validate_identifier(repository_id, "repository_id")

    graph_name, denied = _graph_for_repository(repository)
    if denied is not None:
        return denied
    churn = _forensics.churn_ranking(
        repository, path_prefix=target, limit=clamp(limit), graph_name=graph_name
    )
    if not churn["files"]:
        return refusal(
            f"No ingested history matches '{target}' in {repository}.",
            notes=["Ingest the repository before relying on forensics for it."],
        )

    hotspots = churn["hotspots"] or churn["files"]
    hottest = hotspots[0]
    contributors = _forensics.module_history(
        repository, path_prefix=target, limit=1, graph_name=graph_name
    )["contributors"]

    notes = [
        f"Highest churn here: {hottest['path']} ({hottest['changes']} changes).",
        f"{len(churn['files'])} tracked files match this path.",
    ]
    if churn["files"][0].get("is_test"):
        notes.append(
            "The most-changed match is a test file, which often means the interface "
            "it covers is still settling."
        )

    return envelope(
        summary=f"{len(churn['files'])} tracked files under '{target}'.",
        entities=[
            {"type": "File", "id": row["file_id"], "name": row["path"]}
            for row in churn["files"][:15]
        ]
        + [
            {"type": "Person", "id": person["author_id"], "name": person["author"]}
            for person in contributors[:8]
        ],
        notes=notes,
        actions=[
            "Review prior changes by the most active contributor.",
            "Prefer a small change with a focused test.",
        ],
    )


def describe_file(file_id: str) -> Dict[str, Any]:
    """Describe a file from the documentation its authors wrote.

    ``file_id`` is the graph node id of the form ``repo_<name>::<path>``.
    """
    graph_name, denied = _graph_for_file_id(file_id)
    if denied is not None:
        return denied
    result = _forensics.describe_file(file_id, graph_name=graph_name)

    if result is None:
        return refusal(
            f"No ingested history for '{file_id}'.",
            notes=[
                "file_id must be the graph node id, e.g. "
                "repo_falkordb_falkordb::src/redis/redis.c"
            ],
        )

    provenance = result["provenance"]
    origin = provenance["origin"]
    origin_note = (
        f"Description written by: {origin}"
        + (f" ({provenance['model']})" if provenance["model"] else "")
    )

    return envelope(
        summary=(
            f"{result['path']} ({result['language']}): "
            f"{result['summary'] or 'no summary'}"
        ),
        entities=[
            {"type": "File", "id": result["file_id"], "name": result["path"]}
        ]
        + [
            {"type": "Symbol", "id": f"{result['file_id']}::{name}", "name": name}
            for name in result["symbols"][:15]
        ],
        notes=[
            result["staleness_reason"],
            origin_note,
        ],
        actions=[
            "Call describe_symbol for a listed symbol to get its signature and doc comment."
        ],
        confidence="stale" if result["stale"] else "supported",
    )


def describe_symbol(symbol_name: str, file_id: str = "") -> Dict[str, Any]:
    """Explain one function, type or method from its authored documentation.

    Returns every match when a name is shared, each with its container, rather
    than silently choosing one.
    """
    name = validate_identifier(symbol_name, "symbol_name")
    graph_name = ""
    if file_id:
        graph_name, denied = _graph_for_file_id(file_id)
        if denied is not None:
            return denied
    result = _forensics.describe_symbol(name, file_id=file_id, graph_name=graph_name)

    if result["match_count"] == 0:
        return refusal(
            f"No ingested declaration named '{name}'.",
            notes=[
                "Only exported declarations are recorded, so private helpers and "
                "items in files excluded by the repository filters will not appear.",
            ],
        )

    matches = result["matches"]
    first = matches[0]
    # The signature and doc comment are the answer, so each entity carries its
    # own detail rather than only an identifier.
    entities = [
        {
            "type": "Symbol",
            "id": match["symbol_id"],
            "name": match["name"],
            "kind": match["kind"],
            "signature": match["signature"],
            "doc_comment": match["doc_comment"],
            "documented": match["documented"],
            "line": match["line"],
            "visibility": match["visibility"],
            "container": match["container"],
            "file_id": match["file_id"],
            "path": match["path"],
            "changes_since_docs": match["changes_since_docs"],
            "recent_history": match["recent_history"],
        }
        for match in matches
    ]
    for match in matches:
        if match["file_id"]:
            entities.append(
                {"type": "File", "id": match["file_id"], "name": match["path"]}
            )

    documented = [m for m in matches if m["documented"]]
    summary = (
        f"{first['kind']} `{first['container']}::{first['name']}`"
        if first["container"]
        else f"{first['kind']} `{first['name']}`"
    )
    if first["path"]:
        summary += f" in {first['path']}:{first['line']}"
    if first["doc_comment"]:
        summary += f" — {first['doc_comment'][:200]}"
    else:
        summary += " — no doc comment"

    return envelope(
        summary=summary,
        entities=entities,
        notes=list(result["notes"])
        + [
            f"{len(documented)} of {len(matches)} match(es) carry a doc comment."
        ],
        actions=[
            "Open the file at the reported line and read the implementation.",
            "Use trace_change_origin on the file to see why it changed.",
        ],
        confidence="partial" if not documented else "supported",
    )


def get_repo_dependency_impact(
    repository_id: str = DEFAULT_REPOSITORY_ID,
) -> Dict[str, Any]:
    """Cross-repository blast radius for an ingested repository."""
    repository = validate_identifier(repository_id, "repository_id")
    graph_name, denied = _graph_for_repository(repository)
    if denied is not None:
        return denied
    dependencies = _forensics.investigation_brief(
        repository, graph_name=graph_name
    )["dependency_blast_radius"]

    if not dependencies:
        return refusal(f"No declared repository dependencies recorded for '{repository}'.")

    return envelope(
        summary=f"{repository} has {len(dependencies)} declared dependent repositories.",
        entities=[
            {"type": "Repository", "id": item["id"], "name": item["name"]}
            for item in dependencies
        ],
        notes=[
            "Dependencies are read from manifest text. No dependency repository "
            "was cloned, scanned or ingested.",
            "This is one hop of recorded edges, not a resolved build graph.",
        ],
        actions=["Check each dependency's changelog before changing a shared interface."],
    )


_TOOL_SPECS = (
    (
        "get_architecture_context",
        "Get architecture context",
        "Summary of a service, repository or decision: owners, dependencies, linked "
        "decisions, and the source documents behind them.",
        get_architecture_context,
    ),
    (
        "find_owner_and_expertise",
        "Find owner and expertise",
        "Accountable team, maintainers and experienced contributors for a system.",
        find_owner_and_expertise,
    ),
    (
        "trace_technical_decision",
        "Trace technical decision",
        "Rationale, alternatives, decision makers and evidence for a decision.",
        trace_technical_decision,
    ),
    (
        "assess_change_impact",
        "Assess change impact",
        "Bounded two-hop dependency analysis for a service, including associated incidents.",
        assess_change_impact,
    ),
    (
        "get_onboarding_context",
        "Get onboarding context",
        "First-week learning path, owned systems, people and reading for a team.",
        get_onboarding_context,
    ),
    (
        "search_architecture_evidence",
        "Search architecture evidence",
        "Ranked source-linked graph entities matching a narrow text query.",
        search_architecture_evidence,
    ),
    (
        "trace_change_origin",
        "Trace change origin",
        "Who changed a file (file_id is a 'repo_<name>::<path>' node id), when, in which "
        "pull request, and which files historically change with it.",
        trace_change_origin,
    ),
    (
        "assess_file_risk",
        "Assess file risk",
        "Change churn, contributors and coupled files for a path, to judge how risky an edit is.",
        assess_file_risk,
    ),
    (
        "get_repo_dependency_impact",
        "Get repository dependency impact",
        "Cross-repository blast radius for an ingested repository, bounded to recorded edges.",
        get_repo_dependency_impact,
    ),
    (
        "describe_file",
        "Describe a file",
        "What a file's authors documented about it, its public symbols, and whether that "
        "description is still current. file_id is a 'repo_<name>::<path>' node id.",
        describe_file,
    ),
    (
        "describe_symbol",
        "Describe a declaration",
        "Explain one function, type or method from its doc comment and signature, with "
        "the file and line it lives in. Returns every match when a name is shared.",
        describe_symbol,
    ),
)


# Tools that change the graph. Separate from _TOOL_SPECS because they carry
# different annotations and a different disclosure: a client that trusts
# readOnlyHint has to be able to tell these apart before it runs one.
_WRITE_TOOL_SPECS = (
    (
        "ingest_repository",
        "Ingest a repository",
        "Queue a repository ingestion and return a job id straight away. The scan "
        "clones the repository in a sandbox, reads its history and files, and "
        "writes the code to a graph belonging to that repository alone. It runs "
        "for minutes, so poll get_ingest_job until the status is done or failed. "
        "Re-running is safe: every write merges on a stable id, so a second "
        "ingest updates rather than duplicates.",
        enqueue_repository_ingest,
    ),
    (
        "get_ingest_job",
        "Report an ingestion job",
        "Report the current state of an ingestion job: its status, the stage it "
        "has reached, and the counts ingested so far.",
        get_ingest_job,
    ),
)

WRITE_DISCLOSURE = (
    "This tool CHANGES the knowledge graph. It needs a write token, and every "
    "answer drawn from this repository will reflect the ingest afterwards. "
    "Re-running is safe: each write merges on a stable id, so a second ingest "
    "updates what is already there rather than duplicating it. It removes "
    "nothing, so a file deleted upstream since the last scan stays in the graph "
    "as a stale node. Confirm with a human before ingesting."
)


def register_tools(server) -> None:
    """Attach every tool to an MCPServer instance."""
    for name, title, description, handler in _TOOL_SPECS:
        server.tool(
            name=name,
            title=title,
            description=f"{description}\n\n{ADVISORY_DISCLOSURE}",
            annotations=READ_ONLY,
        )(handler)

    for name, title, description, handler in _WRITE_TOOL_SPECS:
        server.tool(
            name=name,
            title=title,
            description=f"{description}\n\n{WRITE_DISCLOSURE}",
            annotations=WRITES,
        )(handler)