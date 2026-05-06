from hubspot_agent.agents.analytics import get_analytics_agent_prompt


def test_analytics_agent_prompt_has_correct_tools():
    prompt = get_analytics_agent_prompt()
    assert prompt.agent_name == "Analytics Agent"
    expected = [
        "hubspot_get_report",
        "hubspot_calculate_metrics",
        "hubspot_pipeline_velocity",
    ]
    assert sorted(prompt.tool_names) == sorted(expected)
