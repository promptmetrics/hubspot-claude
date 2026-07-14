"""End-to-end durable-loop test: plan -> pause -> approve -> continue -> verify.

Exercises the real safety path (apply_write persistence, execute_pending_write's
count gate + undo snapshot + audit + clear-pending) and the real resume
disambiguation (pending-gone + audit ``approve:<id>`` -> capture artifact from
the undo snapshot).  Only the two HTTP seams are stubbed: the preview builder
and the execute dispatch.
"""
from __future__ import annotations

import pytest

from hubspot_agent.config import PortalConfig
from hubspot_agent.handlers import execute_pending_write
from hubspot_agent.models import LoopPlan, PlanStep, PreviewResult, RiskLevel
from hubspot_agent import loop_state
from hubspot_agent.orchestrator import loop_verify, run_loop


def _portal_config() -> PortalConfig:
    return PortalConfig(portal_id="123", token="test-token", tier="Professional")


@pytest.fixture
def loop_dirs(tmp_path, monkeypatch):
    """Point every on-disk root the loop touches at one temp tree."""
    root = tmp_path / ".claude" / "hubspot"
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", root)
    return root


async def _fake_build_preview_for_intent(agent_name, intent, client, portal_id):
    return PreviewResult(
        preview={"message": "Will create property renewal_date"},
        impact_count=1,
        risk_level=RiskLevel.MEDIUM,
        proposed_payload={"name": "renewal_date", "type": "date"},
        original_values={},
        informing_sources=[],
    )


def _fake_execute_dispatch(agent_name):
    async def _execute(agent, intent, request_text, client, portal_id, proposed_payload):
        return {"status": "success", "data": {"result": {"id": "prop-1"}}}
    return _execute


@pytest.mark.asyncio
async def test_durable_loop_plan_pause_approve_continue_verify(loop_dirs, monkeypatch):
    monkeypatch.setattr(
        "hubspot_agent.orchestrator._build_preview_for_intent", _fake_build_preview_for_intent
    )
    monkeypatch.setattr("hubspot_agent.orchestrator.get_execute_dispatch", _fake_execute_dispatch)

    portal = _portal_config()
    plan = LoopPlan(
        goal="Create a custom contact property renewal_date",
        success_criteria=["property exists"],
        steps=[
            PlanStep(
                step_number=1,
                agent="properties",
                action="create property renewal_date",
                expected_artifact_keys=["property_id"],
                risk_level=RiskLevel.MEDIUM,
            )
        ],
        overall_risk=RiskLevel.MEDIUM,
        max_iterations=3,
    )

    # 1. loop start -> pauses at the write, persists a real pending preview.
    start_result = await run_loop(plan.goal, portal, ".", "e2e-trace", plan=plan)
    assert "paused" in start_result.lower()

    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    action_id = state.pending_action_id
    assert action_id  # a real uuid[:8] minted by apply_write

    # 2. approve -> the unchanged safety path executes, snapshots, audits, clears.
    exec_result = await execute_pending_write(portal, action_id)
    assert exec_result.status == "success"
    assert exec_result.created_ids == ["prop-1"]

    # 3. loop continue -> detects the executed write, captures the artifact.
    continue_result = await run_loop(state.request_text, portal, ".", "e2e-trace")
    assert "loop verify" in continue_result
    state = loop_state.load("123")
    assert state.status == "awaiting_verification"
    assert state.artifacts[0].created_ids == ["prop-1"]
    assert state.artifacts[0].outputs.get("property_id") == "prop-1"

    # 4. loop verify (verified) -> proceed -> no more steps -> completed.
    verify_result = await loop_verify(
        '{"status": "verified", "checked_count": 1, "verified_count": 1}', portal, "."
    )
    assert "completed" in verify_result.lower()
    assert "prop-1" in verify_result
    assert loop_state.load("123") is None  # cleared on completion


@pytest.mark.asyncio
async def test_durable_loop_reject_stops(loop_dirs, monkeypatch):
    monkeypatch.setattr(
        "hubspot_agent.orchestrator._build_preview_for_intent", _fake_build_preview_for_intent
    )

    from hubspot_agent.persistence import clear as clear_pending

    portal = _portal_config()
    plan = LoopPlan(
        goal="Create a property",
        steps=[
            PlanStep(step_number=1, agent="properties", action="create property x",
                     risk_level=RiskLevel.MEDIUM)
        ],
        overall_risk=RiskLevel.MEDIUM,
    )

    await run_loop(plan.goal, portal, ".", "e2e-reject", plan=plan)
    state = loop_state.load("123")
    action_id = state.pending_action_id

    # Reject == clear the pending preview without ever approving it.
    clear_pending("123", action_id)

    result = await run_loop(state.request_text, portal, ".", "e2e-reject")
    assert "rejected or cancelled" in result
    assert loop_state.load("123").status == "stop"
