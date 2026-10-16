"""MCP server construction and the development-only mount.

Safety constraints:

* The ``/mcp`` route is mounted **only** when ``ENVIRONMENT`` is
  ``development``. It is absent entirely from preview and production rather
  than running unauthenticated there.
* The route is never added to ``CORS_ORIGINS``, so the browser client cannot
  reach it even in development.
* If an ``MCP_API_TOKEN`` is configured but no verifier is wired, startup
  fails loudly instead of silently serving an open endpoint.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.core.config import settings
from app.mcp import INSTRUCTIONS, SERVER_NAME, SERVER_VERSION
from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources
from app.mcp.tools import register_tools

logger = logging.getLogger(__name__)

MCP_MOUNT_PATH = "/mcp"
DEV_ENVIRONMENTS = {"development", "dev", "local"}

# DNS-rebinding protection stays enabled. Only loopback origins may reach the
# route; "testserver" is the host Starlette's TestClient presents.
DEV_TRANSPORT_SECURITY = TransportSecuritySettings(
    allowed_hosts=["localhost:*", "127.0.0.1:*", "[::1]:*", "testserver"],
    allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
)


def create_server() -> MCPServer:
    """Build the read-only OrgAtlas context server."""
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
    )
    register_tools(server)
    register_resources(server)
    register_prompts(server)
    return server


def mount_dev_only(app, server: Optional[MCPServer] = None) -> bool:
    """Mount the MCP ASGI app on a FastAPI instance in development only.

    Returns True when mounted.
    """
    environment = (settings.ENVIRONMENT or "").strip().lower()

    if environment not in DEV_ENVIRONMENTS:
        logger.info(
            "MCP route not mounted: ENVIRONMENT=%s. It is development-only.", environment
        )
        return False

    if settings.MCP_API_TOKEN:
        raise RuntimeError(
            "MCP_API_TOKEN is configured but /mcp mounts without authentication in "
            "development. Either set ENVIRONMENT to a non-development value or remove "
            "MCP_API_TOKEN until a verifier is implemented."
        )

    resolved = server or create_server()

    # ``streamable_http_app()`` returns a Starlette app whose only route is
    # already "/mcp". Mounting it under "/mcp" again would produce "/mcp/mcp",
    # so it is mounted at the host root and requests for /mcp fall through to
    # it. API routes are registered before this call and keep precedence.
    streamable = resolved.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=DEV_TRANSPORT_SECURITY,
    )

    # Starlette does not forward lifespan events to mounted applications, and
    # the MCP session manager needs its lifespan to be running before any
    # request is served. Compose it into the host application's lifespan.
    host_lifespan = app.router.lifespan_context
    inner_lifespan = streamable.router.lifespan_context

    @asynccontextmanager
    async def _combined_lifespan(scope):
        async with host_lifespan(scope):
            async with inner_lifespan(streamable):
                yield

    app.router.lifespan_context = _combined_lifespan
    app.mount("/", streamable)

    logger.warning(
        "MCP context server mounted unauthenticated at %s (development only).",
        MCP_MOUNT_PATH,
    )
    return True


def main() -> None:
    """Entry point for a stdio transport, used by local coding-agent hosts."""
    logging.basicConfig(level=logging.INFO)
    server = create_server()
    logger.info("Starting %s over stdio", SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()