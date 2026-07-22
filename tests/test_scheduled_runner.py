"""Task 5/6: ``run_scheduled_due`` — the deterministic scheduled-run sweep.

Reads run inline; every write is staged as a pending preview (nothing mutates);
gates decide skip (not due / prior batch pending) vs expire (stale batch) vs run.
Staged previews carry schedule provenance.  ``now`` is injected so due-computation
is deterministic and no test touches the wall clock.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import hubspot_agent.agents  # noqa: F401 — populate the @tool registry for get_tool()
from hubspot_agent import loop_state, schedule_store
from hubspot_agent.config import PortalConfig
from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel
from hubspot_agent.orchestrator import run_scheduled_due
from hubspot_agent.persistence import load as load_pending, store as store_pending
from hubspot_agent.schedule_store import Schedule

_NOW = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)

_WRITE_TOOLS = {
    "hubspot_update_object",
    "hubspot_delete_object",
    "hubspot_create_object",
    "hubspot_merge_objects",
}


def _portal(pid: str = "123") -> PortalConfig:
    return PortalConfig(portal_id=pid, token="test-token", tier="Professional")


@pytest.fixture
def loop_dirs(tmp_path, monkeypatch):
    root = tmp_path / ".claude" / "hubspot"
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", root)
    return root


class _FakeClient:
    async def close(self):
        return None


@pytest.fixture
def _fakes(monkeypatch):
    recorder: list[dict] = []

    async def _fake_invoke(tool_name, portal_id, **kwargs):
        recorder.append({"tool": tool_name, "kwargs": dict(kwargs)})
        if tool_name == "hubspot_get_object":
            return {"id": str(kwargs.get("object_id", "x")), "properties": {"firstname": "Old"}}
        if tool_name == "hubspot_update_object":
            return {"id": kwargs.get("object_id"), "properties": kwargs.get("properties", {})}
        return {"id": "1"}

    async def _fake_build(portal_config):
        return _FakeClient(), None

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _fake_invoke)
    monkeypatch.setattr("hubspot_agent.handlers.build_fresh_client_cache", _fake_build)
    return recorder


def _plan_dict(n_writes: int, *, max_steps: int = 50) -> dict:
    steps = [
        PlanStep(
            step_number=i + 1,
            agent="objects",
            action=f"update contact c-{i + 1} firstname",
            risk_level=RiskLevel.MEDIUM,
            tool_name="hubspot_update_object",
            tool_input={
                "object_id": f"c-{i + 1}",
                "object_type": "contacts",
                "properties": {"firstname": f"N{i + 1}"},
            },
        )
        for i in range(n_writes)
    ]
    return LoopPlan(
        goal="backfill",
        success_criteria=["done"],
        steps=steps,
        overall_risk=RiskLevel.MEDIUM,
        max_steps=max_steps,
    ).model_dump(mode="json")


def _save(portal_id, sid, *, cron="* * * * *", plan=None, created_at=None,
          last_run_at=None, last_batch=None, name=None):
    schedule_store.save(portal_id, Schedule(
        id=sid,
        name=name or f"Schedule {sid}",
        cron=cron,
        plan=plan if plan is not None else _plan_dict(1),
        created_at=created_at or datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc),
        last_run_at=last_run_at,
        last_batch=last_batch,
    ))


@pytest.mark.asyncio
async def test_due_schedule_stages_previews_no_mutation(loop_dirs, _fakes):
    _save("123", "s1", plan=_plan_dict(2))
    await run_scheduled_due(_portal(), ".", now=_NOW)

    sched = schedule_store.load("123", "s1")
    assert sched.last_batch["status"] == "pending"
    assert len(sched.last_batch["pending_action_ids"]) == 2
    assert sched.last_run_at == _NOW

    for aid in sched.last_batch["pending_action_ids"]:
        assert load_pending("123", aid) is not None

    # No write tool ever invoked — reads/preview builds only.
    assert not (_WRITE_TOOLS & {c["tool"] for c in _fakes})
    # Scheduled run cleared its own state file; no interactive state created.
    assert not (loop_dirs / "123" / "loop-state.json").exists()
    assert not (loop_dirs / "123" / "schedules" / "runs" / "s1.json").exists()


@pytest.mark.asyncio
async def test_staged_preview_carries_schedule_provenance(loop_dirs, _fakes):
    _save("123", "s1", plan=_plan_dict(1), name="Daily dedupe")
    await run_scheduled_due(_portal(), ".", now=_NOW)

    sched = schedule_store.load("123", "s1")
    aid = sched.last_batch["pending_action_ids"][0]
    preview = load_pending("123", aid)
    assert preview["origin"]["schedule_name"] == "Daily dedupe"
    assert preview["origin"]["schedule_id"] == "s1"
    assert preview["origin"]["run_at"] == _NOW.isoformat()


@pytest.mark.asyncio
async def test_not_due_schedule_is_skipped(loop_dirs, _fakes):
    _save("123", "s1", cron="0 0 1 1 *", plan=_plan_dict(1))  # Jan 1 only
    summary = await run_scheduled_due(_portal(), ".", now=_NOW)

    assert "skipped (not due)" in summary
    sched = schedule_store.load("123", "s1")
    assert sched.last_batch is None
    assert sched.last_run_at is None


@pytest.mark.asyncio
async def test_overlap_fresh_pending_is_skipped(loop_dirs, _fakes):
    batch = {
        "run_at": (_NOW - timedelta(days=1)).isoformat(),
        "status": "pending",
        "pending_action_ids": ["old-1"],
    }
    _save("123", "s1", plan=_plan_dict(1), last_batch=batch)
    store_pending("123", "old-1", {"tool_name": "hubspot_update_object", "proposed_payload": {}})

    summary = await run_scheduled_due(_portal(), ".", now=_NOW)

    assert "prior batch pending" in summary
    # Untouched: batch still pending, its queued preview still on disk.
    sched = schedule_store.load("123", "s1")
    assert sched.last_batch["status"] == "pending"
    assert load_pending("123", "old-1") is not None


@pytest.mark.asyncio
async def test_resolved_batch_unfreezes_and_runs(loop_dirs, _fakes):
    """The overlap gate derives "still pending" from disk, not the status
    string: a batch whose queued preview was approved/rejected (cleared → gone)
    no longer blocks, so a due schedule runs again even while last_batch still
    reads ``pending``."""
    batch = {
        "run_at": (_NOW - timedelta(days=1)).isoformat(),  # recent, within TTL
        "status": "pending",
        "pending_action_ids": ["gone1"],  # NOT on disk — resolved
    }
    _save("123", "s1", plan=_plan_dict(1), last_batch=batch)

    summary = await run_scheduled_due(_portal(), ".", now=_NOW)

    assert "ran" in summary
    sched = schedule_store.load("123", "s1")
    assert sched.last_batch["status"] == "pending"
    assert "gone1" not in sched.last_batch["pending_action_ids"]
    assert len(sched.last_batch["pending_action_ids"]) == 1


@pytest.mark.asyncio
async def test_unresolved_batch_still_skips(loop_dirs, _fakes):
    """Same recent batch, but its queued preview STILL EXISTS on disk (unreviewed)
    → the schedule is skipped to avoid piling a second stale batch."""
    batch = {
        "run_at": (_NOW - timedelta(days=1)).isoformat(),  # recent, within TTL
        "status": "pending",
        "pending_action_ids": ["gone1"],
    }
    _save("123", "s1", plan=_plan_dict(1), last_batch=batch)
    store_pending("123", "gone1", {"tool_name": "hubspot_update_object", "proposed_payload": {}})

    summary = await run_scheduled_due(_portal(), ".", now=_NOW)

    assert "prior batch pending" in summary
    sched = schedule_store.load("123", "s1")
    assert sched.last_batch["status"] == "pending"
    assert sched.last_batch["pending_action_ids"] == ["gone1"]
    assert load_pending("123", "gone1") is not None


@pytest.mark.asyncio
async def test_overlap_stale_pending_expires_then_runs(loop_dirs, _fakes):
    batch = {
        "run_at": (_NOW - timedelta(days=8)).isoformat(),  # older than ttl (7)
        "status": "pending",
        "pending_action_ids": ["old-1"],
    }
    _save("123", "s1", plan=_plan_dict(1), last_batch=batch)
    store_pending("123", "old-1", {"tool_name": "hubspot_update_object", "proposed_payload": {}})

    await run_scheduled_due(_portal(), ".", now=_NOW)

    # Stale queued preview cleared, and the schedule ran fresh.
    assert load_pending("123", "old-1") is None
    sched = schedule_store.load("123", "s1")
    assert sched.last_batch["status"] == "pending"
    assert "old-1" not in sched.last_batch["pending_action_ids"]
    assert len(sched.last_batch["pending_action_ids"]) == 1


@pytest.mark.asyncio
async def test_proxy_budget_halts_runaway_plan_mid_run(loop_dirs, _fakes):
    _save("123", "s1", plan=_plan_dict(3, max_steps=1))
    await run_scheduled_due(_portal(), ".", now=_NOW)

    sched = schedule_store.load("123", "s1")
    # Budget = 1 step → only the first write staged; run halted before the rest.
    assert len(sched.last_batch["pending_action_ids"]) == 1


@pytest.mark.asyncio
async def test_one_failing_schedule_does_not_stop_others(loop_dirs, _fakes):
    # A schedule whose stored plan is invalid (no steps) fails at model_validate.
    _save("123", "bad", plan={"goal": "broken"},
          created_at=datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc))
    _save("123", "good", plan=_plan_dict(1),
          created_at=datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc))

    summary = await run_scheduled_due(_portal(), ".", now=_NOW)

    assert "failed" in summary
    assert schedule_store.load("123", "bad").last_batch["status"] == "failed"
    good = schedule_store.load("123", "good")
    assert good.last_batch["status"] == "pending"
    assert len(good.last_batch["pending_action_ids"]) == 1


@pytest.mark.asyncio
async def test_per_portal_isolation(loop_dirs, _fakes):
    _save("123", "s1", plan=_plan_dict(1))
    _save("456", "s2", plan=_plan_dict(1))

    await run_scheduled_due(_portal("123"), ".", now=_NOW)

    # Portal 123's schedule ran; portal 456's is untouched.
    assert schedule_store.load("123", "s1").last_batch["status"] == "pending"
    assert schedule_store.load("456", "s2").last_batch is None
    assert schedule_store.load("456", "s2").last_run_at is None


@pytest.mark.asyncio
async def test_no_schedules_returns_notice(loop_dirs, _fakes):
    summary = await run_scheduled_due(_portal(), ".", now=_NOW)
    assert "No schedules" in summary
