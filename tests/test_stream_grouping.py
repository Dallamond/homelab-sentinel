"""Tests de TracebackMerger: agrupación de tracebacks multilínea en un solo evento."""
from __future__ import annotations

import datetime as dt

from app.collectors.base import RawEvent
from app.db.models import Severity, SourceType
from app.stream_grouping import TracebackMerger

_TS = dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.timezone.utc)


def _evt(message: str, severity: Severity = Severity.error, source: str = "myapp") -> RawEvent:
    return RawEvent(
        timestamp=_TS,
        source_type=SourceType.docker,
        source_name=source,
        severity=severity,
        message=message,
        raw=message,
    )


class TestTracebackMerger:
    def test_normal_events_pass_through(self):
        merger = TracebackMerger()
        e = _evt("INFO: started", Severity.info)
        out = list(merger.feed(e))
        assert len(out) == 1
        assert out[0]["message"] == "INFO: started"

    def test_single_line_traceback_passthrough(self):
        """Un solo 'Traceback (most recent call last):' sin continuación."""
        merger = TracebackMerger()
        e1 = _evt("Traceback (most recent call last):", Severity.error)
        out = list(merger.feed(e1))
        assert out == []  # buffering, nothing yielded yet
        # Flush explicit
        out = list(merger.flush())
        assert len(out) == 1
        assert "Traceback" in out[0]["message"]

    def test_multiline_traceback_is_merged(self):
        merger = TracebackMerger()
        lines = [
            "Traceback (most recent call last):",
            '  File "/app/main.py", line 10, in <module>',
            '    raise ValueError("boom")',
            "ValueError: boom",
        ]
        out = []
        for line in lines:
            out.extend(merger.feed(_evt(line)))
        # No events yielded until complete (the last line is column-0 → complete)
        # After all lines, we expect 1 merged event
        assert len(out) == 1
        merged = out[0]
        assert merged["message"] == "\n".join(lines)
        assert merged["severity"] == Severity.error

    def test_severity_is_max_of_lines(self):
        merger = TracebackMerger()
        lines = [
            "Traceback (most recent call last):",       # error
            "  File \"/app/main.py\", line 10",          # warning
            "    x += 1",                                # debug
            "NameError: x not defined",                 # critical
        ]
        out = []
        for line in lines:
            sev = Severity.warning if "File" in line else (Severity.debug if "x +=" in line else Severity.critical if "NameError" in line else Severity.error)
            out.extend(merger.feed(_evt(line, severity=sev)))
        assert len(out) == 1
        assert out[0]["severity"] == Severity.critical

    def test_traceback_source_change_flushes_pending(self):
        """Cambio de fuente a mitad de traceback → flush parcial."""
        merger = TracebackMerger()
        lines_a = [
            "Traceback (most recent call last):",
            '  File "/app/a.py", line 1, in run',
        ]
        out = []
        for line in lines_a:
            out.extend(merger.feed(_evt(line, source="app-a")))
        # pending in buffer, nothing yielded
        assert out == []
        # New source appears
        out.extend(merger.feed(_evt("INFO: normal from B", Severity.info, source="app-b")))
        # Should flush partial traceback + pass-through the new event
        assert len(out) == 2
        assert "Traceback" in out[0]["message"]
        assert out[0]["source_name"] == "app-a"
        assert out[1]["source_name"] == "app-b"

    def test_new_traceback_flushes_previous(self):
        """Un traceback nuevo cierra el anterior y lo emite."""
        merger = TracebackMerger()
        lines_a = [
            "Traceback (most recent call last):",
            '  File "/app/x.py", line 5',
            "RuntimeError: fail",
        ]
        all_out = []
        for line in lines_a:
            all_out.extend(merger.feed(_evt(line)))
        # After the loop, the first traceback was completed and yielded.
        assert len(all_out) == 1
        assert "RuntimeError" in all_out[0]["message"]
        # Next Traceback starts a new buffer (previous already flushed).
        new_out = list(merger.feed(_evt("Traceback (most recent call last):")))
        assert new_out == []

    def test_max_traceback_lines_flushes(self):
        """Un traceback sin columna 0 en >300 líneas → flush forzado periódico."""
        merger = TracebackMerger()
        # Start + 301 lines = 302 total, triggers flush at index 300 (len=301 > MAX=300)
        lines = ["Traceback (most recent call last):"] + ["  line %d" % i for i in range(301)]
        out = []
        for line in lines:
            out.extend(merger.feed(_evt(line)))
        # The flush triggers at the 301st line (len > 300), producing one
        # large merged event, then the remaining 2 lines buffer (and get
        # flushed at the end or on next feed). So we get ≥1 merged event
        # that starts with "Traceback" and has 300+ lines.
        merged = [e for e in out if e["message"].startswith("Traceback")]
        assert len(merged) >= 1
        assert len(merged[0]["message"].split("\n")) >= 300

    def test_non_traceback_column0_passes_through(self):
        """Una línea con columna 0 que no empieza por 'Traceback' es evento normal."""
        merger = TracebackMerger()
        out = list(merger.feed(_evt("SomeColumn0Error")))
        assert len(out) == 1

    def test_journald_source_type(self):
        """Tracebacks desde journald también se agrupan."""
        merger = TracebackMerger()
        evt = RawEvent(
            timestamp=_TS,
            source_type=SourceType.journald,
            source_name="myapp.service",
            severity=Severity.error,
            message="Traceback (most recent call last):",
            raw="Traceback (most recent call last):",
        )
        out = list(merger.feed(evt))
        assert out == []
