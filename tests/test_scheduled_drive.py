"""Task 4: stage-and-continue drive mode for scheduled runs.

A ``run_mode="scheduled"`` loop stages every write as a pending preview and
advances instead of pausing at ``awaiting_approval`` — reads still run inline,
nothing mutates, and the run reaches ``completed`` with N queued approvals.
The interactive drive of the same plan is unchanged (still pauses at the first
write).  Scheduled state is isolated on disk under ``schedules/runs/<key>.json``
so it never creates or clobbers the interactive ``loop-state.json``.
"""
from __future__ import annotations

import pytest

import hubspot_agent.agents  # noqa: F401 — populate the @tool registry for get_tool()
from hubspot_agent import loop_state
from hubspot_agent.config import PortalConfig
from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel
from hubspot_agent.orchestrator import _drive_loop, run_loop
from hubspot_agent.persistence import load as load_pending


def _portal() -> PortalConfig:
    return PortalConfig(portal_id="123", token="test-token", tier="Professional")


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


_WRITE_TOOLS = {
    "hubspot_update_object",
    "hubspot_delete_object",
    "hubspot_create_object",
    "hubspot_merge_objects",
}


def _patch_invoke_tool(monkeypatch, recorder: list[dict]):
    async def _fake(tool_name, portal_id, **kwargs):
        recorder.append({"tool": tool_name, "kwargs": dict(kwargs)})
        if tool_name == "hubspot_get_object":
            return {"id": str(kwargs.get("object_id", "x")), "properties": {"firstname": "Old"}}
        if tool_name == "hubspot_update_object":
            return {"id": kwargs.get("object_id"), "properties": kwargs.get("properties", {})}
        return {"id": "1"}

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _fake)


def _patch_fresh_client(monkeypatch):
    async def _fake_build(portal_config):
        return _FakeClient(), None

    monkeypatch.setattr("hubspot_agent.handlers.build_fresh_client_cache", _fake_build)


def _two_write_plan() -> LoopPlan:
    return LoopPlan(
        goal="Backfill two contacts",
        success_criteria=["both updated"],
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="update contact c-1 firstname",
                risk_level=RiskLevel.MEDIUM,
                tool_name="hubspot_update_object",
                tool_input={
                    "object_id": "c-1",
                    "object_type": "contacts",
                    "properties": {"firstname": "One"},
                },
            ),
            PlanStep(
                step_number=2,
                agent="objects",
                action="update contact c-2 firstname",
                risk_level=RiskLevel.MEDIUM,
                tool_name="hubspot_update_object",
                tool_input={
                    "object_id": "c-2",
                    "object_type": "contacts",
                    "properties": {"firstname": "Two"},
                },
            ),
        ],
        overall_risk=RiskLevel.MEDIUM,
    )


@pytest.mark.asyncio
async def test_scheduled_drive_stages_all_writes_and_completes(loop_dirs, monkeypatch):
    recorder: list[dict] = []
    _patch_invoke_tool(monkeypatch, recorder)
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    state = loop_state.LoopState(
        portal_id="123",
        request_text="Backfill two contacts",
        trace_id="trace-sched",
        plan=_two_write_plan(),
        run_mode="scheduled",
        state_key="sched-1",
    )

    await _drive_loop(portal, state, ".")

    # Both writes staged, run advanced to completion — no pause.
    assert state.status == "completed"
    assert len(state.staged_action_ids) == 2
    assert state.pending_action_id is None

    # Each staged id is a real pending preview on disk (a queued approval).
    for aid in state.staged_action_ids:
        assert load_pending("123", aid) is not None

    # ZERO mutation: only reads/preview builds ran; no write tool was invoked.
    invoked = [c["tool"] for c in recorder]
    assert not (_WRITE_TOOLS & set(invoked)), invoked

    # State isolation: a scheduled run never creates the interactive state file.
    assert not (loop_dirs / "123" / "loop-state.json").exists()


@pytest.mark.asyncio
async def test_interactive_drive_of_same_plan_still_pauses(loop_dirs, monkeypatch):
    recorder: list[dict] = []
    _patch_invoke_tool(monkeypatch, recorder)
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    plan = _two_write_plan()
    result = await run_loop(plan.goal, portal, ".", "trace-int", plan=plan)

    assert "paused" in result.lower()
    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    assert state.pending_action_id
    # Paused at the FIRST write — the second step never ran.
    assert state.current_step == 0
    # Interactive state lives in loop-state.json; no scheduled run file exists.
    assert (loop_dirs / "123" / "loop-state.json").exists()
    assert not (loop_dirs / "123" / "schedules" / "runs").exists()


def test_state_path_routes_by_state_key(loop_dirs):
    portal_id = "123"
    interactive = loop_state.LoopState(
        portal_id=portal_id, request_text="i", trace_id="t", plan=_two_write_plan(),
    )
    scheduled = loop_state.LoopState(
        portal_id=portal_id, request_text="s", trace_id="t", plan=_two_write_plan(),
        run_mode="scheduled", state_key="sched-9",
    )

    loop_state.save(interactive)
    loop_state.save(scheduled)

    assert (loop_dirs / portal_id / "loop-state.json").exists()
    assert (loop_dirs / portal_id / "schedules" / "runs" / "sched-9.json").exists()

    # clear_run removes only the scheduled run file; the interactive file stays.
    loop_state.clear_run(scheduled)
    assert not (loop_dirs / portal_id / "schedules" / "runs" / "sched-9.json").exists()
    assert (loop_dirs / portal_id / "loop-state.json").exists()


def test_run_mode_fields_roundtrip(loop_dirs):
    state = loop_state.LoopState(
        portal_id="123", request_text="s", trace_id="t", plan=_two_write_plan(),
        run_mode="scheduled", state_key="sched-3", staged_action_ids=["a", "b"],
    )
    restored = loop_state.LoopState.from_dict(state.to_dict())
    assert restored.run_mode == "scheduled"
    assert restored.state_key == "sched-3"
    assert restored.staged_action_ids == ["a", "b"]


@pytest.mark.asyncio
async def test_scheduled_drive_refuses_free_text_step(loop_dirs, monkeypatch):
    """A scheduled plan MUST be fully concrete: a step with no ``tool_name``
    could reach the free-text execute branch and mutate unattended, so the
    drive hard-stops (status "failed") and never dispatches it."""
    recorder: list[dict] = []
    _patch_invoke_tool(monkeypatch, recorder)
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    plan = LoopPlan(
        goal="Remove stale deals",
        success_criteria=["done"],
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="remove stale deals",  # free-text, no tool_name
                risk_level=RiskLevel.LOW,
            ),
        ],
        overall_risk=RiskLevel.LOW,
    )
    state = loop_state.LoopState(
        portal_id="123",
        request_text="Remove stale deals",
        trace_id="trace-freetext",
        plan=plan,
        run_mode="scheduled",
        state_key="sched-ft",
    )

    result = await _drive_loop(portal, state, ".")

    assert state.status == "failed"
    assert "concrete" in result.lower()
    assert "tool_name" in result
    assert state.staged_action_ids == []
    # Refused before any dispatch — no tool of any kind (least of all a write) ran.
    assert not (_WRITE_TOOLS & {c["tool"] for c in recorder})
    assert recorder == []


def test_run_mode_defaults_on_legacy_state(loop_dirs):
    state = loop_state.LoopState(
        portal_id="123", request_text="s", trace_id="t", plan=_two_write_plan(),
    )
    data = state.to_dict()
    del data["run_mode"]
    del data["staged_action_ids"]
    del data["state_key"]
    restored = loop_state.LoopState.from_dict(data)
    assert restored.run_mode == "interactive"
    assert restored.state_key is None
    assert restored.staged_action_ids == []
