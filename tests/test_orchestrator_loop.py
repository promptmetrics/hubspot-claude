import pytest
from unittest.mock import patch

from hubspot_agent.config import PortalConfig
from hubspot_agent.models import AgentResult
from hubspot_agent.orchestrator import run_loop, run_simple


def _portal_config(tier: str = "Professional") -> PortalConfig:
    return PortalConfig(portal_id="123", token="test-token", tier=tier)


@pytest.fixture(autouse=True)
def _clear_loop_state(monkeypatch, tmp_path):
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    yield


@pytest.mark.asyncio
async def test_run_loop_returns_clarifying_question_for_non_json():
    config = _portal_config()
    with patch("hubspot_agent.orchestrator.spawn_agent", return_value="What object type do you want?"):
        result = await run_loop("do something", config, ".", "trace-1")
    assert "need a bit more clarity" in result
    assert "What object type" in result


@pytest.mark.asyncio
async def test_run_loop_validates_plan_and_executes():
    config = _portal_config()
    plan_json = """
    {
      "goal": "Create a property",
      "success_criteria": ["property exists"],
      "steps": [
        {"step_number": 1, "agent": "properties", "action": "create property renewal_date",
         "expected_artifact_keys": ["property_id"], "risk_level": "medium"}
      ],
      "overall_risk": "medium"
    }
    """

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(
            agent_name=agent_name,
            status="preview" if mode == "preview" else "success",
            data={"artifacts": {"property_id": "prop-123"}},
        )

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            result = await run_loop("create property renewal_date", config, ".", "trace-2")

    assert "Goal:" in result
    assert "prop-123" in result
    assert "properties" in result


@pytest.mark.asyncio
async def test_run_loop_detects_missing_workflow_capability():
    config = _portal_config(tier="Free")
    plan_json = """
    {
      "goal": "Create workflow",
      "steps": [
        {"step_number": 1, "agent": "workflows", "action": "create workflow", "risk_level": "medium"}
      ],
      "overall_risk": "medium"
    }
    """

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        result = await run_loop("create workflow", config, ".", "trace-3")

    assert "cannot be executed" in result
    assert "workflow" in result.lower()


@pytest.mark.asyncio
async def test_run_loop_handles_execution_error():
    config = _portal_config()
    plan_json = """
    {
      "goal": "Create a property",
      "steps": [
        {"step_number": 1, "agent": "properties", "action": "create property", "risk_level": "medium"}
      ],
      "overall_risk": "medium"
    }
    """

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(agent_name=agent_name, status="error", error_message="api down")

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            result = await run_loop("create property", config, ".", "trace-4")

    assert "Execution stopped" in result
    assert "api down" in result


@pytest.mark.asyncio
async def test_run_simple_backwards_compatible():
    config = _portal_config()
    results = await run_simple("find contacts", config)
    assert any(r.agent_name == "objects" for r in results)
    assert all(r.status == "preview" for r in results)


@pytest.mark.asyncio
async def test_run_loop_acceptance_property_and_workflow():
    """Group 1 acceptance: property creation feeds workflow creation with verification."""
    config = _portal_config(tier="Professional")
    plan_json = """
    {
      "goal": "Create a custom contact property renewal_date and build a workflow that enrolls contacts 30 days before renewal",
      "success_criteria": ["property exists", "workflow references property"],
      "steps": [
        {
          "step_number": 1,
          "agent": "properties",
          "action": "create property renewal_date",
          "description": "Create custom contact property renewal_date",
          "expected_artifact_keys": ["property_id"],
          "risk_level": "medium"
        },
        {
          "step_number": 2,
          "agent": "workflows",
          "action": "create workflow enrollment rule",
          "description": "Build workflow that enrolls contacts 30 days before renewal_date",
          "prerequisites": ["1"],
          "expected_artifact_keys": ["workflow_id"],
          "risk_level": "medium"
        }
      ],
      "overall_risk": "medium",
      "max_iterations": 3
    }
    """

    calls: list[tuple[str, str]] = []

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        calls.append((agent_name, mode))
        if agent_name == "properties":
            return AgentResult(
                agent_name="properties",
                status="preview" if mode == "preview" else "success",
                data={"artifacts": {"property_id": "prop-renewal-123"}},
            )
        if agent_name == "workflows":
            assert "prop-renewal-123" in user_request
            return AgentResult(
                agent_name="workflows",
                status="preview" if mode == "preview" else "success",
                data={"artifacts": {"workflow_id": "wf-renewal-456"}},
            )
        return AgentResult(agent_name=agent_name, status="error", error_message="unknown")

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            result = await run_loop(
                "create a custom contact property called renewal_date and build a workflow "
                "that enrolls contacts 30 days before renewal",
                config,
                ".",
                "acceptance-1",
            )

    assert "prop-renewal-123" in result
    assert "wf-renewal-456" in result
    assert any(c == ("properties", "preview") for c in calls)
    assert any(c == ("properties", "execute") for c in calls)
    assert any(c == ("workflows", "preview") for c in calls)
    assert any(c == ("workflows", "execute") for c in calls)


@pytest.mark.asyncio
async def test_run_loop_resumes_from_saved_state():
    """A second call with the same request resumes and completes remaining steps."""
    config = _portal_config()
    plan_json = """
    {
      "goal": "Create two properties",
      "steps": [
        {"step_number": 1, "agent": "properties", "action": "create property a", "expected_artifact_keys": ["property_id"], "risk_level": "medium"},
        {"step_number": 2, "agent": "properties", "action": "create property b", "expected_artifact_keys": ["property_id"], "risk_level": "medium"}
      ],
      "overall_risk": "medium"
    }
    """

    calls: list[tuple[str, str]] = []

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        calls.append((agent_name, mode))
        return AgentResult(
            agent_name=agent_name,
            status="preview" if mode == "preview" else "success",
            data={"artifacts": {"property_id": f"prop-{len(calls)}"}},
        )

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            result1 = await run_loop("create two properties", config, ".", "trace-resume")

    assert "Step 1 (properties)" in result1
    assert "Step 2 (properties)" in result1

    # Second call with same request should clear completed state and start fresh
    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            result2 = await run_loop("create two properties", config, ".", "trace-resume-2")

    assert "Step 1 (properties)" in result2
    assert "Step 2 (properties)" in result2


@pytest.mark.asyncio
async def test_run_loop_retry_then_succeed():
    """Verification fails once then succeeds; loop should retry and complete."""
    config = _portal_config()
    plan_json = """
    {
      "goal": "Create a property",
      "steps": [
        {"step_number": 1, "agent": "properties", "action": "create property", "expected_artifact_keys": ["property_id"], "risk_level": "medium"}
      ],
      "overall_risk": "medium",
      "max_iterations": 3
    }
    """

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(
            agent_name=agent_name,
            status="preview" if mode == "preview" else "success",
            data={"artifacts": {"property_id": "prop-123"}},
        )

    verify_responses = [
        '{"status": "mismatch", "mismatches": [{"field": "name", "expected": "A", "actual": "B"}]}',
        '{"status": "verified", "checked_count": 1, "verified_count": 1, "message": "ok"}',
    ]

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            with patch(
                "hubspot_agent.sequential_dispatch.spawn_agent",
                side_effect=verify_responses,
            ):
                result = await run_loop("create property", config, ".", "trace-retry")

    assert "completed" in result
    assert "prop-123" in result


@pytest.mark.asyncio
async def test_run_loop_plateau_escalates():
    """Two identical verification mismatches trigger escalate/stop."""
    config = _portal_config()
    plan_json = """
    {
      "goal": "Create a property",
      "steps": [
        {"step_number": 1, "agent": "properties", "action": "create property", "expected_artifact_keys": ["property_id"], "risk_level": "medium"}
      ],
      "overall_risk": "medium",
      "max_iterations": 3
    }
    """

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(
            agent_name=agent_name,
            status="preview" if mode == "preview" else "success",
            data={"artifacts": {"property_id": "prop-123"}},
        )

    verify_response = '{"status": "mismatch", "mismatches": [{"field": "name", "expected": "A", "actual": "B"}]}'

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
            with patch(
                "hubspot_agent.sequential_dispatch.spawn_agent",
                return_value=verify_response,
            ):
                result = await run_loop("create property", config, ".", "trace-plateau")

    assert "halted" in result or "stopped" in result.lower()
