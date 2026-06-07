import pytest

import hubspot_agent.agents.objects
from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import save_portal_config, PortalConfig
from hubspot_agent.models import AgentResult, RiskLevel
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
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
        monkeypatch.setattr(
            orchestrator, "_store_pending_preview", lambda pid, aid, data: None
        )

        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            hubspot_agent.agents.objects, "invoke_tool", mock_tool
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
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)

        async def mock_tool(*a, **k):
            return {"id": "1"}

        monkeypatch.setattr(
            hubspot_agent.agents.objects, "invoke_tool", mock_tool
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
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)

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
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)

        async def mock_tool(*a, **k):
            return {"id": "1"}

        monkeypatch.setattr(
            hubspot_agent.agents.objects, "invoke_tool", mock_tool
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
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)

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
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        result = hubspot_command("approve unknown", working_dir=str(tmp_path))
        assert "No pending preview found" in result

    def test_preview_renders_informing_sources(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
        monkeypatch.setattr(
            orchestrator, "_store_pending_preview", lambda pid, aid, data: None
        )

        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            hubspot_agent.agents.objects, "invoke_tool", mock_tool
        )

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        result = hubspot_command("find contacts", working_dir=str(tmp_path))
        # informing_sources is empty in synthetic preview, so "Sources:" should not appear
        assert "Sources:" not in result
        assert "Approve with" in result

    def test_approve_logs_informing_sources(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.audit._audit_file_path", lambda pid: tmp_path / "audit.log")

        async def mock_tool(*a, **k):
            return {"id": "1"}

        monkeypatch.setattr(
            hubspot_agent.agents.objects, "invoke_tool", mock_tool
        )

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        _store_pending_preview("123", "audit-test", {
            "agent_name": "objects",
            "request_text": "create a contact",
            "intent": {"intent_type": "create", "target_object": "contacts"},
            "preview": {},
            "batch_mode": "single",
            "proposed_payload": {"properties": {"firstname": "Alice"}},
            "informing_sources": [
                {
                    "source": "official",
                    "trust_tier": "official",
                    "title": "Contacts API",
                    "url": "https://developers.hubspot.com/docs/api/crm/contacts",
                    "last_updated": "2026-05-01",
                }
            ],
        })

        result = hubspot_command("approve audit-test", working_dir=str(tmp_path))
        assert "Approved and executed" in result

        audit_path = tmp_path / "audit.log"
        assert audit_path.exists()
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = __import__("json").loads(lines[0])
        assert entry["action"] == "approve:audit-test"
        assert entry["agent"] == "objects"
        assert len(entry["informing_sources"]) == 1
        assert entry["informing_sources"][0]["trust_tier"] == "official"

    def test_full_hitl_end_to_end(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.audit._audit_file_path", lambda pid: tmp_path / "audit.log")

        preview_result = AgentResult(
            agent_name="objects",
            status="preview",
            data={
                "action_id": "e2e-test",
                "risk_level": RiskLevel.MEDIUM,
                "impact_count": 1,
                "preview": "Will create contact Alice",
            },
            informing_sources=[],
        )

        async def mock_dispatch_parallel(*a, **k):
            # Store the preview via the real orchestrator function
            _store_pending_preview(
                "123",
                "e2e-test",
                {
                    "agent_name": "objects",
                    "request_text": "create a contact",
                    "intent": {"intent_type": "create", "target_object": "contacts"},
                    "preview": preview_result.data,
                    "batch_mode": "single",
                    "proposed_payload": {"properties": {"firstname": "Alice"}},
                    "trace_id": "t1",
                    "informing_sources": [],
                },
            )
            return [preview_result]

        monkeypatch.setattr(cli, "dispatch_agents_parallel", mock_dispatch_parallel)

        async def mock_dispatch_agent(*a, **k):
            return AgentResult(
                agent_name="objects",
                status="success",
                data={"message": "Contact created."},
            )

        monkeypatch.setattr(cli, "dispatch_agent", mock_dispatch_agent)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        # Step 1: request generates preview
        result1 = hubspot_command("create a contact named Alice", working_dir=str(tmp_path))
        assert "Preview" in result1
        assert "e2e-test" in result1
        assert _load_pending_preview("123", "e2e-test") is not None

        # Step 2: approve and execute
        result2 = hubspot_command("y", working_dir=str(tmp_path))
        assert "Approved and executed" in result2
        assert _load_pending_preview("123", "e2e-test") is None

        # Step 3: audit written
        audit_path = tmp_path / "audit.log"
        assert audit_path.exists()
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = __import__("json").loads(lines[0])
        assert entry["action"] == "approve:e2e-test"
        assert entry["agent"] == "objects"
