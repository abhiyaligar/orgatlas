"""A write token is required, and the annotation has to tell the truth.

The context server was read-only by construction until this. Two things now
change it, and both are easy to undo by accident:

* a tool that declares ``readOnlyHint`` while it writes, so a client that trusts
  the hint runs it without asking anyone
* a write capability gated by the same shared secret as reads, so every token
  that can be handed to a read-only agent can also rewrite the graph
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.mcp import READ_ONLY, WRITES
from app.mcp.auth import (
    MCP_READ_SCOPE,
    MCP_WRITE_SCOPE,
    describe,
    scope_for_token,
)
from app.mcp.scope import (
    InsufficientScope,
    has_scope,
    require_write,
    reset_scope,
    set_scope,
)
from app.mcp.server import create_server


@pytest.fixture()
def tokens():
    read = settings.MCP_API_TOKEN
    write = settings.MCP_WRITE_API_TOKEN
    settings.MCP_API_TOKEN = "read-a,read-b"
    settings.MCP_WRITE_API_TOKEN = "write-a"
    yield
    settings.MCP_API_TOKEN = read
    settings.MCP_WRITE_API_TOKEN = write


class TestScopes:
    def test_a_read_token_grants_read(self, tokens):
        assert scope_for_token("read-a") == MCP_READ_SCOPE

    def test_a_write_token_grants_write(self, tokens):
        assert scope_for_token("write-a") == MCP_WRITE_SCOPE

    def test_a_write_token_also_reads(self, tokens):
        """A client that may ingest has no use for a token that cannot read."""
        assert scope_for_token("write-a") == MCP_WRITE_SCOPE

    def test_rotation_is_accepted_for_reads(self, tokens):
        assert scope_for_token("read-b") == MCP_READ_SCOPE

    def test_an_unknown_token_is_refused(self, tokens):
        assert scope_for_token("nope") is None

    def test_an_empty_header_is_refused(self, tokens):
        assert scope_for_token("") is None
        assert scope_for_token(None) is None

    def test_the_bare_form_is_accepted(self, tokens):
        """MCP clients configured by URL commonly send the bare token."""
        assert scope_for_token("write-a") == MCP_WRITE_SCOPE

    def test_describe_reports_the_strongest_scope_without_leaking(self, tokens):
        summary = describe()

        assert summary["write_enabled"] is True
        assert summary["scope"] == MCP_WRITE_SCOPE
        assert "write-a" not in str(summary)


class TestRequireWrite:
    def test_a_read_caller_is_refused(self, tokens):
        token = set_scope(MCP_READ_SCOPE)
        try:
            with pytest.raises(InsufficientScope):
                require_write()
        finally:
            reset_scope(token)

    def test_a_write_caller_is_allowed(self, tokens):
        token = set_scope(MCP_WRITE_SCOPE)
        try:
            require_write()
        finally:
            reset_scope(token)

    def test_no_scope_at_all_is_refused(self, tokens):
        """A direct call with no middleware must not be treated as privileged."""
        assert has_scope(MCP_WRITE_SCOPE) is False
        with pytest.raises(InsufficientScope):
            require_write()

    def test_the_scope_is_cleared_afterwards(self, tokens):
        """A pooled worker must not serve the next caller the previous one's rights."""
        token = set_scope(MCP_WRITE_SCOPE)
        reset_scope(token)

        assert has_scope(MCP_WRITE_SCOPE) is False


class TestToolAnnotations:
    def test_the_write_tools_are_not_announced_as_read_only(self):
        tools = {t.name: t for t in create_server()._tool_manager.list_tools()}

        assert tools["ingest_repository"].annotations.read_only_hint is False
        assert tools["get_ingest_job"].annotations.read_only_hint is False

    def test_the_write_tools_announce_that_they_are_destructive(self):
        """True because the change is not something a later query takes back.

        Every answer drawn from that repository shifts once the ingest lands, and
        the generated documentation of every file rescanned is cleared. It does
        not delete anything, so the hint is about irreversibility, not removal.
        """
        tools = {t.name: t for t in create_server()._tool_manager.list_tools()}

        assert tools["ingest_repository"].annotations.destructive_hint is True

    def test_the_original_eleven_are_still_read_only(self):
        """Thirteen read now, but the original eleven must stay read-only.

        The two source tools were added later and read from object storage
        rather than the graph. Adding reads must not quietly widen the write
        boundary, so this still checks the original set explicitly.
        """
        tools = {t.name: t for t in create_server()._tool_manager.list_tools()}

        read_only = [
            name for name, tool in tools.items()
            if tool.annotations.read_only_hint and name
            not in {"ingest_repository", "get_ingest_job"}
        ]
        assert len(read_only) == 13

    def test_the_annotation_constants_say_what_they_are(self):
        assert READ_ONLY.read_only_hint is True
        assert WRITES.read_only_hint is False
        assert WRITES.destructive_hint is True

    def test_the_server_tells_a_client_it_is_no_longer_read_only(self):
        """The instructions were the promise; they have to match the tools."""
        from app.mcp import INSTRUCTIONS

        assert "any write capability" not in INSTRUCTIONS
        assert "ingest a repository" in INSTRUCTIONS
        assert "write token" in INSTRUCTIONS


class TestWriteToolGuards:
    def test_enqueue_refuses_a_read_caller_before_touching_the_database(self, tokens):
        from app.mcp.write_tools import enqueue_repository_ingest

        token = set_scope(MCP_READ_SCOPE)
        try:
            result = enqueue_repository_ingest("https://github.com/example/repo")
        finally:
            reset_scope(token)

        assert "write token" in str(result).lower()
        assert "job_id" not in result

    def test_polling_a_job_refuses_a_read_caller(self, tokens):
        from app.mcp.write_tools import get_ingest_job

        token = set_scope(MCP_READ_SCOPE)
        try:
            result = get_ingest_job(1)
        finally:
            reset_scope(token)

        assert "write token" in str(result).lower()
        assert "status" not in result

    def test_a_refusal_explains_itself_rather_than_crashing(self, tokens):
        """The SDK turns an exception into "Error executing tool".

        An agent that cannot tell a permissions problem from a crash cannot do
        anything sensible, so the reason has to survive to the caller.
        """
        from app.mcp.write_tools import enqueue_repository_ingest

        token = set_scope(MCP_READ_SCOPE)
        try:
            result = enqueue_repository_ingest("https://github.com/example/repo")
        finally:
            reset_scope(token)

        assert "write token" in result["summary"].lower()
        assert "MCP_WRITE_API_TOKEN" in result["summary"]
        assert result["risk_and_uncertainty_notes"]

    def test_a_non_http_url_is_refused_with_a_reason(self, tokens):
        from app.mcp.write_tools import enqueue_repository_ingest

        token = set_scope(MCP_WRITE_SCOPE)
        try:
            result = enqueue_repository_ingest("ftp://example.com/repo")
        finally:
            reset_scope(token)

        assert "http" in str(result).lower()

class TestOverRealHttp:
    """The unit tests cannot see this: the SDK runs a tool in a context that is
    not the one the ASGI middleware ran in. These go through the whole stack.
    """

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text-event-stream",
    }
    INITIALIZE = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }

    def _app(self, monkeypatch, write_token="", read_token="read-token"):
        from starlette.testclient import TestClient

        from app.main import create_app

        monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
        monkeypatch.setattr(settings, "MCP_API_TOKEN", read_token, raising=False)
        monkeypatch.setattr(settings, "MCP_WRITE_API_TOKEN", write_token, raising=False)
        monkeypatch.setattr(settings, "MCP_ALLOWED_HOSTS", "*", raising=False)
        return TestClient(create_app())

    def _call(self, client, token, name, arguments):
        headers = dict(self.HEADERS, Authorization=f"Bearer {token}")
        client.post("/mcp", headers=headers, json=self.INITIALIZE)
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        )
        return response.text

    def test_a_read_token_cannot_ingest(self, monkeypatch):
        with self._app(monkeypatch) as client:
            body = self._call(
                client,
                "read-token",
                "ingest_repository",
                {"repository_url": "https://github.com/example/repo"},
            )

        assert "write token" in body.lower()

    def test_the_refusal_reaches_the_caller_with_its_reason(self, monkeypatch):
        """Not "Error executing tool": an agent has to know what went wrong."""
        with self._app(monkeypatch) as client:
            body = self._call(
                client,
                "read-token",
                "ingest_repository",
                {"repository_url": "https://github.com/example/repo"},
            )

        assert "MCP_WRITE_API_TOKEN" in body
        assert "Error executing tool" not in body

    def test_a_write_token_reaches_the_tool(self, monkeypatch):
        """Proved with a URL the tool rejects, so nothing is ingested."""
        with self._app(monkeypatch, write_token="write-token") as client:
            body = self._call(
                client,
                "write-token",
                "ingest_repository",
                {"repository_url": "ftp://example.com/repo"},
            )

        assert "http or https" in body.lower()
        assert "write token" not in body.lower()

    def test_a_read_token_cannot_read_a_job(self, monkeypatch):
        with self._app(monkeypatch) as client:
            body = self._call(client, "read-token", "get_ingest_job", {"job_id": 1})

        assert "write token" in body.lower()

    def test_a_read_token_still_answers_read_tools(self, monkeypatch):
        """The read boundary is the point of the split; check it still opens."""
        with self._app(monkeypatch) as client:
            headers = dict(self.HEADERS, Authorization="Bearer read-token")
            client.post("/mcp", headers=headers, json=self.INITIALIZE)
            response = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                },
            )

        assert response.status_code == 200
        assert "get_architecture_context" in response.text

    def test_no_token_at_all_still_refuses_the_route(self, monkeypatch):
        """The split must not weaken the existing fail-closed behaviour."""
        with self._app(monkeypatch, read_token="", write_token="") as client:
            client.post("/mcp", headers=self.HEADERS, json=self.INITIALIZE)
            response = client.post("/mcp", headers=self.HEADERS, json=self.INITIALIZE)

        assert response.status_code == 404
