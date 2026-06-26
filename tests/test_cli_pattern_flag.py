"""T10: ``hubspot --pattern '<request>'`` → ``BatchApprovalMode.PATTERN``.

``parse_batch_mode`` recognises the ``--pattern`` flag (FR-10) and the CLI
propagates the resulting mode into ``dispatch_agents_parallel``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hubspot_agent import cli
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.models import AgentResult, BatchApprovalMode, RiskLevel
from hubspot_agent.orchestrator import parse_batch_mode


def test_parse_batch_mode_pattern_flag():
    mode, cleaned = parse_batch_mode("--pattern create a contact")
    assert mode is BatchApprovalMode.PATTERN
    assert "--pattern" not in cleaned
    assert "create a contact" in cleaned


def test_parse_batch_mode_pattern_flag_strips_only_the_flag():
    mode, cleaned = parse_batch_mode("reconcile stale deals --pattern")
    assert mode is BatchApprovalMode.PATTERN
    assert cleaned == "reconcile stale deals"


def test_parse_batch_mode_pattern_takes_precedence_over_single():
    mode, _ = parse_batch_mode("--pattern find contacts in northeast")
    assert mode is BatchApprovalMode.PATTERN


def test_parse_batch_mode_pattern_takes_precedence_over_batch():
    # --pattern is checked first, so a request with both flags is treated as
    # PATTERN (the more specific sample-verify-scale mode).
    mode, cleaned = parse_batch_mode("--pattern --batch create contacts")
    assert mode is BatchApprovalMode.PATTERN
    assert "--pattern" not in cleaned


@pytest.mark.asyncio
async def test_hubspot_command_pattern_propagates_to_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
    (tmp_path / ".hubspot-portal").write_text("123\n")
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    captured: dict = {}

    async def mock_dispatch_parallel(*args, **kwargs):
        captured["batch_mode"] = kwargs.get("batch_mode")
        return [
            AgentResult(
                agent_name="objects",
                status="preview",
                data={
                    "action_id": "pat-test",
                    "risk_level": RiskLevel.MEDIUM,
                    "impact_count": 1,
                    "preview": "Will create a contact",
                },
                informing_sources=[],
            )
        ]

    async def stub_init(_portal_id: str) -> None:
        return None

    async def stub_readiness(_agents, _portal_config) -> dict:
        return {"ready": True}

    monkeypatch.setattr(cli, "dispatch_agents_parallel", mock_dispatch_parallel)
    monkeypatch.setattr(cli, "initialize_session", stub_init)
    monkeypatch.setattr(cli, "check_dispatch_readiness", stub_readiness)

    from hubspot_agent.cli import hubspot_command

    result = hubspot_command("--pattern create a contact", working_dir=str(tmp_path))

    assert captured["batch_mode"] is BatchApprovalMode.PATTERN
    assert "pat-test" in result