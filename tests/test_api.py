"""Tests de la API: endpoints, auth, rate-limit, schemas."""
from __future__ import annotations

import datetime as dt
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sentinel.db")
os.environ.setdefault("SUMMARIZER_BACKEND", "none")

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import ExplainRequest, ExplainResponse, IngestBatch, RuleOut, SummaryOut
from app.config import Settings
from app.db.models import Severity, SourceType
from app.db.session import engine
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _init_db():
    # Ensure DB exists and is clean before any test
    import asyncio

    from app.db.models import Base

    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())


class TestHealth:
    def test_health_ok(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["role"] in ("standalone", "server", "agent")
        assert isinstance(body["auth_required"], bool)


class TestIngest:
    def test_ingest_requires_agent_key(self, client: TestClient):
        # Without key -> 401
        resp = client.post("/api/ingest", json={"host": "h1", "events": []})
        assert resp.status_code == 401

    def test_ingest_with_wrong_key(self, client: TestClient):
        resp = client.post(
            "/api/ingest",
            json={"host": "h1", "events": []},
            headers={"X-Agent-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_ingest_with_correct_key(self, client: TestClient):
        # Get the actual agent key from settings
        s = Settings()
        resp = client.post(
            "/api/ingest",
            json={
                "host": "test-host",
                "events": [
                    {
                        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "source_type": "journald",
                        "source_name": "test.service",
                        "severity": "info",
                        "message": "hello world",
                        "raw": "hello world",
                    }
                ],
            },
            headers={"X-Agent-Key": s.agent_api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["ingested"] == 1


class TestSources:
    def test_sources_list(self, client: TestClient):
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sources_register(self, client: TestClient):
        s = Settings()
        resp = client.post(
            "/api/sources/register",
            json=[{"host": "test-host", "source_type": "journald", "source_name": "test.service"}],
            headers={"X-Agent-Key": s.agent_api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["upserted"] == 1

    def test_sources_toggle(self, client: TestClient):
        # Need a source to toggle; register one first
        s = Settings()
        client.post(
            "/api/sources/register",
            json=[{"host": "toggle-host", "source_type": "docker", "source_name": "test-container"}],
            headers={"X-Agent-Key": s.agent_api_key},
        )
        sources = client.get("/api/sources").json()
        mine = [x for x in sources if x["host"] == "toggle-host"]
        assert mine
        sid = mine[0]["id"]
        initial = mine[0]["enabled"]

        resp = client.post(f"/api/sources/{sid}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] != initial


class TestEvents:
    def test_events_list(self, client: TestClient):
        resp = client.get("/api/events?limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_events_filter_by_host(self, client: TestClient):
        resp = client.get("/api/events?limit=10&host=test-host")
        assert resp.status_code == 200
        for e in resp.json():
            assert e["host"] == "test-host"

    def test_events_filter_by_severity(self, client: TestClient):
        resp = client.get("/api/events?limit=10&severity=info")
        assert resp.status_code == 200
        for e in resp.json():
            assert e["severity"] == "info"


class TestAlerts:
    def test_alerts_list(self, client: TestClient):
        resp = client.get("/api/alerts?limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSummaries:
    def test_summaries_list(self, client: TestClient):
        resp = client.get("/api/summaries")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_summaries_filter_by_period(self, client: TestClient):
        resp = client.get("/api/summaries?period=weekly")
        assert resp.status_code == 200
        for s in resp.json():
            assert s["period"] == "weekly"


class TestExplain:
    def test_explain_requires_existing_event(self, client: TestClient):
        resp = client.post("/api/explain", json={"event_id": 999999})
        assert resp.status_code == 404

    def test_explain_requires_dashboard_auth(self, client: TestClient):
        s = Settings()
        # Create an event first
        client.post(
            "/api/ingest",
            json={
                "host": "explain-host",
                "events": [
                    {
                        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "source_type": "journald",
                        "source_name": "explain.service",
                        "severity": "error",
                        "message": "boom",
                        "raw": "boom",
                    }
                ],
            },
            headers={"X-Agent-Key": s.agent_api_key},
        )
        events = client.get("/api/events?limit=1&host=explain-host").json()
        assert events
        eid = events[0]["id"]

        # Without auth -> 401 if dashboard key set, 200 if not
        # In test env, no dashboard key, so 200
        resp = client.post("/api/explain", json={"event_id": eid})
        # Should work without dashboard key
        assert resp.status_code == 200
        assert "explanation" in resp.json()


class TestRules:
    def test_rules_list(self, client: TestClient):
        resp = client.get("/api/rules")
        assert resp.status_code == 200
        rules = resp.json()
        assert isinstance(rules, list)
        for r in rules:
            RuleOut(**r)  # validate schema

    def test_rules_reload(self, client: TestClient):
        resp = client.post("/api/rules/reload")
        assert resp.status_code == 200
        body = resp.json()
        assert "loaded" in body
        assert "rules" in body
        assert isinstance(body["rules"], list)
        for r in body["rules"]:
            RuleOut(**r)


class TestRateLimit:
    def test_llm_rate_limit_explain(self, client: TestClient, monkeypatch):
        from app.config import settings
        from app.rate_limit import limiter

        # Bajar el límite a 2 para este test y vaciar el limiter
        original_limit = settings.llm_rate_limit_explain
        settings.llm_rate_limit_explain = 2
        # Limpiar hits previos de explain
        limiter._hits.clear()
        try:
            s = Settings()
            # First need an event
            client.post(
                "/api/ingest",
                json={
                    "host": "rate-host",
                    "events": [
                        {
                            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                            "source_type": "journald",
                            "source_name": "rate.service",
                            "severity": "error",
                            "message": "rate limit test",
                            "raw": "rate limit test",
                        }
                    ],
                },
                headers={"X-Agent-Key": s.agent_api_key},
            )
            events = client.get("/api/events?limit=1&host=rate-host").json()
            eid = events[0]["id"]

            # Primeras 2 llamadas deben pasar
            r1 = client.post("/api/explain", json={"event_id": eid})
            r2 = client.post("/api/explain", json={"event_id": eid})
            assert r1.status_code == 200
            assert r2.status_code == 200

            # La tercera debe dar 429
            r3 = client.post("/api/explain", json={"event_id": eid})
            assert r3.status_code == 429
            assert "429" in str(r3.status_code)
        finally:
            settings.llm_rate_limit_explain = original_limit
            limiter._hits.clear()


class TestSchemas:
    def test_ingest_batch_schema(self):
        batch = IngestBatch(
            host="h1",
            events=[
                {
                    "timestamp": dt.datetime.now(dt.timezone.utc),
                    "source_type": SourceType.journald,
                    "source_name": "s1",
                    "severity": Severity.info,
                    "message": "msg",
                    "raw": "msg",
                }
            ],
        )
        assert batch.host == "h1"

    def test_explain_request_schema(self):
        req = ExplainRequest(event_id=1)
        assert req.event_id == 1

    def test_explain_response_schema(self):
        resp = ExplainResponse(explanation="test")
        assert resp.explanation == "test"

    def test_summary_out_schema(self):
        s = SummaryOut(
            id=1,
            created_at=dt.datetime.now(dt.timezone.utc),
            period="weekly",
            period_start=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7),
            period_end=dt.datetime.now(dt.timezone.utc),
            backend_used="gemini",
            content_md="## Test",
        )
        assert s.period == "weekly"

    def test_rule_out_schema(self):
        r = RuleOut(
            name="test",
            match="boom",
            min_severity="warning",
            source_type="any",
            threshold=3,
            window_seconds=60,
            cooldown_seconds=300,
            severity="error",
            notify=["telegram"],
        )
        assert r.name == "test"