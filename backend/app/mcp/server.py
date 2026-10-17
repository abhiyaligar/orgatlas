"""MCP server construction and the environment-aware mount.

Safety constraints:

* **Production requires authentication.** ``/mcp`` mounts outside development
  only when ``MCP_API_TOKEN`` is set and a verifier accepts it. Without a token
  the route is absent, rather than present and open.
* **Development stays convenient but not silent.** The route mounts without a
  token in development and says so loudly in the log, so an unauthenticated
  socket is never a surprise.
* The route is never added to ``CORS_ORIGINS``, so a browser client cannot reach
  it in any environment. MCP is reached by agents, not by pages.
* Token comparison is constant-time and no token is ever logged. See
  ``app.mcp.auth``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.core.config import settings
from app.mcp import INSTRUCTIONS, SERVER_NAME, SERVER_VERSION
from app.mcp.auth import auth_enabled
from app.mcp.auth import describe as describe_auth
from app.mcp.middleware import BearerAuthMiddleware
from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources
from app.mcp.tools import register_tools

logger = logging.getLogger(__name__)

MCP_MOUNT_PATH = "/mcp"
DEV_ENVIRONMENTS = {"development", "dev", "local"}

# DNS-rebinding protection stays enabled. Only loopback origins may reach the
# route; "testserver" is the host Starlette's TestClient presents.
# Both the portless and any-port forms are listed: a client connecting to
# "localhost" with no port was being refused as a rebinding attempt.
DEV_TRANSPORT_SECURITY = TransportSecuritySettings(
    allowed_hosts=[
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "[::1]",
        "[::1]:*",
        "testserver",
    ],
    allowed_origins=["http://localhost", "http://localhost:*", "http://127.0.0.1", "http://127.0.0.1:*"],
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


def _transport_security(is_development: bool) -> TransportSecuritySettings:
    """Which Host and Origin headers this server will answer to.

    In production the published host must be stated explicitly. Left empty,
    every request is refused as a DNS-rebinding attempt -- which is the correct
    failure, but a confusing one for an operator who has not configured it yet,
    so the warning below says so at startup.
    """
    if is_development:
        return DEV_TRANSPORT_SECURITY

    hosts = [
        host.strip()
        for host in (settings.MCP_ALLOWED_HOSTS or "").replace(";", ",").split(",")
        if host.strip()
    ]
    if not hosts:
        logger.warning(
            "MCP_ALLOWED_HOSTS is empty: every MCP request will be refused as a "
            "DNS-rebinding attempt. Set it to the host MCP is published at."
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"https://{host}" for host in hosts],
    )


def mount_dev_only(app, server: Optional[MCPServer] = None) -> bool:
    """Mount the MCP ASGI app on a FastAPI instance in development only.

    Returns True when mounted.
    """
    environment = (settings.ENVIRONMENT or "").strip().lower()
    is_development = environment in DEV_ENVIRONMENTS

    if not auth_enabled() and not is_development:
        # Fail closed: outside development an unauthenticated context server
        # would expose decision history and repository structure to anyone who
        # can reach the port. Absent is better than open.
        logger.warning(
            "MCP route not mounted: ENVIRONMENT=%s requires MCP_API_TOKEN.", environment
        )
        return False

    resolved = server or create_server()


    # ``streamable_http_app()`` returns a Starlette app whose only route is
    # already "/mcp". Mounting it under "/mcp" again would produce "/mcp/mcp",
    # so it is mounted at the host root and requests for /mcp fall through to
    # it. API routes are registered before this call and keep precedence.
    streamable_kwargs = dict(
        json_response=True,
        stateless_http=True,
        # In production the host header must match the published origin, which
        # is what stops a DNS-rebinding attack from reaching the socket through
        # a browser. In development localhost is allowed.
        transport_security=_transport_security(is_development),
    )
    streamable = resolved.streamable_http_app(**streamable_kwargs)

    # One block of middleware guards every method, rather than the SDK being
    # handed a provider that covers only the ones it knows to check. The
    # lifespan is taken from the inner app, since the wrapper has no router.
    served = BearerAuthMiddleware(streamable) if auth_enabled() else streamable

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
    app.mount("/", served)

    summary = describe_auth()
    if summary["authenticated"]:
        logger.warning(
            "MCP context server mounted at %s (authenticated, %d token(s), scope %s).",
            MCP_MOUNT_PATH,
            summary["token_count"],
            summary["scope"],
        )
    else:
        logger.warning(
            "MCP context server mounted at %s WITHOUT authentication "
            "(ENVIRONMENT=%s). Do not expose this beyond localhost.",
            MCP_MOUNT_PATH,
            environment,
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