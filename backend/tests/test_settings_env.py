"""CORS_ORIGINS has to be settable the way a hosting dashboard sets it.

``CORS_ORIGINS`` is the only list-valued setting, and pydantic-settings parses a
list from an environment variable as JSON. That means the obvious
``CORS_ORIGINS=https://app.example.com`` refuses to start the service with a
SettingsError, which is exactly what happened on the first Render deploy.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _origins(monkeypatch, raw):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    return Settings().CORS_ORIGINS


def test_a_single_bare_origin_is_accepted(monkeypatch):
    """The value a dashboard makes you type, with no JSON quoting."""
    assert _origins(monkeypatch, "https://app.example.com") == [
        "https://app.example.com"
    ]


def test_a_comma_separated_list_is_accepted(monkeypatch):
    assert _origins(monkeypatch, "https://a.example.com,https://b.example.com") == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_spaces_after_the_commas_are_ignored(monkeypatch):
    assert _origins(monkeypatch, "https://a.example.com, https://b.example.com") == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_a_json_array_still_works(monkeypatch):
    """A value copied out of a JSON env file must not stop working."""
    assert _origins(monkeypatch, '["https://a.example.com"]') == [
        "https://a.example.com"
    ]


def test_an_empty_entry_is_dropped_rather_than_becoming_an_empty_origin(monkeypatch):
    """An empty string in allow_origins silently matches nothing."""
    assert _origins(monkeypatch, "https://a.example.com/,") == ["https://a.example.com/"]


def test_a_blank_value_yields_no_origins(monkeypatch):
    assert _origins(monkeypatch, "   ") == []


def test_the_local_defaults_are_still_there_when_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    origins = Settings().CORS_ORIGINS

    assert "http://localhost:5173" in origins


def test_an_origin_is_kept_exactly_as_given(monkeypatch):
    """No silent normalisation: a trailing slash or a port is the caller's call."""
    assert _origins(monkeypatch, "http://localhost:3000") == ["http://localhost:3000"]


def test_the_setting_is_reachable_from_the_environment_not_only_a_file(monkeypatch):
    """The service on Render has no .env at all, so this is the real path."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://orgatlas-dev-web.onrender.com")

    settings = Settings()

    assert settings.ENVIRONMENT == "production"
    assert settings.CORS_ORIGINS == ["https://orgatlas-dev-web.onrender.com"]