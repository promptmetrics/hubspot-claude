from unittest.mock import MagicMock, patch

from hubspot_agent.agent_dispatch import build_triage_prompt, build_verify_prompt, spawn_agent
from hubspot_agent.config import PortalConfig


def test_spawn_agent_without_runtime_returns_placeholder():
    result = spawn_agent("triage", "do something")
    assert result == "[agent:triage:no_runtime]"


def test_spawn_agent_with_runtime():
    fake_agent = MagicMock(return_value="plan json here")
    with patch.dict("sys.modules", {"claude_code": MagicMock(Agent=fake_agent)}):
        # Force re-import path by patching the local reference
        import hubspot_agent.agent_dispatch as dispatch_module

        original = getattr(dispatch_module, "RuntimeAgent", None)
        dispatch_module.RuntimeAgent = fake_agent
        try:
            result = spawn_agent("verify", "verify this")
            assert result == "plan json here"
        finally:
            if original is not None:
                dispatch_module.RuntimeAgent = original
            else:
                del dispatch_module.RuntimeAgent


def test_build_triage_prompt_contains_request():
    prompt = build_triage_prompt("create a property and workflow")
    assert "create a property and workflow" in prompt
    assert "LoopPlan" in prompt


def test_build_verify_prompt_contains_expected_state():
    step = {"agent": "properties", "action": "create property"}
    expected = {"property_id": "prop-123"}
    prompt = build_verify_prompt(step, expected)
    assert "properties" in prompt
    assert "prop-123" in prompt
    assert "VerificationResult" in prompt


def test_build_verify_prompt_uses_portal_context():
    config = PortalConfig(portal_id="123", token="test", tier="Professional")
    prompt = build_verify_prompt({}, {}, portal_config=config)
    assert "Portal ID: 123" in prompt
