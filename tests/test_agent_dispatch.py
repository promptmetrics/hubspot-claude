from hubspot_agent.agent_dispatch import build_verify_prompt, spawn_agent
from hubspot_agent.config import PortalConfig


def test_spawn_agent_always_returns_no_runtime_placeholder():
    # There is no in-process Python runtime for spawning sub-agents: the durable
    # loop's reasoning is done by Claude in-session via the loop CLI subcommands.
    # spawn_agent is a stub retained only for the legacy execute_plan verify path.
    assert spawn_agent("triage", "do something") == "[agent:triage:no_runtime]"
    assert spawn_agent("verify", "verify this") == "[agent:verify:no_runtime]"


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
