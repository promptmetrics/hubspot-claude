"""Task 7/8: the ``hubspot schedule`` CLI family + scheduled-origin status grouping."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import hubspot_agent.agents  # noqa: F401 — populate the @tool registry for get_tool()
from hubspot_agent import schedule_store
from hubspot_agent.cli import _parse_schedule_flags, hubspot_command
from hubspot_agent.persistence import store as store_pending


def _setup_portal(tmp_path, monkeypatch):
    (tmp_path / ".hubspot-portal").write_text("123\n")
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")
    root = tmp_path / ".claude" / "hubspot"
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", root)
    return root


def _plan_json() -> str:
    return json.dumps({
        "goal": "backfill",
        "success_criteria": ["done"],
        "overall_risk": "medium",
        "steps": [
            {
                "step_number": 1,
                "agent": "objects",
                "action": "update contact c-1 firstname",
                "risk_level": "medium",
                "tool_name": "hubspot_update_object",
                "tool_input": {
                    "object_id": "c-1",
                    "object_type": "contacts",
                    "properties": {"firstname": "X"},
                },
            }
        ],
    })


# --------------------------------------------------------------------------- #
# flag parser
# --------------------------------------------------------------------------- #

def test_parse_schedule_flags_order_independent_and_spaced_cron():
    args = '--cron 0 9 * * 1 --name Weekly dedupe --plan {"goal": "g"}'
    flags = _parse_schedule_flags(args)
    assert flags["cron"] == "0 9 * * 1"
    assert flags["name"] == "Weekly dedupe"
    assert flags["plan"] == '{"goal": "g"}'


# --------------------------------------------------------------------------- #
# add
# --------------------------------------------------------------------------- #

def test_add_rejects_bad_cron(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command(
        f"schedule add --plan {_plan_json()} --cron nonsense --name Bad",
        working_dir=str(tmp_path),
    )
    assert "Invalid cron expression" in result
    assert schedule_store.list_schedules("123") == []


def test_add_stores_and_returns_id(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command(
        f"schedule add --plan {_plan_json()} --cron 0 9 * * 1 --name Weekly dedupe",
        working_dir=str(tmp_path),
    )
    assert "Scheduled 'Weekly dedupe'" in result
    assert "Next due" in result

    schedules = schedule_store.list_schedules("123")
    assert len(schedules) == 1
    s = schedules[0]
    assert s.name == "Weekly dedupe"
    assert s.cron == "0 9 * * 1"
    # The minted id is echoed in the confirmation.
    assert s.id in result


def test_add_seeds_last_run_at_for_reliable_first_fire(tmp_path, monkeypatch):
    """Regression: ``last_run_at`` is seeded at creation so ``run-due``'s interval
    scan catches the first matching tick even when the external poll interval is
    unaligned to the cron minute. An unseeded schedule (last_run_at=None) reduces
    ``is_due`` to an exact ``matches(now)`` check and would miss the first fire —
    and, never advancing its clock, could miss every fire."""
    _setup_portal(tmp_path, monkeypatch)
    hubspot_command(
        f"schedule add --plan {_plan_json()} --cron 5 9 * * 1 --name Weekly",
        working_dir=str(tmp_path),
    )
    s = schedule_store.list_schedules("123")[0]
    assert s.last_run_at is not None
    assert s.last_run_at == s.created_at


def test_add_rejects_non_concrete_plan(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    free_text_plan = json.dumps({
        "goal": "remove stale deals",
        "success_criteria": ["done"],
        "overall_risk": "low",
        "steps": [
            {
                "step_number": 1,
                "agent": "objects",
                "action": "remove stale deals",
                "risk_level": "low",
            }
        ],
    })
    result = hubspot_command(
        f"schedule add --plan {free_text_plan} --cron 0 9 * * 1 --name Stale deals",
        working_dir=str(tmp_path),
    )
    assert "must be concrete" in result
    assert schedule_store.list_schedules("123") == []


def test_add_without_flags_returns_usage(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("schedule add", working_dir=str(tmp_path))
    assert "Usage: /hubspot schedule add" in result


# --------------------------------------------------------------------------- #
# list / remove
# --------------------------------------------------------------------------- #

def test_list_shows_next_due(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    hubspot_command(
        f"schedule add --plan {_plan_json()} --cron 0 9 * * 1 --name Weekly dedupe",
        working_dir=str(tmp_path),
    )
    result = hubspot_command("schedule list", working_dir=str(tmp_path))
    assert "Weekly dedupe" in result
    assert "next due" in result
    assert "0 9 * * 1" in result


def test_list_empty(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("schedule list", working_dir=str(tmp_path))
    assert "No schedules registered" in result


def test_remove(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    hubspot_command(
        f"schedule add --plan {_plan_json()} --cron 0 9 * * 1 --name Weekly dedupe",
        working_dir=str(tmp_path),
    )
    sid = schedule_store.list_schedules("123")[0].id
    result = hubspot_command(f"schedule remove {sid}", working_dir=str(tmp_path))
    assert "Removed schedule" in result
    assert schedule_store.list_schedules("123") == []


def test_remove_missing(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("schedule remove nope", working_dir=str(tmp_path))
    assert "No schedule nope found" in result


# --------------------------------------------------------------------------- #
# run-due / install-timer
# --------------------------------------------------------------------------- #

class _FakeClient:
    async def close(self):
        return None


def test_run_due_returns_summary(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)

    async def _fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            return {"id": str(kwargs.get("object_id", "x")), "properties": {"firstname": "Old"}}
        return {"id": "1"}

    async def _fake_build(portal_config):
        return _FakeClient(), None

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _fake_invoke)
    monkeypatch.setattr("hubspot_agent.handlers.build_fresh_client_cache", _fake_build)

    hubspot_command(
        f"schedule add --plan {_plan_json()} --cron * * * * * --name Every minute",
        working_dir=str(tmp_path),
    )
    # The seeded clock means a schedule created this minute isn't due until the
    # next tick; backdate it so this poll genuinely runs the (every-minute) plan.
    sid = schedule_store.list_schedules("123")[0].id
    schedule_store.set_last_run("123", sid, datetime.now(timezone.utc) - timedelta(minutes=2))
    result = hubspot_command("schedule run-due", working_dir=str(tmp_path))
    assert "Every minute" in result
    assert "ran" in result


def test_install_timer_snippet_mentions_run_due(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("schedule install-timer", working_dir=str(tmp_path))
    assert "run-due" in result
    assert "launchd" in result.lower()
    assert "cron" in result.lower()


def test_unknown_schedule_subcommand_returns_usage(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("schedule bogus", working_dir=str(tmp_path))
    assert "Usage: /hubspot schedule" in result


# --------------------------------------------------------------------------- #
# Task 8: status grouping
# --------------------------------------------------------------------------- #

def test_status_groups_scheduled_previews_by_schedule(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    # Two staged previews from one schedule + one ad-hoc preview with no origin.
    store_pending("123", "a1", {
        "proposed_payload": {},
        "origin": {"schedule_id": "s1", "schedule_name": "Daily dedupe",
                   "run_at": "2026-07-22T09:30:00+00:00"},
    })
    store_pending("123", "a2", {
        "proposed_payload": {},
        "origin": {"schedule_id": "s1", "schedule_name": "Daily dedupe",
                   "run_at": "2026-07-22T09:30:00+00:00"},
    })
    store_pending("123", "b1", {"proposed_payload": {}})

    result = hubspot_command("status", working_dir=str(tmp_path))

    assert "3 preview(s) awaiting approval" in result
    assert 'from schedule "Daily dedupe" (2026-07-22T09:30:00+00:00): 2 preview(s)' in result
