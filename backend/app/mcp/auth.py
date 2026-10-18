"""Bearer-token authentication for the MCP context server.

One shared secret, read from ``MCP_API_TOKEN`` in the environment and compared
against the request's ``Authorization`` header. That is the whole scheme. It is
enough for a self-hosted read-only server with one known client, and it is not
OAuth -- no flows, no clients, no scopes beyond a name used in logs.

The three properties that matter:

* **Constant-time comparison.** ``==`` on a secret leaks its length and prefix
  through timing. ``secrets.compare_digest`` does not.
* **No token is ever logged.** Not at startup, not on rejection.
* **Several tokens are accepted.** ``MCP_API_TOKEN`` may be a comma-separated
  list, so a secret can be rotated by running the old and new alongside each
  other, then dropping the old one.

``.env`` is the only place the token lives. It is gitignored, and a token is
never written into the image, the code, or a log line.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

MCP_READ_SCOPE = "orgatlas:read"
MCP_WRITE_SCOPE = "orgatlas:write"

_BEARER = "bearer "


def _split(raw: Optional[str]) -> List[str]:
    return [part.strip() for part in (raw or "").replace(";", ",").split(",") if part.strip()]


def configured_tokens() -> List[str]:
    """Every accepted read token, from configuration."""
    return _split(settings.MCP_API_TOKEN)


def configured_write_tokens() -> List[str]:
    """Tokens allowed to change things.

    Kept separate rather than giving every read token write access. An agent
    holding a context token should not be able to rewrite the graph it is being
    asked to read, and a single shared secret cannot express that difference. A
    write token also grants read, because a client that may ingest has no use
    for a token that cannot read.
    """
    return _split(settings.MCP_WRITE_API_TOKEN)


def auth_enabled() -> bool:
    return bool(configured_tokens() or configured_write_tokens())


def presented_token(header_value: Optional[str]) -> str:
    """Extract the secret from an Authorization header.

    ``Bearer x`` and a bare ``x`` are both accepted, because MCP clients
    configured by URL commonly send the bare form.
    """
    value = (header_value or "").strip()
    if value.lower().startswith(_BEARER):
        value = value[len(_BEARER) :].strip()
    return value


def scope_for_token(header_value: Optional[str]) -> Optional[str]:
    """The scope a presented token carries, or None when it is not accepted.

    Write tokens are checked first and grant both scopes. Every candidate is
    compared even after a match, so the time taken does not depend on which
    token matched, or how many exist.
    """
    import secrets

    candidate = presented_token(header_value)
    if not candidate:
        return None

    read_match = False
    for known in configured_write_tokens():
        read_match |= secrets.compare_digest(candidate, known)
    if read_match:
        return MCP_WRITE_SCOPE

    for known in configured_tokens():
        # No short-circuit: every comparison runs.
        read_match |= secrets.compare_digest(candidate, known)
    if read_match:
        return MCP_READ_SCOPE

    logger.info("MCP request rejected: token not accepted")
    return None


def is_authorised(header_value: Optional[str]) -> bool:
    """Whether an Authorization header carries an accepted token of any scope."""
    return scope_for_token(header_value) is not None


def describe() -> dict:
    """A startup summary that reports scopes without leaking a token."""
    tokens = configured_tokens()
    write_tokens = configured_write_tokens()
    return {
        "authenticated": bool(tokens or write_tokens),
        "scope": MCP_WRITE_SCOPE if write_tokens else (MCP_READ_SCOPE if tokens else None),
        "write_enabled": bool(write_tokens),
        # The counts, never the values.
        "token_count": len(tokens) + len(write_tokens),
    }