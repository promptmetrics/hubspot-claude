import pytest

from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt, format_tool_descriptions
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import ToolDef


def test_format_tool_descriptions():
    tools = [
        ToolDef(name="tool_a", description="Does A", func=lambda: None, is_async=False),
        ToolDef(name="tool_b", description="Does B", func=lambda: None, is_async=False),
    ]
    text = format_tool_descriptions(tools)
    assert "- tool_a: Does A" in text
    assert "- tool_b: Does B" in text


def test_build_agent_prompt_basic():
    tools = [
        ToolDef(name="get_thing", description="Get a thing", func=lambda: None, is_async=False),
    ]
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="Testing domain.",
        available_tools=tools,
    )
    assert isinstance(prompt, AgentPrompt)
    assert prompt.agent_name == "Test Agent"
    assert "Testing domain." in prompt.system_prompt
    assert "get_thing" in prompt.system_prompt
    assert prompt.tool_names == ["get_thing"]


def test_build_agent_prompt_with_portal():
    tools = []
    portal = PortalConfig(portal_id="123", token="t", tier="Professional")
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="Testing domain.",
        available_tools=tools,
        portal_config=portal,
    )
    assert "Portal ID: 123" in prompt.system_prompt
    assert "Tier: Professional" in prompt.system_prompt


def test_build_agent_prompt_contains_self_correction_block():
    tools = []
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="Testing domain.",
        available_tools=tools,
    )
    assert "Self-correction rules" in prompt.system_prompt
    assert "VALIDATION errors" in prompt.system_prompt


def test_build_agent_prompt_contains_research_block():
    tools = []
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="Testing domain.",
        available_tools=tools,
    )
    assert "Research guidance" in prompt.system_prompt
    assert "site:developers.hubspot.com" in prompt.system_prompt
    assert "informing_sources" in prompt.system_prompt


def test_build_agent_prompt_research_block_before_reflection_block():
    tools = [
        ToolDef(name="create_thing", description="Create a thing", func=lambda: None, is_async=False),
    ]
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="Testing domain.",
        available_tools=tools,
    )
    research_idx = prompt.system_prompt.index("Research guidance")
    reflection_idx = prompt.system_prompt.index("Write verification")
    assert research_idx < reflection_idx


def test_build_agent_prompt_contains_terse_output_block():
    tools = []
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="Testing domain.",
        available_tools=tools,
    )
    assert "terse and final-result-oriented" in prompt.system_prompt
    terse_idx = prompt.system_prompt.index("terse and final-result-oriented")
    self_correction_idx = prompt.system_prompt.index("Self-correction rules")
    assert terse_idx < self_correction_idx
