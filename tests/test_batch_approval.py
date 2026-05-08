from hubspot_agent.models import BatchApprovalMode, PreviewResult, RiskLevel
from hubspot_agent.orchestrator import dispatch_agent, parse_batch_mode, present_preview
from hubspot_agent.config import PortalConfig


def test_parse_batch_mode_single():
    mode, text = parse_batch_mode("create a contact")
    assert mode == BatchApprovalMode.SINGLE
    assert text == "create a contact"


def test_parse_batch_mode_batch():
    mode, text = parse_batch_mode("batch create contacts --batch")
    assert mode == BatchApprovalMode.BATCH
    assert text == "batch create contacts"


def test_parse_batch_mode_pattern():
    mode, text = parse_batch_mode("update deals --pattern")
    assert mode == BatchApprovalMode.PATTERN
    assert text == "update deals"


def test_parse_batch_mode_case_insensitive():
    mode, text = parse_batch_mode("Update Contacts --BATCH")
    assert mode == BatchApprovalMode.BATCH


def test_present_preview_batch_mode():
    result = PreviewResult(
        preview={},
        impact_count=5,
        risk_level=RiskLevel.MEDIUM,
        batch_mode=BatchApprovalMode.BATCH,
    )
    text = present_preview(result)
    assert "Batch mode" in text
    assert "Approve entire plan" in text


def test_present_preview_pattern_mode():
    result = PreviewResult(
        preview={},
        impact_count=10,
        risk_level=RiskLevel.MEDIUM,
        batch_mode=BatchApprovalMode.PATTERN,
        pattern_sample_size=3,
    )
    text = present_preview(result)
    assert "Pattern mode" in text
    assert "sample of 3 records" in text
    assert "Approve sample" in text


def test_present_preview_destructive_overrides_batch():
    result = PreviewResult(
        preview={},
        impact_count=1,
        risk_level=RiskLevel.DESTRUCTIVE,
        batch_mode=BatchApprovalMode.BATCH,
    )
    text = present_preview(result)
    assert "Batch mode" in text
    assert "Destructive action" not in text


def test_dispatch_agent_includes_batch_mode():
    result = dispatch_agent(
        "objects",
        "list contacts",
        batch_mode=BatchApprovalMode.BATCH,
    )
    assert result.status == "preview"
    assert result.data["batch_mode"] == "batch"
    assert "Batch approval mode: batch" in result.data["full_prompt"]


def test_dispatch_agent_pattern_mode_prompt():
    result = dispatch_agent(
        "objects",
        "list contacts",
        batch_mode=BatchApprovalMode.PATTERN,
    )
    assert "pattern" in result.data["full_prompt"].lower()
