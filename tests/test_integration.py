import pytest

from hubspot_agent.cli import hubspot_command


@pytest.fixture
def mock_portal(tmp_path, monkeypatch):
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")
    return str(tmp_path)


def test_integration_read_query(mock_portal):
    result = hubspot_command("how many contacts", working_dir=mock_portal)
    assert "Portal: 123" in result
    assert "objects" in result


def test_integration_write_routing(mock_portal):
    result = hubspot_command("create a contact with email test@example.com", working_dir=mock_portal)
    assert "Portal: 123" in result
    assert "objects" in result


def test_integration_portal_switch(mock_portal):
    result = hubspot_command("portal switch 456")
    assert "Switched to portal 456" in result


def test_integration_refresh(mock_portal):
    result = hubspot_command("refresh", working_dir=mock_portal)
    assert "Cache refreshed" in result
    assert "123" in result


class TestIntegrationHitlHappyPath:
    def test_preview_approve_execute_audit(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from hubspot_agent.config import save_portal_config, PortalConfig
        from hubspot_agent.models import AgentResult, RiskLevel
        from pathlib import Path

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.audit._audit_file_path", lambda pid: tmp_path / "audit.log")

        preview_result = AgentResult(
            agent_name="objects",
            status="preview",
            data={
                "action_id": "int-test",
                "risk_level": RiskLevel.MEDIUM,
                "impact_count": 1,
                "preview": "Will create contact Bob",
            },
            informing_sources=[],
        )

        async def mock_dispatch_parallel(*a, **k):
            orchestrator._store_pending_preview(
                "123",
                "int-test",
                {
                    "agent_name": "objects",
                    "request_text": "create a contact named Bob",
                    "intent": {"intent_type": "create", "target_object": "contacts"},
                    "preview": preview_result.data,
                    "batch_mode": "single",
                    "proposed_payload": {"properties": {"firstname": "Bob"}},
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

        # Step 1: preview
        result1 = hubspot_command("create a contact named Bob", working_dir=str(tmp_path))
        assert "Preview" in result1
        assert "int-test" in result1
        assert orchestrator._load_pending_preview("123", "int-test") is not None

        # Step 2: approve
        result2 = hubspot_command("approve int-test", working_dir=str(tmp_path))
        assert "Approved and executed" in result2
        assert orchestrator._load_pending_preview("123", "int-test") is None

        # Step 3: audit
        audit_path = tmp_path / "audit.log"
        assert audit_path.exists()
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = __import__("json").loads(lines[0])
        assert entry["action"] == "approve:int-test"
        assert entry["agent"] == "objects"

    def test_reject_clears_preview(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from hubspot_agent.config import save_portal_config, PortalConfig
        from pathlib import Path

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        orchestrator._store_pending_preview("123", "rej-test", {
            "agent_name": "objects",
            "request_text": "delete a contact",
            "intent": {},
            "preview": {},
            "batch_mode": "single",
        })

        result = hubspot_command("n", working_dir=str(tmp_path))
        assert "Rejected" in result
        assert orchestrator._load_pending_preview("123", "rej-test") is None

    def test_batch_mode_preview(self, tmp_path, monkeypatch):
        from hubspot_agent import cli, orchestrator
        from hubspot_agent.config import save_portal_config, PortalConfig
        from hubspot_agent.models import AgentResult, RiskLevel
        from pathlib import Path

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)

        preview_result = AgentResult(
            agent_name="objects",
            status="preview",
            data={
                "action_id": "batch-test",
                "risk_level": RiskLevel.MEDIUM,
                "impact_count": 3,
                "preview": "Will create 3 contacts",
            },
            informing_sources=[],
        )

        async def mock_dispatch_parallel(*a, **k):
            orchestrator._store_pending_preview(
                "123",
                "batch-test",
                {
                    "agent_name": "objects",
                    "request_text": "create three contacts",
                    "intent": {"intent_type": "create", "target_object": "contacts"},
                    "preview": preview_result.data,
                    "batch_mode": "batch",
                    "proposed_payload": {"properties": {"firstname": "Batch"}},
                    "trace_id": "t2",
                    "informing_sources": [],
                },
            )
            return [preview_result]

        monkeypatch.setattr(cli, "dispatch_agents_parallel", mock_dispatch_parallel)

        portal_file = tmp_path / ".hubspot-portal"
        portal_file.write_text("123\n")
        save_portal_config(PortalConfig(portal_id="123", token="test-token"))

        result = hubspot_command("create three contacts --batch", working_dir=str(tmp_path))
        assert "Preview" in result
        assert "batch-test" in result
        preview = orchestrator._load_pending_preview("123", "batch-test")
        assert preview is not None
        assert preview["batch_mode"] == "batch"
