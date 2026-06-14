from hubspot_agent.agents.triage import get_triage_agent_prompt
from hubspot_agent.config import PortalConfig


def test_triage_agent_prompt_has_no_tools():
    prompt = get_triage_agent_prompt()
    assert prompt.tool_names == []


def test_triage_agent_prompt_contains_instructions():
    prompt = get_triage_agent_prompt()
    assert "Triage Agent" in prompt.system_prompt
    assert "LoopPlan" in prompt.system_prompt
    assert "clarifying questions" in prompt.system_prompt


def test_triage_agent_prompt_respects_free_tier():
    config = PortalConfig(portal_id="123", token="test", tier="Free")
    prompt = get_triage_agent_prompt(config)
    assert "Workflows: no" in prompt.system_prompt


def test_triage_agent_prompt_respects_professional_tier():
    config = PortalConfig(portal_id="123", token="test", tier="Professional")
    prompt = get_triage_agent_prompt(config)
    assert "Workflows: yes" in prompt.system_prompt
