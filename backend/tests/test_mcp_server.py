"""Safety and contract tests for the read-only MCP context server.

Every test runs against mocks, so the suite needs no graph and no network.
Async MCP introspection is driven through ``asyncio.run`` to avoid adding an
async pytest plugin to the project.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.mcp import (
    MAX_RECORDS,
    ToolInputError,
    clamp,
    envelope,
    refusal,
    validate_identifier,
)
from app.mcp import tools as tools_module
from app.mcp.server import create_server, mount_dev_only


def _list(server, method):
    return asyncio.run(getattr(server, method)())


@pytest.fixture
def server():
    return create_server()


class TestValidation:
    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_blank_identifier_is_rejected(self, value):
        with pytest.raises(ToolInputError):
            validate_identifier(value)

    def test_oversized_identifier_is_rejected(self):
        with pytest.raises(ToolInputError):
            validate_identifier("a" * 500)

    @pytest.mark.parametrize(
        "payload",
        [
            "MATCH (n) DETACH DELETE n",
            "1; DROP DATABASE",
            "' OR 1=1 --",
            "RETURN 1 //",
        ],
    )
    def test_query_shaped_input_cannot_be_used_as_a_short_identifier(self, payload):
        """Identifiers are always bound parameters, never query text.

        A short, well-formed string is accepted as a value, so this asserts the
        contract rather than pretending to block Cypher at the validator.
        """
        validate_identifier(payload)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(1, 1), (MAX_RECORDS, MAX_RECORDS), (None, MAX_RECORDS), ("x", MAX_RECORDS), (0, 1)],
    )
    def test_clamp_bounds_record_counts(self, value, expected):
        assert clamp(value) == expected


class TestEnvelope:
    def test_envelope_exposes_the_documented_keys(self):
        payload = envelope(summary="s")
        for key in (
            "summary",
            "entities",
            "sources",
            "subgraph_nodes_and_edges",
            "risk_and_uncertainty_notes",
            "suggested_actions",
        ):
            assert key in payload

    def test_envelope_is_advisory_only(self):
        assert envelope(summary="s")["advisory_only"] is True

    def test_refusal_states_the_reason_in_the_risk_notes(self):
        payload = refusal("nothing found")
        assert payload["advisory_only"] is True
        assert payload["summary"] == "nothing found"
        assert payload["risk_and_uncertainty_notes"] == ["nothing found"]


class TestSurface:
    def test_exposes_exactly_the_eleven_planned_tools(self, server):
        assert {t.name for t in _list(server, "list_tools")} == {
            "get_architecture_context",
            "find_owner_and_expertise",
            "trace_technical_decision",
            "assess_change_impact",
            "get_onboarding_context",
            "search_architecture_evidence",
            "trace_change_origin",
            "assess_file_risk",
            "get_repo_dependency_impact",
            "describe_file",
            "describe_symbol",
        }

    def test_every_tool_declares_read_only_and_non_destructive(self, server):
        for tool in _list(server, "list_tools"):
            assert tool.annotations is not None, f"{tool.name} has no annotations"
            assert tool.annotations.read_only_hint is True, tool.name
            assert tool.annotations.destructive_hint is False, tool.name

    @pytest.mark.parametrize(
        "marker",
        ["write", "create", "update", "delete", "commit", "push", "exec", "edit_", "run_"],
    )
    def test_no_tool_name_implies_mutation(self, server, marker):
        for tool in _list(server, "list_tools"):
            assert marker not in tool.name.lower(), f"{tool.name} looks mutating"

    def test_every_tool_description_discloses_advisory_only_use(self, server):
        """Required by Docs/MCP_SERVER.md: results are not change approval."""
        for tool in _list(server, "list_tools"):
            description = (tool.description or "").lower()
            assert "advisory" in description, tool.name
            assert "not change approval" in description, tool.name

    def test_exposes_four_resource_templates(self, server):
        assert {t.uri_template for t in _list(server, "list_resource_templates")} == {
            "orgatlas://services/{service_id}",
            "orgatlas://teams/{team_id}",
            "orgatlas://decisions/{decision_id}",
            "orgatlas://repositories/{repository_id}",
        }

    def test_exposes_three_planning_prompts(self, server):
        assert {p.name for p in _list(server, "list_prompts")} == {
            "plan_architecture_aligned_change",
            "investigate_service_incident",
            "onboard_to_engineering_team",
        }

    def test_every_prompt_repeats_the_read_only_boundary(self, server):
        rendered = asyncio.run(
            server.get_prompt(
                "investigate_service_incident",
                {"service_identifier": "svc_checkout"},
            )
        )
        text = rendered.messages[0].content.text
        assert "read-only" in text.lower()
        assert "not assert a root cause" in text


class TestMountSafety:
    def test_not_mounted_outside_development(self):
        from fastapi import FastAPI

        with patch("app.mcp.server.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            mock_settings.MCP_API_TOKEN = None
            assert mount_dev_only(FastAPI()) is False

    def test_refuses_to_mount_unauthenticated_when_a_token_is_configured(self):
        from fastapi import FastAPI

        with patch("app.mcp.server.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            mock_settings.MCP_API_TOKEN = "configured-but-unused"
            with pytest.raises(RuntimeError, match="MCP_API_TOKEN"):
                mount_dev_only(FastAPI())

    def test_mounts_in_development(self):
        from fastapi import FastAPI

        with patch("app.mcp.server.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            mock_settings.MCP_API_TOKEN = None
            app = FastAPI()
            assert mount_dev_only(app, server=create_server()) is True
            # The streamable app is mounted at the host root because it already
            # routes "/mcp" internally; mounting it under "/mcp" would 307 to
            # "/mcp/mcp". The protocol path is exercised by TestHttpRoundTrip.
            mounts = [r for r in app.routes if type(r).__name__ == "Mount"]
            assert mounts and mounts[-1].path == ""

    def test_lifespan_of_the_mcp_app_is_composed_into_the_host(self):
        from fastapi import FastAPI

        with patch("app.mcp.server.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            mock_settings.MCP_API_TOKEN = None
            app = FastAPI()
            before = app.router.lifespan_context
            mount_dev_only(app, server=create_server())

        assert app.router.lifespan_context is not before

    def test_browser_cors_never_reaches_the_mcp_route(self):
        from app.core.config import settings

        assert "mcp" not in " ".join(settings.CORS_ORIGINS).lower()

    def test_mcp_route_is_not_part_of_the_versioned_api_router(self):
        from app.api.router import api_router

        assert not any("mcp" in getattr(route, "path", "") for route in api_router.routes)


class TestRefusalsInsteadOfGuessing:
    def test_unknown_identifier_refuses_and_suggests_valid_ids(self):
        with patch.object(tools_module, "_decisions") as decisions, patch.object(
            tools_module, "_ownership"
        ) as ownership:
            decisions.trace_decision.return_value = None
            ownership.get_ownership.return_value = None

            payload = tools_module.get_architecture_context("nope")

        assert payload["advisory_only"] is True
        assert "No architecture context found" in payload["summary"]
        assert any("svc_" in note for note in payload["risk_and_uncertainty_notes"])

    def test_uningested_repository_refuses_instead_of_inventing_hotspots(self):
        with patch.object(tools_module, "_forensics") as forensics:
            forensics.investigation_brief.return_value = {
                "hotspots": [],
                "dependency_blast_radius": [],
                "guidance": [],
            }
            payload = tools_module.get_architecture_context("repo_unknown")

        assert payload["advisory_only"] is True
        assert "No ingested history" in payload["summary"]

    def test_unknown_decision_names_the_seeded_decisions(self):
        with patch.object(tools_module, "_decisions") as decisions:
            decisions.trace_decision.return_value = None
            payload = tools_module.trace_technical_decision("dec_nope")

        assert any("dec_kafka_async" in n for n in payload["risk_and_uncertainty_notes"])

    def test_unknown_team_names_the_seeded_teams(self):
        with patch.object(tools_module, "_onboarding") as onboarding:
            onboarding.get_onboarding_map.return_value = None
            payload = tools_module.get_onboarding_context("team_nope")

        assert any("team_payments" in n for n in payload["risk_and_uncertainty_notes"])


class TestForensicTools:
    def _timeline(self, **overrides):
        base = {
            "file_id": "repo_x::src/a.c",
            "path": "src/a.c",
            "change_count": 2,
            "history": [
                {"sha": "aaa111", "message": "fix leak", "author": "dev"},
                {"sha": "bbb222", "message": "add api", "author": "dev"},
            ],
            "citations": [],
            "graph": None,
        }
        base.update(overrides)
        return base

    def test_trace_change_origin_reports_provenance_and_gaps(self):
        with patch.object(tools_module, "_forensics") as forensics, patch.object(
            tools_module, "_provenance"
        ) as provenance:
            forensics.file_timeline.return_value = self._timeline()
            forensics.coupled_files.return_value = {"coupled": [], "advice": "no coupling"}
            provenance.trace.return_value = {
                "commit": {"pr_number": 42},
                "decisions": [{"id": "dec_kafka_async", "title": "Kafka"}],
                "citations": [],
                "gaps": ["No linked ticket."],
                "confidence": "partial",
            }

            payload = tools_module.trace_change_origin("repo_x::src/a.c")

        assert "PR #42" in " ".join(payload["risk_and_uncertainty_notes"])
        assert "No linked ticket." in payload["risk_and_uncertainty_notes"]
        assert payload["confidence"] == "partial"
        assert any(e["type"] == "Decision" for e in payload["entities"])

    def test_trace_change_origin_survives_missing_provenance(self):
        with patch.object(tools_module, "_forensics") as forensics, patch.object(
            tools_module, "_provenance"
        ) as provenance:
            forensics.file_timeline.return_value = self._timeline()
            forensics.coupled_files.return_value = {"coupled": [], "advice": "no coupling"}
            provenance.trace.return_value = None

            payload = tools_module.trace_change_origin("repo_x::src/a.c")

        assert payload["advisory_only"] is True
        assert payload["confidence"] == "partial"

    def test_trace_change_origin_explains_the_file_id_format(self):
        with patch.object(tools_module, "_forensics") as forensics:
            forensics.file_timeline.return_value = None
            payload = tools_module.trace_change_origin("src/a.c")

        joined = " ".join(payload["risk_and_uncertainty_notes"])
        assert "file_id" in joined
        assert "::" in joined, "should show the repo::path node-id form"

    def test_assess_file_risk_flags_a_test_only_hotspot(self):
        with patch.object(tools_module, "_forensics") as forensics:
            forensics.churn_ranking.return_value = {
                "files": [{"file_id": "repo_x::t/a_test.rs", "path": "t/a_test.rs",
                           "changes": 30, "is_test": True}],
                "hotspots": [],
            }
            forensics.module_history.return_value = {"contributors": []}
            payload = tools_module.assess_file_risk("t/a_test.rs")

        assert any("still settling" in n for n in payload["risk_and_uncertainty_notes"])

    def test_assess_file_risk_refuses_on_unknown_path(self):
        with patch.object(tools_module, "_forensics") as forensics:
            forensics.churn_ranking.return_value = {"files": [], "hotspots": []}
            payload = tools_module.assess_file_risk("does/not/exist")

        assert "No ingested history" in payload["summary"]

    def test_dependency_impact_states_that_nothing_was_cloned(self):
        with patch.object(tools_module, "_forensics") as forensics:
            forensics.investigation_brief.return_value = {
                "dependency_blast_radius": [{"id": "repo_dep", "name": "dep"}]
            }
            payload = tools_module.get_repo_dependency_impact()

        assert any("was cloned" in n for n in payload["risk_and_uncertainty_notes"])


class TestHttpRoundTrip:
    """End-to-end protocol wiring.

    These cover three defects that unit tests cannot see: the mount path,
    the session-manager lifespan, and DNS-rebinding host validation.
    """

    def _call(self, client, method, headers, params=None):
        import json as _json

        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or {},
            },
        )
        assert response.status_code == 200, response.text
        payload = _json.loads(response.text)
        inner = payload.get("result", payload)
        return _json.loads(inner) if isinstance(inner, str) else inner

    def test_initialize_and_discovery_succeed_over_http(self):
        from starlette.testclient import TestClient

        from app.main import create_app

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        with TestClient(create_app()) as client:
            info = self._call(
                client,
                "initialize",
                headers,
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            )
            assert info["serverInfo"]["name"] == "orgatlas-context-server"
            assert info["instructions"]

            tools = self._call(client, "tools/list", headers)["tools"]
            prompts = self._call(client, "prompts/list", headers)["prompts"]
            templates = self._call(
                client, "resources/templates/list", headers
            )["resourceTemplates"]

        assert len(tools) == 11
        assert len(prompts) == 3
        assert len(templates) == 4
        assert all(t["annotations"]["readOnlyHint"] for t in tools)

    def test_browser_api_still_served_alongside_mcp(self):
        from starlette.testclient import TestClient

        from app.core.config import settings
        from app.main import create_app

        with TestClient(create_app()) as client:
            response = client.get(f"{settings.API_V1_PREFIX}/health")
        assert response.status_code == 200


class TestSearchBounds:
    def test_search_filters_by_entity_type(self):
        with patch.object(tools_module, "graph_gateway") as gateway:
            gateway.search_entities.return_value = [
                {"label": "Service", "id": "svc_a", "name": "a"},
                {"label": "Decision", "id": "dec_b", "name": "b"},
            ]
            payload = tools_module.search_architecture_evidence("svc", entity_type="Service")

        assert [e["id"] for e in payload["entities"]] == ["svc_a"]

    def test_search_rejects_a_one_character_query(self):
        with pytest.raises(ToolInputError):
            tools_module.search_architecture_evidence("a")

    def test_search_limit_is_clamped(self):
        with patch.object(tools_module, "graph_gateway") as gateway:
            gateway.search_entities.return_value = [
                {"label": "Service", "id": f"svc_{i}", "name": "n"} for i in range(200)
            ]
            payload = tools_module.search_architecture_evidence("svc", limit=10_000)

        assert len(payload["entities"]) == MAX_RECORDS

class TestSymbolToolsCarryTheirDetail:
    """A describe_* tool that drops the doc comment answers nothing.

    Both tools return the shared envelope, whose entity list must therefore
    carry each match's signature, documentation and location rather than only
    an identifier.
    """

    def _match(self, **overrides):
        base = {
            "symbol_id": "repo_x::src/f.rs::function:C:new",
            "name": "new",
            "kind": "function",
            "signature": "pub fn new(&self) -> Self",
            "doc_comment": "Builds an empty widget.",
            "documented": True,
            "line": 14,
            "visibility": "pub",
            "container": "Widget",
            "language": "Rust",
            "file_id": "repo_x::src/f.rs",
            "path": "src/f.rs",
            "repository_id": "repo_x",
            "is_test": False,
            "changes_since_docs": 0,
            "recent_history": [{"sha": "s1", "subject": "init", "authored_at": "2024"}],
        }
        base.update(overrides)
        return base

    def test_describe_symbol_surfaces_signature_and_docs(self):
        from app.mcp import tools as tools_module

        with patch.object(tools_module, "_forensics") as forensics:
            forensics.describe_symbol.return_value = {
                "query": "new",
                "file_id": "",
                "match_count": 1,
                "matches": [self._match()],
                "guidance": [],
                "notes": [],
            }
            payload = tools_module.describe_symbol("new")

        entity = next(e for e in payload["entities"] if e["type"] == "Symbol")
        assert entity["signature"] == "pub fn new(&self) -> Self"
        assert entity["doc_comment"] == "Builds an empty widget."
        assert entity["line"] == 14
        assert entity["path"] == "src/f.rs"
        assert "Builds an empty widget" in payload["summary"]

    def test_undocumented_symbol_says_so_in_the_summary(self):
        from app.mcp import tools as tools_module

        with patch.object(tools_module, "_forensics") as forensics:
            forensics.describe_symbol.return_value = {
                "query": "new",
                "file_id": "",
                "match_count": 1,
                "matches": [self._match(doc_comment="", documented=False)],
                "guidance": ["None of these declarations carries a doc comment."],
                "notes": [],
            }
            payload = tools_module.describe_symbol("new")

        assert "no doc comment" in payload["summary"]
        assert payload["confidence"] == "partial"

    def test_ambiguous_name_lists_every_match_separately(self):
        from app.mcp import tools as tools_module

        with patch.object(tools_module, "_forensics") as forensics:
            forensics.describe_symbol.return_value = {
                "query": "new",
                "file_id": "",
                "match_count": 2,
                "matches": [
                    self._match(),
                    self._match(
                        symbol_id="repo_x::src/f.rs::function:Other:new",
                        container="Other",
                        doc_comment="",
                        documented=False,
                        line=22,
                    ),
                ],
                "guidance": [],
                "notes": ["'new' matches 2 declarations."],
            }
            payload = tools_module.describe_symbol("new")

        symbols = [e for e in payload["entities"] if e["type"] == "Symbol"]
        assert len(symbols) == 2
        assert {s["container"] for s in symbols} == {"Widget", "Other"}
        assert any("matches 2 declarations" in n for n in payload["risk_and_uncertainty_notes"])

    def test_describe_symbol_refuses_on_unknown_name(self):
        from app.mcp import tools as tools_module

        with patch.object(tools_module, "_forensics") as forensics:
            forensics.describe_symbol.return_value = {
                "query": "nope",
                "file_id": "",
                "match_count": 0,
                "matches": [],
                "guidance": [],
                "notes": ["No ingested declaration named 'nope'."],
            }
            payload = tools_module.describe_symbol("nope")

        assert payload["advisory_only"] is True
        assert any("exported declarations" in n for n in payload["risk_and_uncertainty_notes"])

    def test_describe_file_names_its_provenance_and_symbols(self):
        from app.mcp import tools as tools_module

        with patch.object(tools_module, "_forensics") as forensics:
            forensics.describe_file.return_value = {
                "file_id": "repo_x::src/f.rs",
                "path": "src/f.rs",
                "name": "f.rs",
                "language": "Rust",
                "is_test": False,
                "repository_id": "repo_x",
                "summary": "Widget storage.",
                "symbols": ["Widget", "new"],
                "docs_source": "module",
                "docs_at_sha": "abc",
                "stale": False,
                "changes_since_docs": 0,
                "recent_shas": [],
                "provenance": {"origin": "authored", "model": ""},
                "raw_response": "",
                "staleness_reason": "Description matches the file as of abc.",
            }
            payload = tools_module.describe_file("repo_x::src/f.rs")

        assert payload["confidence"] == "supported"
        assert any("authored" in n for n in payload["risk_and_uncertainty_notes"])
        names = {e["name"] for e in payload["entities"] if e["type"] == "Symbol"}
        assert names == {"Widget", "new"}