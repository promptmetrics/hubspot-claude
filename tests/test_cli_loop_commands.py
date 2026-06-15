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
