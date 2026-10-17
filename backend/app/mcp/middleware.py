"""ASGI middleware that guards the MCP route with a bearer token.

Kept as middleware rather than passed into the SDK because the installed SDK's
``streamable_http_app`` does not take a token provider, and because this way the
check is one readable block that applies to every method -- initialize, tools
list, resources, prompts -- rather than only to the ones someone remembered.

A rejected request gets a 401 and a challenge, and nothing else. The response
does not distinguish an unknown token from a malformed header, because that
distinction is free for an attacker to probe.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, MutableMapping

from app.mcp.auth import MCP_READ_SCOPE, is_authorised

logger = logging.getLogger(__name__)

Scope = MutableMapping
Receive = Callable[[], Awaitable[MutableMapping]]
Send = Callable[[MutableMapping], Awaitable[None]]

_UNAUTHENTICATED_BODY = (
    b'{"error":"unauthorized","error_description":"A valid bearer token is required."}'
)


class BearerAuthMiddleware:
    """Require a valid bearer token on every request that passes through."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            # Lifespan and websocket traffic carry no Authorization header.
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

        if not is_authorised(headers.get("authorization")):
            await self._reject(send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        logger.info("MCP request rejected: no valid bearer token")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_UNAUTHENTICATED_BODY)).encode("latin-1")),
                    (b"www-authenticate", f'Bearer scope="{MCP_READ_SCOPE}"'.encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHENTICATED_BODY})