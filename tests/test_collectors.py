"""Tests de collectors: base, docker, journald, discovery."""
from __future__ import annotations

import datetime as dt
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sentinel_collectors.db")
os.environ.setdefault("SUMMARIZER_BACKEND", "none")

import pytest

from app.collectors.base import RawEvent
from app.collectors.docker_collector import DockerCollector
from app.collectors.discovery import discover_sources
from app.config import Settings


class TestRawEvent:
    def test_raw_event_shape(self):
        """RawEvent es un TypedDict con los campos esperados."""
        event: RawEvent = {
            "timestamp": dt.datetime.now(dt.timezone.utc),
            "source_type": "journald",
            "source_name": "test.service",
            "severity": "info",
            "message": "hello",
            "raw": "hello",
        }
        assert event["source_type"] in ("journald", "docker")
        assert event["severity"] in ("debug", "info", "warning", "error", "critical")


class TestDockerCollector:
    def test_init_without_docker(self):
        """Collector se inicializa aunque Docker no esté disponible."""
        with patch("docker.DockerClient") as mock_client:
            mock_client.side_effect = Exception("no docker")
            collector = DockerCollector()
            assert collector._client is None

    def test_init_with_filters(self):
        collector = DockerCollector(container_filters=["immich", "proxmox"])
        assert collector.container_filters == ["immich", "proxmox"]

    def test_matches_filter_no_filters(self):
        collector = DockerCollector(container_filters=[])
        mock_container = MagicMock()
        mock_container.name = "anything"
        assert collector._matches_filter(mock_container) is True

    def test_matches_filter_with_filters(self):
        collector = DockerCollector(container_filters=["immich", "proxmox"])
        mock_container = MagicMock()
        mock_container.name = "immich-server"
        assert collector._matches_filter(mock_container) is True

        mock_container.name = "other-container"
        assert collector._matches_filter(mock_container) is False

    def test_guess_severity(self):
        from app.collectors.docker_collector import _guess_severity
        from app.db.models import Severity

        assert _guess_severity("CRITICAL: out of memory") == Severity.critical
        assert _guess_severity("FATAL error") == Severity.critical
        assert _guess_severity("ERROR: connection refused") == Severity.error
        assert _guess_severity("Exception traceback") == Severity.error
        assert _guess_severity("WARN: slow query") == Severity.warning
        assert _guess_severity("WARNING: disk space low") == Severity.warning
        assert _guess_severity("DEBUG: entering function") == Severity.debug
        assert _guess_severity("INFO: started") == Severity.info
        assert _guess_severity("just a message") == Severity.info


class TestDiscovery:
    @pytest.mark.asyncio
    async def test_discover_sources_no_docker_no_journald(self):
        """Cuando collect_journald y collect_docker son False, discover devuelve vacía."""
        from app.config import settings

        orig_j, orig_d = settings.collect_journald, settings.collect_docker
        try:
            settings.collect_journald = False
            settings.collect_docker = False
            sources = await discover_sources()
            assert sources == []
        finally:
            settings.collect_journald = orig_j
            settings.collect_docker = orig_d

    @pytest.mark.asyncio
    async def test_discover_sources_with_journald_only(self):
        """Si solo hay journald activo, solo devuelve unidades systemd."""
        from app.config import settings

        orig_j, orig_d = settings.collect_journald, settings.collect_docker
        try:
            settings.collect_journald = True
            settings.collect_docker = False
            with patch("app.collectors.discovery.discover_journald_units", new_callable=AsyncMock, return_value=["immich.service", "sshd.service"]):
                sources = await discover_sources()
                assert len(sources) == 2
                for t, n in sources:
                    assert t.value == "journald"
                    assert n in ("immich.service", "sshd.service")
        finally:
            settings.collect_journald = orig_j
            settings.collect_docker = orig_d

    @pytest.mark.asyncio
    async def test_discover_sources_with_docker_only(self):
        """Si solo hay docker activo, solo devuelve contenedores."""
        from app.config import settings

        orig_j, orig_d = settings.collect_journald, settings.collect_docker
        try:
            settings.collect_journald = False
            settings.collect_docker = True
            with patch("app.collectors.discovery.discover_docker_containers", new_callable=AsyncMock, return_value=["immich-server"]):
                sources = await discover_sources()
                assert len(sources) == 1
                t, n = sources[0]
                assert t.value == "docker"
                assert n == "immich-server"
        finally:
            settings.collect_journald = orig_j
            settings.collect_docker = orig_d


class TestJournaldCollector:
    @pytest.mark.asyncio
    async def test_journald_collector_imports(self):
        """Importar el collector no debe romperse aunque systemd no esté disponible."""
        from app.collectors.journald_collector import JournaldCollector

        # Just verify it can be instantiated
        collector = JournaldCollector()
        assert collector is not None

    @pytest.mark.asyncio
    async def test_journald_collector_streams(self):
        """Smoke test: collector puede crear un stream (mock de journalctl)."""
        from app.collectors.journald_collector import JournaldCollector

        collector = JournaldCollector()
        # Just verify the stream method exists and is async generator
        import inspect
        assert inspect.isasyncgenfunction(collector.stream)


class TestConfigIntegration:
    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("DOCKER_CONTAINERS", "immich proxmox")
        monkeypatch.setenv("JOURNALD_UNITS", "immich.service sshd.service")
        s = Settings()
        assert "immich" in s.docker_containers
        assert "proxmox" in s.docker_containers
        assert "immich.service" in s.journald_units
        assert "sshd.service" in s.journald_units

    def test_settings_json_arrays(self, monkeypatch):
        monkeypatch.setenv("DOCKER_CONTAINERS", '["immich", "proxmox"]')
        s = Settings()
        assert s.docker_containers == ["immich", "proxmox"]