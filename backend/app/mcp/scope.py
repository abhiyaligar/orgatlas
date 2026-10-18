"""The scope of the caller currently being served.

The ASGI middleware authenticates a request and puts its scope here, so a tool
can ask whether this caller may write. It is a context variable rather than an
argument because the tool signature is what an agent sees, and adding a scope
parameter to eleven read-only tools to satisfy two write tools would be noise.

A fresh context has no scope, which means an unauthenticated direct call is
treated as read-only. Failing closed matters more here than convenience: a
missing scope must never be the thing that lets a write through.
"""

from __future__ import annotations

from contextvars import ContextVar

from app.mcp.auth import MCP_READ_SCOPE, MCP_WRITE_SCOPE

_current_scope: ContextVar[str | None] = ContextVar("orgatlas_mcp_scope", default=None)


def set_scope(scope: str | None):
    """Record the caller's scope. Returns the token, to reset it afterwards."""
    return _current_scope.set(scope)


def reset_scope(token) -> None:
    _current_scope.reset(token)


def current_scope() -> str | None:
    return _current_scope.get()


def has_scope(required: str) -> bool:
    """Whether the caller holds a scope that satisfies the requirement."""
    held = _current_scope.get()
    if required == MCP_WRITE_SCOPE:
        return held == MCP_WRITE_SCOPE
    return held is not None


class InsufficientScope(PermissionError):
    """A caller asked for something their token does not permit."""


def require_write() -> None:
    """Refuse a write unless the caller presented a write token."""
    if not has_scope(MCP_WRITE_SCOPE):
        raise InsufficientScope(
            "This tool changes the knowledge graph and needs a write token. "
            "Configure MCP_WRITE_API_TOKEN on the server and send that token."
        )