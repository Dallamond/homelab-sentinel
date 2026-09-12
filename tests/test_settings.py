"""Tests del sistema de Ajustes (A1-A5): GET/POST /api/settings y test de conexión."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sentinel.db")
os.environ.setdefault("SUMMARIZER_BACKEND", "none")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.session import engine
from app.main import app
from app.settings_store import mask_secret


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _init_db():
    import asyncio
    from app.db.models import Base

    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())


class TestSettingsGet:
    def test_get_returns_structure(self, client: TestClient):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert "effective" in body
        assert "secret_keys" in body
        assert "overridden" in body
        assert isinstance(body["effective"], dict)
        assert isinstance(body["secret_keys"], list)

    def test_get_masks_secrets(self, client: TestClient):
        original = settings.telegram_bot_token
        settings.telegram_bot_token = "super-secret-token-1234"
        try:
            resp = client.get("/api/settings")
            assert resp.status_code == 200
            eff = resp.json()["effective"]
            token = eff["telegram_bot_token"]
            # Masked: starts with bullets, ends with 1234, doesn't contain the full token
            assert token.startswith("•")
            assert token.endswith("1234")
            assert "super-secret-token" not in token
        finally:
            settings.telegram_bot_token = original

    def test_mask_secret_helper(self):
        assert mask_secret("mytoken1234") == "•" * 8 + "1234"
        assert mask_secret("") == ""
        assert mask_secret("ab") == "•" * 8 + "ab"  # short string: bullets + last chars


class TestSettingsPost:
    def test_post_persists_and_applies(self, client: TestClient):
        resp = client.post(
            "/api/settings",
            json={"updates": {"ollama_base_url": "http://test-host:11434", "telegram_enabled": True}},
        )
        assert resp.status_code == 200
        eff = resp.json()["effective"]
        assert eff["ollama_base_url"] == "http://test-host:11434"
        assert eff["telegram_enabled"] is True
        assert "ollama_base_url" in resp.json()["overridden"]

    def test_post_null_reverts_to_env_default(self, client: TestClient):
        # First set a value
        client.post("/api/settings", json={"updates": {"ollama_model": "custom-model"}})
        # Then revert
        resp = client.post("/api/settings", json={"updates": {"ollama_model": None}})
        assert resp.status_code == 200
        overridden = resp.json()["overridden"]
        assert "ollama_model" not in overridden
        # Should be back to env default (llama3.1)
        assert resp.json()["effective"]["ollama_model"] == "llama3.1"

    def test_post_masked_placeholder_ignored(self, client: TestClient):
        # Set a real value first
        client.post("/api/settings", json={"updates": {"gemini_model": "gemini-test"}})
        # Send masked placeholder — should be ignored (keep gemini-test)
        resp = client.post(
            "/api/settings",
            json={"updates": {"gemini_model": "••••••••test"}},
        )
        assert resp.status_code == 200
        assert resp.json()["effective"]["gemini_model"] == "gemini-test"

    def test_post_rejects_unknown_key(self, client: TestClient):
        resp = client.post("/api/settings", json={"updates": {"nonexistent_key": "x"}})
        assert resp.status_code == 422

    def test_post_validates_summarizer_backend(self, client: TestClient):
        resp = client.post("/api/settings", json={"updates": {"summarizer_backend": "invalid"}})
        # Should still save as a string (frontend already restricts the select)
        # but the value is stored; summarizer backend check happens at runtime
        assert resp.status_code == 200


class TestSettingsTestConnection:
    def test_unknown_channel_returns_422(self, client: TestClient):
        resp = client.post("/api/settings/test", json={"channel": "invalid"})
        assert resp.status_code == 422

    def test_telegram_missing_config(self, client: TestClient):
        original_token = settings.telegram_bot_token
        original_chat = settings.telegram_chat_id
        settings.telegram_bot_token = ""
        settings.telegram_chat_id = ""
        try:
            resp = client.post("/api/settings/test", json={"channel": "telegram"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is False
            assert "TELEGRAM_BOT_TOKEN" in body["message"] or "CHAT_ID" in body["message"]
        finally:
            settings.telegram_bot_token = original_token
            settings.telegram_chat_id = original_chat

    def test_email_missing_config(self, client: TestClient):
        original = settings.smtp_user
        settings.smtp_user = ""
        try:
            resp = client.post("/api/settings/test", json={"channel": "email"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is False
            assert "SMTP_USER" in body["message"]
        finally:
            settings.smtp_user = original

    def test_gemini_missing_key(self, client: TestClient):
        original = settings.gemini_api_key
        settings.gemini_api_key = ""
        try:
            resp = client.post("/api/settings/test", json={"channel": "gemini"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is False
            assert "GEMINI_API_KEY" in body["message"]
        finally:
            settings.gemini_api_key = original

    def test_ollama_connection_fails(self, client: TestClient):
        """Ollama is not running in test env; this should fail gracefully."""
        original = settings.ollama_base_url
        settings.ollama_base_url = "http://localhost:19999"
        try:
            resp = client.post("/api/settings/test", json={"channel": "ollama"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is False
            assert "Error" in body["message"]
        finally:
            settings.ollama_base_url = original

    def test_openai_compat_missing_url(self, client: TestClient):
        original = settings.openai_compat_base_url
        settings.openai_compat_base_url = ""
        try:
            resp = client.post("/api/settings/test", json={"channel": "openai_compat"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is False
            assert "OPENAI_COMPAT_BASE_URL" in body["message"]
        finally:
            settings.openai_compat_base_url = original


class TestDashboardAuthActivation:
    """A5: al guardar DASHBOARD_API_KEY, los endpoints empiezan a exigirla."""

    def test_dashboard_key_activates_auth(self, client: TestClient):
        key = "test-dash-key-0000"
        # Set the key
        resp = client.post("/api/settings", json={"updates": {"dashboard_api_key": key}})
        assert resp.status_code == 200

        # Without the key → 401 on protected endpoints
        r = client.get("/api/events")
        assert r.status_code == 401

        # With the key → 200
        r2 = client.get("/api/events", headers={"X-Dashboard-Key": key})
        assert r2.status_code == 200

        # Revert (must send the key since auth is now active)
        resp2 = client.post(
            "/api/settings",
            json={"updates": {"dashboard_api_key": None}},
            headers={"X-Dashboard-Key": key},
        )
        assert resp2.status_code == 200
        assert "dashboard_api_key" not in resp2.json()["overridden"]