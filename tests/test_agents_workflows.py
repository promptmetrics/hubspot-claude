from hubspot_agent.agents.workflows import get_workflows_agent_prompt


def test_workflows_agent_prompt_has_correct_tools():
    prompt = get_workflows_agent_prompt()
    assert prompt.agent_name == "Workflows Agent"
    expected = [
        "hubspot_get_workflow",
        "hubspot_list_workflows",
        "hubspot_create_workflow",
        "hubspot_create_workflow_from_blueprint",
        "hubspot_update_workflow",
        "hubspot_enroll_workflow",
        "hubspot_toggle_workflow",
    ]
    assert sorted(prompt.tool_names) == sorted(expected)
