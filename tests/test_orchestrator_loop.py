from unittest.mock import patch

import pytest

from hubspot_agent.config import PortalConfig
from hubspot_agent.models import AgentResult, LoopPlan, PlanStep, RiskLevel
from hubspot_agent import loop_state
from hubspot_agent.orchestrator import loop_verify, run_loop, run_simple


def _portal_config(tier: str = "Professional") -> PortalConfig:
    return PortalConfig(portal_id="123", token="test-token", tier=tier)


@pytest.fixture(autouse=True)
def _isolate_loop_dirs(monkeypatch, tmp_path):
    root = tmp_path / ".claude" / "hubspot"
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", root)
    # PR-B: keep the module-level last-seen rate snapshot hermetic per test so a
    # prior test's client response can't leak into pacing decisions here.
    monkeypatch.setattr("hubspot_agent.client._LAST_RATE_STATE", {})
    yield


def _write_plan(goal: str = "Create a property") -> LoopPlan:
    return LoopPlan(
        goal=goal,
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
    )


def _fake_dispatch(action_id: str = "act-1", created_id: str = "prop-123"):
    """dispatch_agent stub: preview → action_id; execute → success artifact."""

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        if mode == "preview":
            return AgentResult(
                agent_name=agent_name,
                status="preview",
                data={
                    "action_id": action_id,
                    "preview": f"preview of {agent_name}",
                    "risk_level": "medium",
                    "impact_count": 1,
                    "intent_type": "create",
                    "target_object": "contacts",
                    "proposed_payload": {},
                },
            )
        return AgentResult(
            agent_name=agent_name,
            status="success",
            data={"artifacts": {"property_id": created_id}},
        )

    return dispatch


# ---------------------------------------------------------------------------
# Planning / start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_loop_without_plan_or_state_asks_for_a_plan():
    result = await run_loop("do something", _portal_config(), ".", "trace-1")
    assert "needs a plan" in result
    assert "loop start --plan" in result


@pytest.mark.asyncio
async def test_run_loop_pauses_at_first_write():
    with patch("hubspot_agent.orchestrator.dispatch_agent", _fake_dispatch()):
        result = await run_loop(
            "create property", _portal_config(), ".", "trace-2", plan=_write_plan()
        )

    assert "paused" in result.lower()
    assert "act-1" in result
    assert "hubspot approve act-1" in result

    state = loop_state.load("123")
    assert state is not None
    assert state.status == "awaiting_approval"
    assert state.pending_action_id == "act-1"
    assert state.current_step == 0  # not advanced until verified


@pytest.mark.asyncio
async def test_run_loop_runs_read_step_then_pauses_at_write():
    plan = LoopPlan(
        goal="Find then create",
        steps=[
            PlanStep(step_number=1, agent="objects", action="find contacts", risk_level=RiskLevel.LOW),
            PlanStep(step_number=2, agent="properties", action="create property x", risk_level=RiskLevel.MEDIUM),
        ],
        overall_risk=RiskLevel.MEDIUM,
    )
    calls: list[tuple[str, str]] = []

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        calls.append((agent_name, mode))
        if mode == "preview":
            return AgentResult(agent_name=agent_name, status="preview",
                               data={"action_id": "act-9", "risk_level": "medium", "impact_count": 1,
                                     "intent_type": "create", "preview": "p"})
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("find then create", _portal_config(), ".", "trace-rw", plan=plan)

    # Read step executed, then paused at the write step.
    assert ("objects", "execute") in calls
    assert ("properties", "preview") in calls
    assert "paused" in result.lower()
    state = loop_state.load("123")
    assert state.current_step == 1  # read step advanced


@pytest.mark.asyncio
async def test_run_loop_pauses_on_risky_step_without_write_verb():
    # "purge" is not in is_write_step's verb set, but the plan marks it
    # destructive — it must still pause for approval, not execute as a read.
    plan = LoopPlan(
        goal="Purge stale deals",
        steps=[PlanStep(step_number=1, agent="objects", action="purge stale deals",
                        risk_level=RiskLevel.DESTRUCTIVE)],
        overall_risk=RiskLevel.DESTRUCTIVE,
    )
    with patch("hubspot_agent.orchestrator.dispatch_agent", _fake_dispatch(action_id="act-purge")):
        result = await run_loop("purge stale deals", _portal_config(), ".", "trace-risk", plan=plan)

    assert "paused" in result.lower()
    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    assert state.pending_action_id == "act-purge"


@pytest.mark.asyncio
async def test_run_loop_rejects_uncapable_plan():
    plan = LoopPlan(
        goal="Create workflow",
        steps=[PlanStep(step_number=1, agent="workflows", action="create workflow", risk_level=RiskLevel.MEDIUM)],
        overall_risk=RiskLevel.MEDIUM,
    )
    result = await run_loop("create workflow", _portal_config(tier="Free"), ".", "trace-cap", plan=plan)
    assert "cannot be executed" in result
    assert "workflow" in result.lower()


@pytest.mark.asyncio
async def test_run_loop_preview_error_stops():
    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        return AgentResult(agent_name=agent_name, status="error", error_message="api down")

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("create property", _portal_config(), ".", "trace-4", plan=_write_plan())

    assert "Execution stopped" in result
    assert "api down" in result
    assert loop_state.load("123").status == "failed"


# ---------------------------------------------------------------------------
# Proxy budget (Phase 3 PR-A): per-step enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_loop_stops_mid_run_at_step_budget():
    # Two read steps, but max_steps=1: the loop must stop BEFORE the second
    # step (per-step enforcement, not only at the post-write verify checkpoint).
    plan = LoopPlan(
        goal="Two reads",
        steps=[
            PlanStep(step_number=1, agent="objects", action="find contacts", risk_level=RiskLevel.LOW),
            PlanStep(step_number=2, agent="objects", action="find companies", risk_level=RiskLevel.LOW),
        ],
        overall_risk=RiskLevel.LOW,
        max_steps=1,
    )

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("two reads", _portal_config(), ".", "trace-budget", plan=plan)

    assert "budget exhausted" in result.lower()
    state = loop_state.load("123")
    assert state is not None
    assert state.status == "stopped"
    assert state.current_step == 1  # first step executed, stopped before the second
    assert state.step_count == 1

    from hubspot_agent import loop_log
    events = loop_log.get_recent("123", trace_id="trace-budget")
    assert any(e["event_type"] == "budget_exhausted" for e in events)


@pytest.mark.asyncio
async def test_run_loop_stops_mid_run_at_api_call_budget():
    plan = LoopPlan(
        goal="Two reads",
        steps=[
            PlanStep(step_number=1, agent="objects", action="find contacts", risk_level=RiskLevel.LOW),
            PlanStep(step_number=2, agent="objects", action="find companies", risk_level=RiskLevel.LOW),
        ],
        overall_risk=RiskLevel.LOW,
        max_api_calls=1,
    )

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("two reads", _portal_config(), ".", "trace-apibudget", plan=plan)

    assert "budget exhausted" in result.lower()
    state = loop_state.load("123")
    assert state.status == "stopped"
    assert state.api_call_count == 1


# ---------------------------------------------------------------------------
# Back-pressure (Phase 3 PR-B): per-step retry + proactive pacing
# ---------------------------------------------------------------------------


def _one_read_plan() -> LoopPlan:
    return LoopPlan(
        goal="one read",
        steps=[PlanStep(step_number=1, agent="objects", action="find contacts",
                        risk_level=RiskLevel.LOW)],
        overall_risk=RiskLevel.LOW,
    )


def _two_read_plan() -> LoopPlan:
    return LoopPlan(
        goal="two reads",
        steps=[
            PlanStep(step_number=1, agent="objects", action="find contacts", risk_level=RiskLevel.LOW),
            PlanStep(step_number=2, agent="objects", action="find companies", risk_level=RiskLevel.LOW),
        ],
        overall_risk=RiskLevel.LOW,
    )


@pytest.fixture
def _no_wait(monkeypatch):
    """Replace the loop's injectable sleep with a spy that records, never waits."""
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("hubspot_agent.orchestrator._sleep", fake_sleep)
    return slept


@pytest.mark.asyncio
async def test_read_step_retries_transient_then_succeeds(_no_wait):
    from hubspot_agent.errors import RateLimitError

    calls = {"n": 0}

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError("rate limited", retry_after=1)
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("one read", _portal_config(), ".", "trace-retry", plan=_one_read_plan())

    assert calls["n"] == 3  # failed twice, succeeded on the third attempt
    assert "completed" in result.lower()
    assert loop_state.load("123") is None  # single read completed → cleared
    assert _no_wait == [1, 1]  # Retry-After (1s) honored on both backoffs

    from hubspot_agent import loop_log
    events = loop_log.get_recent("123", trace_id="trace-retry")
    assert sum(1 for e in events if e["event_type"] == "step_retry") == 2


@pytest.mark.asyncio
async def test_read_step_exponential_backoff_without_retry_after(_no_wait):
    from hubspot_agent.errors import ErrorCategory, HubSpotError

    calls = {"n": 0}

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise HubSpotError("server blip", status_code=503, category=ErrorCategory.SERVER)
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        await run_loop("one read", _portal_config(), ".", "trace-backoff", plan=_one_read_plan())

    # No server Retry-After on a 5xx → exponential backoff: 2**0, 2**1.
    assert _no_wait == [1, 2]


@pytest.mark.asyncio
async def test_read_step_fails_after_retry_budget(_no_wait):
    from hubspot_agent.errors import RateLimitError

    calls = {"n": 0}

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        calls["n"] += 1
        raise RateLimitError("still down", retry_after=0)

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("one read", _portal_config(), ".", "trace-budget-x", plan=_one_read_plan())

    assert calls["n"] == 3  # _READ_RETRY_BUDGET attempts, then fail-and-stop
    assert "Execution stopped" in result
    assert "still down" in result
    assert loop_state.load("123").status == "failed"


@pytest.mark.asyncio
async def test_read_step_terminal_error_not_retried(_no_wait):
    from hubspot_agent.errors import ErrorCategory, HubSpotError

    calls = {"n": 0}

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        calls["n"] += 1
        raise HubSpotError("bad request", status_code=400, category=ErrorCategory.VALIDATION)

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("one read", _portal_config(), ".", "trace-terminal", plan=_one_read_plan())

    assert calls["n"] == 1  # non-transient → no retries
    assert _no_wait == []  # never slept
    assert "Execution stopped" in result
    assert loop_state.load("123").status == "failed"


@pytest.mark.asyncio
async def test_write_step_preview_retried_but_write_never_executed(_no_wait):
    # Safety invariant: the write mutation is out-of-band (hubspot approve). The
    # loop retries only the PREVIEW build (a read) and then pauses — it never
    # executes the write, so the write is never auto-retried.
    from hubspot_agent.errors import RateLimitError

    modes: list[str] = []
    preview_calls = {"n": 0}

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        modes.append(mode)
        if mode == "preview":
            preview_calls["n"] += 1
            if preview_calls["n"] < 2:
                raise RateLimitError("blip", retry_after=0)
            return AgentResult(
                agent_name=agent_name, status="preview",
                data={"action_id": "act-w", "risk_level": "medium", "impact_count": 1,
                      "intent_type": "create", "preview": "p"},
            )
        raise AssertionError("write step must never execute in-loop — it must pause for approval")

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        result = await run_loop("create property", _portal_config(), ".", "trace-wr", plan=_write_plan())

    assert modes == ["preview", "preview"]  # preview retried once, then paused
    assert "paused" in result.lower()
    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    assert state.pending_action_id == "act-w"


@pytest.mark.asyncio
async def test_pacing_sleeps_before_next_step_when_remaining_low(monkeypatch, _no_wait):
    import time

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    # After each step the client reports few requests left with a reset 30s out.
    monkeypatch.setattr("hubspot_agent.orchestrator.get_last_rate_state",
                        lambda portal_id: (2, time.time() + 30))

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        await run_loop("two reads", _portal_config(), ".", "trace-pace", plan=_two_read_plan())

    # Step 1: no header seen yet → no pace. Step 2: low remaining → one pace.
    assert len(_no_wait) == 1
    assert 0 < _no_wait[0] <= 60

    from hubspot_agent import loop_log
    events = loop_log.get_recent("123", trace_id="trace-pace")
    assert any(e["event_type"] == "paced" for e in events)


@pytest.mark.asyncio
async def test_pacing_no_sleep_when_remaining_high(monkeypatch, _no_wait):
    import time

    async def dispatch(agent_name, request_text, portal_config=None, mode="preview", **kwargs):
        return AgentResult(agent_name=agent_name, status="success", data={"artifacts": {}})

    monkeypatch.setattr("hubspot_agent.orchestrator.get_last_rate_state",
                        lambda portal_id: (500, time.time() + 30))

    with patch("hubspot_agent.orchestrator.dispatch_agent", dispatch):
        await run_loop("two reads", _portal_config(), ".", "trace-nopace", plan=_two_read_plan())

    assert _no_wait == []  # ample quota → never paced


# ---------------------------------------------------------------------------
# Resume disambiguation (awaiting_approval)
# ---------------------------------------------------------------------------


def _save_awaiting_state(action_id: str = "act-1") -> None:
    state = loop_state.LoopState(
        portal_id="123",
        request_text="create property",
        trace_id="trace-resume",
        plan=_write_plan(),
        current_step=0,
        status="awaiting_approval",
        pending_action_id=action_id,
    )
    loop_state.save(state)


@pytest.mark.asyncio
async def test_resume_still_awaiting_reprompts():
    _save_awaiting_state()
    with patch("hubspot_agent.orchestrator._load_pending_preview", return_value={"action_id": "act-1"}):
        result = await run_loop("create property", _portal_config(), ".", "trace-r1")
    assert "still awaiting approval" in result
    assert "hubspot approve act-1" in result
    assert loop_state.load("123").status == "awaiting_approval"


@pytest.mark.asyncio
async def test_resume_after_approve_moves_to_verification():
    _save_awaiting_state()
    with patch("hubspot_agent.orchestrator._load_pending_preview", return_value=None), \
         patch("hubspot_agent.audit.get_recent_audits", return_value=[{"action": "approve:act-1"}]), \
         patch(
             "hubspot_agent.orchestrator.load_undo_snapshot",
             return_value={"metadata": {"created_ids": ["prop-123"], "target_object": "contacts"}},
         ):
        result = await run_loop("create property", _portal_config(), ".", "trace-r2")

    assert "loop verify" in result
    state = loop_state.load("123")
    assert state.status == "awaiting_verification"
    # Artifact captured from the undo snapshot, threaded under the declared key.
    assert state.artifacts[0].created_ids == ["prop-123"]
    assert state.artifacts[0].outputs.get("property_id") == "prop-123"


@pytest.mark.asyncio
async def test_resume_rejected_stops_loop():
    _save_awaiting_state()
    with patch("hubspot_agent.orchestrator._load_pending_preview", return_value=None), \
         patch("hubspot_agent.audit.get_recent_audits", return_value=[]):
        result = await run_loop("create property", _portal_config(), ".", "trace-r3")

    assert "rejected or cancelled" in result
    assert loop_state.load("123").status == "stop"


# ---------------------------------------------------------------------------
# loop_verify
# ---------------------------------------------------------------------------


def _save_awaiting_verification_state(created_ids=("prop-123",)) -> None:
    from hubspot_agent.models import StepArtifact

    created = list(created_ids)
    action = "create property" if created else "update property"
    plan = LoopPlan(
        goal="Change a property",
        steps=[PlanStep(step_number=1, agent="properties", action=action,
                        expected_artifact_keys=["property_id"], risk_level=RiskLevel.MEDIUM)],
        overall_risk=RiskLevel.MEDIUM,
        max_iterations=3,
    )
    outputs = {"property_id": created[0]} if created else {}
    state = loop_state.LoopState(
        portal_id="123",
        request_text="change property",
        trace_id="trace-verify",
        plan=plan,
        current_step=0,
        status="awaiting_verification",
        artifacts=[StepArtifact(step_number=1, agent="properties", outputs=outputs, created_ids=created)],
    )
    loop_state.save(state)


@pytest.mark.asyncio
async def test_loop_verify_proceed_completes_single_step():
    _save_awaiting_verification_state()
    result = await loop_verify(
        '{"status": "verified", "checked_count": 1, "verified_count": 1}',
        _portal_config(), ".",
    )
    assert "completed" in result.lower()
    assert loop_state.load("123") is None  # cleared on completion


@pytest.mark.asyncio
async def test_loop_verify_mismatch_retries_and_repauses():
    # An update (no created_ids) can be safely re-driven on a mismatch retry.
    _save_awaiting_verification_state(created_ids=[])
    with patch("hubspot_agent.orchestrator.dispatch_agent", _fake_dispatch(action_id="act-retry")):
        result = await loop_verify(
            '{"status": "mismatch", "mismatches": [{"field": "name"}]}',
            _portal_config(), ".",
        )
    assert "paused" in result.lower()
    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    assert state.pending_action_id == "act-retry"
    assert state.iterations == 1  # controller recorded the retry


@pytest.mark.asyncio
async def test_loop_verify_retry_after_create_escalates_not_duplicates():
    # A create already committed; a mismatch "retry" would duplicate the record,
    # so the loop escalates for human review instead of re-driving.
    _save_awaiting_verification_state(created_ids=["prop-123"])
    result = await loop_verify(
        '{"status": "mismatch", "mismatches": [{"field": "name"}]}',
        _portal_config(), ".",
    )
    assert "halted" in result.lower()
    assert "duplicate" in result.lower()
    state = loop_state.load("123")
    assert state.status == "escalate"


@pytest.mark.asyncio
async def test_loop_verify_error_escalates():
    _save_awaiting_verification_state()
    result = await loop_verify(
        '{"status": "error", "message": "verification blew up"}',
        _portal_config(), ".",
    )
    assert "halted" in result.lower()
    assert loop_state.load("123").status == "escalate"


@pytest.mark.asyncio
async def test_loop_verify_without_awaiting_state_is_noop():
    result = await loop_verify('{"status": "verified"}', _portal_config(), ".")
    assert "No active loop" in result


@pytest.mark.asyncio
async def test_loop_verify_unparseable_result():
    _save_awaiting_verification_state()
    result = await loop_verify("not json at all", _portal_config(), ".")
    assert "Could not parse" in result
    assert loop_state.load("123").status == "awaiting_verification"  # unchanged


# ---------------------------------------------------------------------------
# Backwards-compat flat dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_simple_backwards_compatible():
    config = _portal_config()
    results = await run_simple("find contacts", config)
    assert any(r.agent_name == "objects" for r in results)
    assert all(r.status == "preview" for r in results)


# ---------------------------------------------------------------------------
# execute-mode fallback: a handler-less agent must not fabricate success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_mode_errors_for_handler_less_agent():
    from hubspot_agent.orchestrator import dispatch_agent

    # 'analytics' is a read-only agent with no execute handler registered.
    # Executing it must return an error, not a fabricated "success" (which would
    # otherwise claim a write happened and mislead the approve/undo path).
    result = await dispatch_agent("analytics", "run a report", _portal_config(), mode="execute")
    assert result.status == "error"
    assert "no execute handler" in (result.error_message or "")


# ---------------------------------------------------------------------------
# M12 residual: an unexpected raise inside the drive loop must park the loop
# as "failed" on disk — not leave it "running", where the next continue would
# resume straight into the same crash.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_raise_marks_loop_failed():
    from hubspot_agent import loop_log

    async def _boom(portal_config, state, working_dir):
        raise RuntimeError("artifact resolution exploded")

    with patch("hubspot_agent.orchestrator._drive_loop", side_effect=_boom):
        result = await run_loop("create a property", _portal_config(), "/tmp", "trace-crash", plan=_write_plan())

    assert "Loop crashed" in result
    state = loop_state.load("123")
    assert state is not None
    assert state.status == "failed"
    assert "artifact resolution exploded" in (state.last_error or "")
    events = loop_log.get_recent("123", trace_id="trace-crash")
    assert any(e["event_type"] == "loop_crashed" for e in events)
