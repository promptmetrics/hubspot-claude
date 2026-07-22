from __future__ import annotations

import pytest

from hubspot_agent.loop_controller import LoopController, LoopDecision
from hubspot_agent.loop_state import LoopState
from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel, VerificationResult


def _make_state(**overrides) -> LoopState:
    plan = LoopPlan(
        goal="Test goal",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="create",
                risk_level=RiskLevel.MEDIUM,
            ),
        ],
    )
    return LoopState(
        portal_id="12345678",
        request_text="test request",
        trace_id="trace-1",
        plan=plan,
        **overrides,
    )


def test_proceed_when_verified():
    controller = LoopController()
    state = _make_state()
    verification = VerificationResult(status=VerificationResult.Status.VERIFIED)
    decision = controller.next_action(state, verification=verification)
    assert decision.action == "proceed"
    assert not decision.final


def test_retry_on_mismatch():
    controller = LoopController()
    state = _make_state()
    verification = VerificationResult(
        status=VerificationResult.Status.MISMATCH,
        mismatches=[{"field": "name", "expected": "A", "actual": "B"}],
    )
    decision = controller.next_action(state, verification=verification)
    assert decision.action == "retry"


def test_stop_at_max_iterations():
    controller = LoopController(max_iterations=3)
    state = _make_state(iterations=3)
    decision = controller.next_action(state)
    assert decision.action == "stop"
    assert decision.final


def test_plateau_escalates_after_two_identical_mismatches():
    controller = LoopController(verification_plateau=2)
    state = _make_state()
    mismatch = VerificationResult(
        status=VerificationResult.Status.MISMATCH,
        mismatches=[{"field": "name", "expected": "A", "actual": "B"}],
    )

    d1 = controller.next_action(state, verification=mismatch)
    assert d1.action == "retry"
    assert state.plateau_count == 1

    d2 = controller.next_action(state, verification=mismatch)
    assert d2.action == "escalate"
    assert d2.final


def test_different_mismatch_resets_plateau():
    controller = LoopController(verification_plateau=2)
    state = _make_state()
    m1 = VerificationResult(
        status=VerificationResult.Status.MISMATCH,
        mismatches=[{"field": "name", "expected": "A", "actual": "B"}],
    )
    m2 = VerificationResult(
        status=VerificationResult.Status.MISMATCH,
        mismatches=[{"field": "email", "expected": "A", "actual": "B"}],
    )
    m3 = VerificationResult(
        status=VerificationResult.Status.MISMATCH,
        mismatches=[{"field": "phone", "expected": "A", "actual": "B"}],
    )

    controller.next_action(state, verification=m1)
    controller.next_action(state, verification=m2)
    d3 = controller.next_action(state, verification=m3)
    assert d3.action == "retry"


def test_step_budget_stops():
    # Proxy budget replaces the retired HUBSPOT_LOOP_COST env hook: an executed
    # step count at/over max_steps hard-stops the loop.
    controller = LoopController(max_steps=10)
    state = _make_state(step_count=10)
    decision = controller.next_action(state)
    assert decision.action == "stop"
    assert decision.final
    assert "Step budget" in decision.reason


def test_api_call_budget_stops():
    controller = LoopController(max_api_calls=100)
    state = _make_state(api_call_count=100)
    decision = controller.next_action(state)
    assert decision.action == "stop"
    assert decision.final
    assert "API-call budget" in decision.reason


def test_budgets_do_not_stop_under_limit():
    # A verified verdict still proceeds while both proxy budgets are under limit.
    controller = LoopController(max_steps=50, max_api_calls=1000)
    state = _make_state(step_count=49, api_call_count=999)
    verification = VerificationResult(status=VerificationResult.Status.VERIFIED)
    decision = controller.next_action(state, verification=verification)
    assert decision.action == "proceed"


def test_step_error_escalates():
    controller = LoopController()
    state = _make_state()
    decision = controller.next_action(state, step_error="api down")
    assert decision.action == "escalate"
    assert decision.final


def test_verification_error_escalates():
    controller = LoopController()
    state = _make_state()
    verification = VerificationResult(
        status=VerificationResult.Status.ERROR,
        message="VerifyAgent failed",
    )
    decision = controller.next_action(state, verification=verification)
    assert decision.action == "escalate"
    assert decision.final


def test_record_iteration_increments():
    controller = LoopController()
    state = _make_state()
    controller.record_iteration(state)
    assert state.iterations == 1


def test_error_budget_escalates():
    controller = LoopController(error_budget=2)
    state = _make_state(iterations=2, last_error="api down")
    decision = controller.next_action(state)
    assert decision.action == "escalate"
    assert "Error budget" in decision.reason
