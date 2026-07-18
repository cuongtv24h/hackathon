# === TASK:WP-010:START ===
"""Unit tests for WP-010 — Backend Runtime Scaffold & Package Normalization."""

from fastapi import FastAPI

from apps.api.core.settings import Settings


def test_app_import():
    """Verify the FastAPI application can be imported without side effects."""
    from apps.api.main import app  # noqa: F811

    assert isinstance(app, FastAPI)
    assert app.title == "HospitalAssistant"


def test_settings_defaults():
    """Verify Settings returns sensible defaults when no env vars are set."""
    s = Settings()
    assert s.app_name == "HospitalAssistant"
    assert s.debug is False
    assert s.api_prefix == "/api/v1"


def test_settings_env_override(monkeypatch):
    """Verify Settings respects HA_ prefixed environment variables."""
    monkeypatch.setenv("HA_APP_NAME", "TestApp")
    monkeypatch.setenv("HA_DEBUG", "true")
    monkeypatch.setenv("HA_API_PREFIX", "/test/v2")

    s = Settings()
    assert s.app_name == "TestApp"
    assert s.debug is True
    assert s.api_prefix == "/test/v2"
# === TASK:WP-010:END ===
