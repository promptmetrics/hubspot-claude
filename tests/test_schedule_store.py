"""Unit tests for the per-portal schedule store."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hubspot_agent import schedule_store
from hubspot_agent.schedule_store import Schedule


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    return tmp_path


def _sched(sid="daily-dedupe", name="Daily dedupe", cron="30 9 * * *",
           created_at=None, **kw):
    return Schedule(
        id=sid,
        name=name,
        cron=cron,
        plan={"steps": [{"tool": "hubspot_find_duplicates"}], "max_steps": 5},
        created_at=created_at or datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc),
        **kw,
    )


# --------------------------------------------------------------------------- #
# round-trip
# --------------------------------------------------------------------------- #

def test_save_load_round_trip(cfg):
    s = _sched()
    schedule_store.save("123", s)
    loaded = schedule_store.load("123", "daily-dedupe")
    assert loaded is not None
    assert loaded.id == "daily-dedupe"
    assert loaded.name == "Daily dedupe"
    assert loaded.cron == "30 9 * * *"
    assert loaded.plan == {"steps": [{"tool": "hubspot_find_duplicates"}], "max_steps": 5}
    assert loaded.created_at == datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    assert loaded.last_run_at is None
    assert loaded.last_batch is None


def test_last_run_and_last_batch_round_trip(cfg):
    batch = {
        "run_at": "2026-07-22T09:30:00+00:00",
        "status": "pending",
        "pending_action_ids": ["a1", "a2"],
        "summary": "2 updates staged",
    }
    s = _sched(
        last_run_at=datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc),
        last_batch=batch,
    )
    schedule_store.save("123", s)
    loaded = schedule_store.load("123", "daily-dedupe")
    assert loaded.last_run_at == datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    assert loaded.last_batch == batch


# --------------------------------------------------------------------------- #
# list / remove
# --------------------------------------------------------------------------- #

def test_list_empty_when_dir_absent(cfg):
    assert schedule_store.list_schedules("123") == []


def test_list_newest_first(cfg):
    schedule_store.save("123", _sched(
        sid="old", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    schedule_store.save("123", _sched(
        sid="new", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc)))
    schedule_store.save("123", _sched(
        sid="mid", created_at=datetime(2026, 4, 1, tzinfo=timezone.utc)))
    ids = [s.id for s in schedule_store.list_schedules("123")]
    assert ids == ["new", "mid", "old"]


def test_per_portal_isolation(cfg):
    schedule_store.save("123", _sched(sid="a"))
    schedule_store.save("456", _sched(sid="b"))
    assert [s.id for s in schedule_store.list_schedules("123")] == ["a"]
    assert [s.id for s in schedule_store.list_schedules("456")] == ["b"]


def test_remove(cfg):
    schedule_store.save("123", _sched())
    assert schedule_store.remove("123", "daily-dedupe") is True
    assert schedule_store.load("123", "daily-dedupe") is None
    # removing again is a no-op returning False
    assert schedule_store.remove("123", "daily-dedupe") is False


# --------------------------------------------------------------------------- #
# mutators
# --------------------------------------------------------------------------- #

def test_set_last_run(cfg):
    schedule_store.save("123", _sched())
    when = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    schedule_store.set_last_run("123", "daily-dedupe", when)
    assert schedule_store.load("123", "daily-dedupe").last_run_at == when


def test_set_last_batch(cfg):
    schedule_store.save("123", _sched())
    batch = {
        "run_at": "2026-07-22T09:30:00+00:00",
        "status": "running",
        "pending_action_ids": [],
        "summary": "",
    }
    schedule_store.set_last_batch("123", "daily-dedupe", batch)
    assert schedule_store.load("123", "daily-dedupe").last_batch == batch


def test_mutators_noop_when_missing(cfg):
    # no file exists — must not raise
    schedule_store.set_last_run("123", "ghost", datetime.now(timezone.utc))
    schedule_store.set_last_batch("123", "ghost", {"status": "done"})
    assert schedule_store.load("123", "ghost") is None


# --------------------------------------------------------------------------- #
# error / robustness
# --------------------------------------------------------------------------- #

def test_missing_file_returns_none(cfg):
    assert schedule_store.load("123", "nope") is None


def test_bad_schedule_id_raises_on_save(cfg):
    with pytest.raises(ValueError):
        schedule_store.save("123", _sched(sid="../etc/passwd"))


def test_bad_portal_id_raises(cfg):
    with pytest.raises(ValueError):
        schedule_store.save("not-numeric", _sched())


def test_corrupt_json_returns_none(cfg):
    schedule_store.save("123", _sched())
    path = cfg / "123" / "schedules" / "daily-dedupe.json"
    path.write_text("{ not valid json")
    assert schedule_store.load("123", "daily-dedupe") is None
