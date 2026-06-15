from __future__ import annotations

import json

import pytest

from hubspot_agent.loop_log import _log_path, get_recent, log_event, rotate


@pytest.fixture(autouse=True)
def _clean_log(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    yield


def test_log_event_appends():
    log_event("12345678", "trace-1", "step_executed", {"step": 1})
    path = _log_path("12345678")
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["trace_id"] == "trace-1"
    assert event["event_type"] == "step_executed"
    assert event["payload"]["step"] == 1
    assert "timestamp" in event


def test_get_recent_returns_events():
    log_event("12345678", "trace-1", "step_executed", {"step": 1})
    log_event("12345678", "trace-1", "step_verified", {"step": 1})
    events = get_recent("12345678", trace_id="trace-1")
    assert len(events) == 2
    assert events[0]["event_type"] == "step_verified"


def test_get_recent_filters_trace():
    log_event("12345678", "trace-1", "step_executed", {"step": 1})
    log_event("12345678", "trace-2", "step_executed", {"step": 2})
    events = get_recent("12345678", trace_id="trace-2")
    assert len(events) == 1
    assert events[0]["payload"]["step"] == 2


def test_get_recent_respects_limit():
    for i in range(5):
        log_event("12345678", "trace-1", "step", {"i": i})
    events = get_recent("12345678", limit=2)
    assert len(events) == 2
    assert events[0]["payload"]["i"] == 4


def test_get_recent_newest_first():
    log_event("12345678", "trace-1", "first", {})
    log_event("12345678", "trace-1", "second", {})
    events = get_recent("12345678")
    assert events[0]["event_type"] == "second"
    assert events[1]["event_type"] == "first"


def test_get_recent_missing_returns_empty():
    assert get_recent("99999999") == []


def test_get_recent_skips_corrupt_lines():
    log_event("12345678", "trace-1", "good", {})
    path = _log_path("12345678")
    with path.open("a") as fh:
        fh.write("not json\n")
    events = get_recent("12345678")
    assert len(events) == 1
    assert events[0]["event_type"] == "good"


def test_rotate_creates_archive(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    log_event("12345678", "trace-1", "big", {"data": "x" * 1000})
    rotate("12345678", max_bytes=1)
    archive_dir = tmp_path / ".claude" / "hubspot" / "12345678" / "loop-log-archive"
    assert any(archive_dir.glob("loop-log-*.ndjson"))
    assert not _log_path("12345678").exists()
