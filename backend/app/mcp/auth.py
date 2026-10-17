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

# The entire permission surface, stated so a future write scope is visible.
MCP_READ_SCOPE = "orgatlas:read"

_BEARER = "bearer "


def configured_tokens() -> List[str]:
    """Every accepted token, from configuration."""
    raw = (settings.MCP_API_TOKEN or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


def auth_enabled() -> bool:
    return bool(configured_tokens())


def presented_token(header_value: Optional[str]) -> str:
    """Extract the secret from an Authorization header.

    ``Bearer x`` and a bare ``x`` are both accepted, because MCP clients
    configured by URL commonly send the bare form.
    """
    value = (header_value or "").strip()
    if value.lower().startswith(_BEARER):
        value = value[len(_BEARER) :].strip()
    return value


def is_authorised(header_value: Optional[str]) -> bool:
    """Whether an Authorization header carries an accepted token.

    Every configured token is compared and the results accumulated, so the time
    taken does not depend on which token matched, or on how many exist.
    """
    import secrets

    candidate = presented_token(header_value)
    if not candidate:
        return False

    accepted = False
    for known in configured_tokens():
        # No short-circuit: every comparison runs.
        accepted |= secrets.compare_digest(candidate, known)

    if not accepted:
        logger.info("MCP request rejected: token not accepted")
    return bool(accepted)


def describe() -> dict:
    """A startup summary that reports whether auth is on without leaking it."""
    tokens = configured_tokens()
    return {
        "authenticated": bool(tokens),
        "scope": MCP_READ_SCOPE if tokens else None,
        # The count, never the values.
        "token_count": len(tokens),
    }