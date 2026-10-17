"""Bearer-token authentication for the MCP surface.

The properties under test are the ones that decide whether this is a real
boundary or decoration: an unauthenticated request must be refused, a wrong
token must be refused, a correct one must not be, and the route must be absent
rather than open when no token is configured.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.mcp.auth import (
    MCP_READ_SCOPE,
    auth_enabled,
    configured_tokens,
    describe,
    is_authorised,
    presented_token,
)
from app.mcp.server import MCP_MOUNT_PATH

TOKEN = "test-token-abc123"
JSONRPC_HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture(autouse=True)
def _restore():
    before = (settings.ENVIRONMENT, settings.MCP_API_TOKEN, settings.MCP_ALLOWED_HOSTS)
    yield
    settings.ENVIRONMENT, settings.MCP_API_TOKEN, settings.MCP_ALLOWED_HOSTS = before


def _client(token, env="production", hosts="orgatlas.example.com"):
    from app.main import create_app

    settings.ENVIRONMENT = env
    settings.MCP_API_TOKEN = token
    settings.MCP_ALLOWED_HOSTS = hosts
    app = create_app()
    return TestClient(app, base_url=f"http://{hosts}", raise_server_exceptions=False)


def _tools_list(client, authorization=None):
    headers = dict(JSONRPC_HEADERS)
    if authorization is not None:
        headers["Authorization"] = authorization
    with client:
        return client.post(
            MCP_MOUNT_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers=headers,
        )


# --- token handling ---------------------------------------------------------


def test_a_bearer_prefix_is_stripped():
    assert presented_token("Bearer abc") == "abc"
    assert presented_token("bearer abc") == "abc"
    assert presented_token("abc") == "abc"


def test_the_correct_token_is_authorised(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_TOKEN", TOKEN, raising=False)
    assert is_authorised(f"Bearer {TOKEN}")
    assert is_authorised(TOKEN)


def test_a_wrong_token_is_not(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_TOKEN", TOKEN, raising=False)
    assert not is_authorised("Bearer wrong")
    assert not is_authorised(TOKEN[:-1])
    assert not is_authorised(TOKEN + "x")


def test_no_header_is_not_authorised(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_TOKEN", TOKEN, raising=False)
    assert not is_authorised(None)
    assert not is_authorised("")
    assert not is_authorised("   ")


def test_several_tokens_are_accepted_for_rotation(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_TOKEN", f"old-token,{TOKEN}", raising=False)
    assert configured_tokens() == ["old-token", TOKEN]
    assert is_authorised("Bearer old-token")
    assert is_authorised(f"Bearer {TOKEN}")


def test_a_description_reports_the_count_and_never_the_token(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_TOKEN", TOKEN, raising=False)
    summary = describe()
    assert summary == {"authenticated": True, "scope": MCP_READ_SCOPE, "token_count": 1}
    assert TOKEN not in str(summary)


def test_auth_is_off_when_no_token_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_TOKEN", "", raising=False)
    assert not auth_enabled()
    assert describe()["authenticated"] is False


# --- the mounted route ------------------------------------------------------


def test_a_correct_token_reaches_the_tools():
    response = _tools_list(_client(TOKEN), f"Bearer {TOKEN}")
    assert response.status_code == 200
    assert "tools" in response.json()["result"]


def test_a_bare_token_without_the_scheme_is_accepted():
    response = _tools_list(_client(TOKEN), TOKEN)
    assert response.status_code == 200


def test_a_wrong_token_is_refused_with_a_challenge():
    response = _tools_list(_client(TOKEN), "Bearer wrong")
    assert response.status_code == 401
    assert "www-authenticate" in {key.lower() for key in response.headers}
    assert MCP_READ_SCOPE in response.headers["www-authenticate"]


def test_a_request_with_no_token_at_all_is_refused():
    response = _tools_list(_client(TOKEN))
    assert response.status_code == 401


def test_production_without_a_token_does_not_mount_the_route():
    """Absent beats open. The route must not exist unauthenticated."""
    response = _tools_list(_client(None))
    assert response.status_code == 404


def test_the_rejection_does_not_say_why():
    """Distinguishing unknown from malformed is free information for an attacker."""
    wrong = _tools_list(_client(TOKEN), "Bearer wrong").json()
    absent = _tools_list(_client(TOKEN)).json()
    assert wrong == absent


def test_development_mounts_without_a_token():
    response = _tools_list(_client(None, env="development", hosts="localhost"))
    assert response.status_code == 200


def test_every_mcp_method_is_guarded():
    """The middleware sits outside the SDK, so a method added later is covered too."""
    client = _client(TOKEN)
    with client:
        for method in ("tools/list", "resources/list", "prompts/list", "initialize"):
            response = client.post(
                MCP_MOUNT_PATH,
                json={"jsonrpc": "2.0", "id": 1, "method": method},
                headers={**JSONRPC_HEADERS, "Authorization": "Bearer wrong"},
            )
            assert response.status_code == 401, f"{method} was reachable unauthenticated"