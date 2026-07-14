from unittest.mock import patch

import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.loop_state import LoopState
from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel


def _setup_portal(tmp_path, monkeypatch):
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", tmp_path / ".claude" / "hubspot")


def _make_state(request_text: str = "create two properties") -> LoopState:
    plan = LoopPlan(
        goal="Create two properties",
        steps=[
            PlanStep(step_number=1, agent="properties", action="create property a", risk_level=RiskLevel.MEDIUM),
            PlanStep(step_number=2, agent="properties", action="create property b", risk_level=RiskLevel.MEDIUM),
        ],
    )
    return LoopState(
        portal_id="123",
        request_text=request_text,
        trace_id="trace-continue",
        plan=plan,
        current_step=1,
        status="running",
    )


def test_continue_no_portal(tmp_path):
    result = hubspot_command("continue", working_dir=str(tmp_path))
    assert "No default portal found" in result


def test_continue_no_active_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("continue", working_dir=str(tmp_path))
    assert "No active loop to continue" in result


def test_abandon_no_active_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("abandon", working_dir=str(tmp_path))
    assert "No active loop to abandon" in result


def test_loop_status_no_active_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("loop status", working_dir=str(tmp_path))
    assert "No active loop for this portal" in result


def test_loop_log_no_entries(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("loop log", working_dir=str(tmp_path))
    assert "No loop log entries" in result


@pytest.mark.asyncio
async def test_continue_resumes_run_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    state = _make_state()
    from hubspot_agent import loop_state
    loop_state.save(state)

    with patch("hubspot_agent.cli.run_loop") as mock_run_loop:
        result = hubspot_command("continue", working_dir=str(tmp_path))

    mock_run_loop.assert_called_once()
    assert result == mock_run_loop.return_value


def test_abandon_clears_state(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    from hubspot_agent import loop_state
    state = _make_state()
    loop_state.save(state)

    result = hubspot_command("abandon", working_dir=str(tmp_path))
    assert "Abandoned active loop" in result
    assert loop_state.load("123") is None


def test_loop_status_shows_state(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    from hubspot_agent import loop_state
    loop_state.save(_make_state())

    result = hubspot_command("loop status", working_dir=str(tmp_path))
    assert "Loop status for portal 123" in result
    assert "Create two properties" in result
    assert "running" in result
    assert "Step: 2 of 2" in result


def test_loop_log_shows_entries(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    from hubspot_agent import loop_log, loop_state
    state = _make_state()
    loop_state.save(state)
    loop_log.log_event("123", "trace-continue", "step_started", {"step": 1})
    loop_log.log_event("123", "trace-continue", "step_completed", {"step": 1})

    result = hubspot_command("loop log", working_dir=str(tmp_path))
    assert "Recent loop log for portal 123" in result
    assert "step_started" in result
    assert "step_completed" in result


def test_loop_checkpoint_no_active_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("loop checkpoint", working_dir=str(tmp_path))
    assert "No active loop to checkpoint" in result


def test_loop_checkpoint_persists_and_logs(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    from hubspot_agent import loop_log, loop_state
    state = _make_state()
    loop_state.save(state)
    original_updated_at = state.updated_at

    result = hubspot_command("loop checkpoint", working_dir=str(tmp_path))
    assert "Checkpointed loop for portal 123" in result
    assert "step 2 of 2" in result

    events = loop_log.get_recent("123", trace_id="trace-continue", limit=50)
    assert any(e.get("event_type") == "loop_checkpoint" for e in events)

    reloaded = loop_state.load("123")
    assert reloaded is not None
    assert reloaded.updated_at >= original_updated_at


@pytest.mark.asyncio
async def test_loop_continue_alias_routes_to_handler(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    from hubspot_agent import loop_state
    loop_state.save(_make_state())

    with patch("hubspot_agent.cli.run_loop") as mock_run_loop:
        result = hubspot_command("loop continue", working_dir=str(tmp_path))

    mock_run_loop.assert_called_once()
    assert result == mock_run_loop.return_value


def test_loop_abandon_alias_clears_state(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    from hubspot_agent import loop_state
    loop_state.save(_make_state())

    result = hubspot_command("loop abandon", working_dir=str(tmp_path))
    assert "Abandoned active loop" in result
    assert loop_state.load("123") is None


def test_loop_unknown_subcommand_returns_usage(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("loop bogus", working_dir=str(tmp_path))
    assert "Usage: /hubspot loop" in result
    assert "checkpoint" in result
    assert "continue" in result
    assert "abandon" in result
    assert "start" in result
    assert "verify" in result


def test_extract_flag_value_forms():
    from hubspot_agent.cli import _extract_flag_value

    assert _extract_flag_value('--plan {"a": 1}', "plan") == '{"a": 1}'
    assert _extract_flag_value('--plan={"a": 1}', "plan") == '{"a": 1}'
    # Bare text with no recognized flag yields "" so the caller shows usage.
    assert _extract_flag_value("foo bar", "plan") == ""
    assert _extract_flag_value("", "plan") == ""


def test_loop_start_without_flag_returns_usage(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("loop start foo bar", working_dir=str(tmp_path))
    assert "Usage: /hubspot loop start --plan" in result


def test_loop_verify_without_flag_returns_usage(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)
    result = hubspot_command("loop verify garbage", working_dir=str(tmp_path))
    assert "Usage: /hubspot loop verify --result" in result


@pytest.mark.asyncio
async def test_loop_start_emits_trace_event_and_pauses(tmp_path, monkeypatch):
    """Bug 1: ``loop start --plan`` must emit the ``loop_start`` trace event
    (real, non-mocked ``emit_trace`` — previously crashed because ``loop_start``
    was absent from ``EVENT_TYPES``) and park the loop at ``awaiting_approval``."""
    import json as _json

    from hubspot_agent import loop_state
    from hubspot_agent.models import PreviewResult, RiskLevel
    from hubspot_agent.trace import get_recent_traces

    _setup_portal(tmp_path, monkeypatch)
    # apply_write persists the pending preview via persistence.CONFIG_DIR; like
    # test_loop_e2e.loop_dirs, point every on-disk root at the temp tree.
    root = tmp_path / ".claude" / "hubspot"
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", root)

    async def _fake_preview(agent_name, intent, client, portal_id):
        return PreviewResult(
            preview={"message": "Will create property renewal_date"},
            impact_count=1,
            risk_level=RiskLevel.MEDIUM,
            proposed_payload={"name": "renewal_date", "type": "date"},
            original_values={},
            informing_sources=[],
        )

    monkeypatch.setattr("hubspot_agent.orchestrator._build_preview_for_intent", _fake_preview)

    plan = {
        "goal": "Create a custom contact property renewal_date",
        "success_criteria": ["property exists"],
        "steps": [
            {
                "step_number": 1,
                "agent": "properties",
                "action": "create property renewal_date",
                "expected_artifact_keys": ["property_id"],
                "risk_level": "medium",
            }
        ],
        "overall_risk": "medium",
        "max_iterations": 3,
    }
    result = hubspot_command(
        f"loop start --plan {_json.dumps(plan)}", working_dir=str(tmp_path)
    )

    assert "paused" in result.lower()
    state = loop_state.load("123")
    assert state is not None
    assert state.status == "awaiting_approval"
    assert state.pending_action_id

    events = get_recent_traces("123")
    assert any(e.event_type == "loop_start" for e in events)
