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
        """An ingest replaces the previous scan of the same repository."""
        tools = {t.name: t for t in create_server()._tool_manager.list_tools()}

        assert tools["ingest_repository"].annotations.destructive_hint is True

    def test_the_original_eleven_are_still_read_only(self):
        tools = {t.name: t for t in create_server()._tool_manager.list_tools()}

        read_only = [
            name for name, tool in tools.items()
            if tool.annotations.read_only_hint and name
            not in {"ingest_repository", "get_ingest_job"}
        ]
        assert len(read_only) == 11

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
            with pytest.raises(InsufficientScope):
                enqueue_repository_ingest("https://github.com/example/repo")
        finally:
            reset_scope(token)

    def test_polling_a_job_refuses_a_read_caller(self, tokens):
        from app.mcp.write_tools import get_ingest_job

        token = set_scope(MCP_READ_SCOPE)
        try:
            with pytest.raises(InsufficientScope):
                get_ingest_job(1)
        finally:
            reset_scope(token)

    def test_a_non_http_url_is_refused_with_a_reason(self, tokens):
        from app.mcp.write_tools import enqueue_repository_ingest

        token = set_scope(MCP_WRITE_SCOPE)
        try:
            result = enqueue_repository_ingest("ftp://example.com/repo")
        finally:
            reset_scope(token)

        assert "http" in str(result).lower()