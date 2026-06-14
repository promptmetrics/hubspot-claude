from hubspot_agent.agents.verify import _READ_ONLY_TOOL_NAMES, get_verify_agent_prompt
from hubspot_agent.config import PortalConfig


def test_verify_agent_has_only_read_only_tools():
    prompt = get_verify_agent_prompt()
    assert prompt.tool_names
    for name in prompt.tool_names:
        assert not name.startswith("hubspot_create_")
        assert not name.startswith("hubspot_update_")
        assert not name.startswith("hubspot_delete_")
        assert not name.startswith("hubspot_enroll_")
        assert not name.startswith("hubspot_toggle_")
        assert not name.startswith("hubspot_merge_")
        assert not name.startswith("hubspot_bulk_update_")
        assert not name.startswith("hubspot_add_to_list")
        assert not name.startswith("hubspot_remove_from_list")
        assert not name.startswith("hubspot_associate_records")
        assert not name.startswith("hubspot_disassociate_records")


def test_verify_agent_prompt_has_instructions():
    prompt = get_verify_agent_prompt()
    assert "Verify Agent" in prompt.system_prompt
    assert "VerificationResult" in prompt.system_prompt
    assert "never write" in prompt.system_prompt.lower()


def test_verify_agent_tools_list_is_stable():
    assert "hubspot_get_object" in _READ_ONLY_TOOL_NAMES
    assert "hubspot_search_objects" in _READ_ONLY_TOOL_NAMES
    assert "hubspot_get_workflow" in _READ_ONLY_TOOL_NAMES


def test_verify_agent_prompt_uses_portal_context():
    config = PortalConfig(portal_id="123", token="test", tier="Professional")
    prompt = get_verify_agent_prompt(config)
    assert "Portal ID: 123" in prompt.system_prompt
