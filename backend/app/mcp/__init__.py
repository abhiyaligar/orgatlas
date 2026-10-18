"""Read-only MCP context server for OrgAtlas.

The surface is advisory context only. Every tool is declared with
``read_only_hint=True`` and there is deliberately no tool that writes files,
edits code, runs shell commands, or mutates the graph or any database.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations

from app.core.config import settings

logger = logging.getLogger(__name__)

SERVER_NAME = "orgatlas-context-server"
SERVER_VERSION = "1.0.0"

INSTRUCTIONS = """
OrgAtlas exposes verified, source-backed architecture context for engineering
work. Use it before and during planning to understand what a change would touch.

What this server provides:
* who owns a system, and who has worked on it
* why an architectural decision was made, with its supporting evidence
* what depends on a service, and the blast radius of changing it
* for ingested repositories: who changed a file, when, and what changes together

What it cannot do:
* edit code, create tickets, or run commands. Nothing here changes a file
  outside the knowledge graph
* certainty. Results are advisory context, not change approval. Inspect the
  code, run the tests, and let a human decide.

Writing, and only when a write token is configured:
* ingest a repository, which reads code and writes it to the graph belonging to
  that repository alone. It replaces what a previous scan left there. It is the
  only write capability, and it never touches a database directly.
""".strip()

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# The opposite, for tools that ingest. read_only_hint is False and
# destructive_hint is True: an ingest replaces what a previous scan left
# for that repository, so a client that trusts these hints must ask a human
# before running one.
WRITES = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)

MAX_HOPS = 2
MAX_RECORDS = 50


class ToolInputError(ValueError):
    """Raised when a tool receives input it cannot safely act on."""


def validate_identifier(value: str, field: str = "identifier") -> str:
    """Accept only stable identifiers.

    Identifiers are used to build parameterised lookups, so anything that could
    look like a query fragment is rejected outright. This is belt-and-braces:
    no tool ever interpolates input into Cypher.
    """
    if not value or not isinstance(value, str):
        raise ToolInputError(f"{field} is required")
    cleaned = value.strip()
    if not cleaned:
        raise ToolInputError(f"{field} must not be blank")
    if len(cleaned) > 200:
        raise ToolInputError(f"{field} is too long")
    return cleaned


def clamp(limit: Optional[int]) -> int:
    """Bound any caller-supplied record limit to the enforced maximum."""
    try:
        value = int(limit) if limit is not None else MAX_RECORDS
    except (TypeError, ValueError):
        return MAX_RECORDS
    return max(1, min(value, MAX_RECORDS))


def refusal(reason: str, notes: List[str] | None = None, **extra: Any) -> Dict[str, Any]:
    """Return an explicit refusal in the standard response shape.

    ``notes`` extends ``risk_and_uncertainty_notes`` so guidance always lands in
    the contractual field rather than as an ad-hoc extra key.
    """
    payload: Dict[str, Any] = {
        "summary": reason,
        "entities": [],
        "sources": [],
        "subgraph_nodes_and_edges": {"nodes": [], "edges": [], "paths": []},
        "risk_and_uncertainty_notes": [reason, *(notes or [])],
        "suggested_actions": [],
        "advisory_only": True,
    }
    payload.update(extra)
    return payload


def envelope(
    summary: str,
    entities: List[Dict[str, Any]] | None = None,
    sources: List[Dict[str, Any]] | None = None,
    subgraph: Dict[str, Any] | None = None,
    notes: List[str] | None = None,
    actions: List[str] | None = None,
    confidence: str = "partial",
) -> Dict[str, Any]:
    """Build the six-part response contract every tool returns."""
    return {
        "summary": summary,
        "entities": entities or [],
        "sources": sources or [],
        "subgraph_nodes_and_edges": subgraph
        or {"nodes": [], "edges": [], "paths": []},
        "risk_and_uncertainty_notes": notes or [],
        "suggested_actions": actions or [],
        "confidence": confidence,
        "advisory_only": True,
    }


def citations_to_sources(citations: List[Any]) -> List[Dict[str, Any]]:
    """Convert Citation models into the MCP source shape."""
    sources: List[Dict[str, Any]] = []
    for citation in citations or []:
        sources.append(
            {
                "source_id": citation.source_id,
                "title": citation.title,
                "type": citation.type,
                "url": getattr(citation, "url", None),
                "excerpt": getattr(citation, "excerpt", None),
            }
        )
    return sources


def subgraph_payload(subgraph: Any) -> Dict[str, Any]:
    """Convert an EvidenceSubgraph into the MCP shape, tolerating None."""
    if subgraph is None:
        return {"nodes": [], "edges": [], "paths": []}
    return {
        "nodes": [node.model_dump() for node in getattr(subgraph, "nodes", [])],
        "edges": [edge.model_dump() for edge in getattr(subgraph, "edges", [])],
        "paths": getattr(subgraph, "paths", []) or [],
    }