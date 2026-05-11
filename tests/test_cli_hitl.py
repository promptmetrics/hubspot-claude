import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import save_portal_config, PortalConfig
from hubspot_agent.orchestrator import (
    _clear_pending_preview,
    _load_pending_preview,
    _store_pending_preview,
)


class TestCliHitlFlow:
    def test_normal_request_returns_preview(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
        monkeypatch.setattr(
            orchestrator, "_store_pending_preview", lambda pid, aid, data: None
        )

        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            orchestrator, "invoke_tool", mock_tool
        )

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        result = hubspot_command("find contacts", working_dir=str(tmp_path))
        assert "Preview" in result
        assert "Risk:" in result
        assert "Impact:" in result
        assert "Approve with" in result

    def test_approve_last_executes(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        async def mock_tool(*a, **k):
            return {"id": "1"}

        monkeypatch.setattr(
            orchestrator, "invoke_tool", mock_tool
        )

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        _store_pending_preview("123", "abc123", {
            "agent_name": "objects",
            "request_text": "create a contact",
            "intent": {"intent_type": "create", "target_object": "contacts"},
            "preview": {},
            "batch_mode": "single",
            "proposed_payload": {"properties": {"firstname": "Alice"}},
        })

        result = hubspot_command("y", working_dir=str(tmp_path))
        assert "Approved and executed" in result
        assert _load_pending_preview("123", "abc123") is None

    def test_reject_last_clears_preview(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        _store_pending_preview("123", "def456", {
            "agent_name": "objects",
            "request_text": "delete a contact",
            "intent": {},
            "preview": {},
            "batch_mode": "single",
        })

        result = hubspot_command("n", working_dir=str(tmp_path))
        assert "Rejected" in result
        assert _load_pending_preview("123", "def456") is None

    def test_approve_specific_id(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        async def mock_tool(*a, **k):
            return {"id": "1"}

        monkeypatch.setattr(
            orchestrator, "invoke_tool", mock_tool
        )

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        _store_pending_preview("123", "xyz789", {
            "agent_name": "objects",
            "request_text": "create a company",
            "intent": {"intent_type": "create", "target_object": "companies"},
            "preview": {},
            "batch_mode": "single",
            "proposed_payload": {},
        })

        result = hubspot_command("approve xyz789", working_dir=str(tmp_path))
        assert "Approved and executed" in result
        assert _load_pending_preview("123", "xyz789") is None

    def test_approve_no_pending_previews(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        result = hubspot_command("y", working_dir=str(tmp_path))
        assert "No pending previews" in result

    def test_approve_unknown_id(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        result = hubspot_command("approve unknown", working_dir=str(tmp_path))
        assert "No pending preview found" in result
