from hubspot_agent.agents._base import SELF_CORRECTION_PROMPT_BLOCK, build_agent_prompt
from hubspot_agent.models import AgentResult
from hubspot_agent.orchestrator import dispatch_correction


def test_self_correction_block_in_prompt():
    prompt = build_agent_prompt(
        agent_name="Test Agent",
        domain_description="You test things.",
        available_tools=[],
    )
    assert SELF_CORRECTION_PROMPT_BLOCK in prompt.system_prompt
    assert "VALIDATION errors" in prompt.system_prompt
    assert "CONFLICT errors" in prompt.system_prompt
    assert "NOT_FOUND errors" in prompt.system_prompt


def test_dispatch_correction_unknown_agent():
    original = AgentResult(agent_name="objects", status="error", error_message="validation failed")
    result = dispatch_correction(
        agent_name="fake_agent",
        user_request="create a contact",
        original_result=original,
        corrected_payload={"email": "test@example.com"},
        correction_reason="fixed typo in property name",
    )
    assert result.status == "error"
    assert "Unknown agent" in (result.error_message or "")


def test_dispatch_correction_returns_corrected_status():
    original = AgentResult(agent_name="objects", status="error", error_message="validation failed")
    result = dispatch_correction(
        agent_name="objects",
        user_request="create a contact",
        original_result=original,
        corrected_payload={"email": "test@example.com"},
        correction_reason="fixed typo in property name",
    )
    assert result.status == "corrected"
    assert result.corrected_payload == {"email": "test@example.com"}
    assert result.correction_reason == "fixed typo in property name"
    assert result.data["corrected_payload"] == {"email": "test@example.com"}
    assert "fixed typo in property name" in result.data["full_prompt"]
    assert "validation failed" in result.data["full_prompt"]


def test_agent_result_model_supports_correction_fields():
    result = AgentResult(
        agent_name="objects",
        status="corrected",
        corrected_payload={"email": "test@example.com"},
        correction_reason="fixed typo",
    )
    assert result.corrected_payload == {"email": "test@example.com"}
    assert result.correction_reason == "fixed typo"
