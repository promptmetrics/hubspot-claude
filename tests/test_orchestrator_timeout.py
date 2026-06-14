import pytest

from hubspot_agent.config import PortalConfig
from hubspot_agent.orchestrator import reconcile_after_timeout

import hubspot_agent.agents.objects  # noqa: F401 — registers preview/execute/reconcile handlers


class TestReconcileAfterTimeout:
    @pytest.mark.asyncio
    async def test_create_verified(self, monkeypatch):
        async def mock_tool(name, portal_id, **kwargs):
            return {
                "results": [
                    {"id": "1", "properties": {"firstname": "Alice", "email": "alice@example.com"}}
                ]
            }

        monkeypatch.setattr("hubspot_agent.agents.objects.invoke_tool", mock_tool)

        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="objects",
            request_text="create a contact named Alice",
            expected_payload={"properties": {"firstname": "Alice"}},
            portal_config=portal,
        )
        assert result["status"] == "verified"
        assert "Found 1 potential matches" in result["message"]

    @pytest.mark.asyncio
    async def test_create_discrepancy_no_records(self, monkeypatch):
        async def mock_tool(name, portal_id, **kwargs):
            return {"results": []}

        monkeypatch.setattr("hubspot_agent.agents.objects.invoke_tool", mock_tool)

        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="objects",
            request_text="create a contact named Alice",
            expected_payload={"properties": {"firstname": "Alice"}},
            portal_config=portal,
        )
        assert result["status"] == "discrepancy"
        assert "No contacts record found" in result["message"]

    @pytest.mark.asyncio
    async def test_update_verified(self, monkeypatch):
        async def mock_tool(name, portal_id, **kwargs):
            return {
                "results": [
                    {"id": "1", "properties": {"firstname": "Alice", "email": "alice@example.com"}}
                ]
            }

        monkeypatch.setattr("hubspot_agent.agents.objects.invoke_tool", mock_tool)

        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="objects",
            request_text="update contact Alice",
            expected_payload={"properties": {"firstname": "Alice"}},
            portal_config=portal,
        )
        assert result["status"] == "verified"
        assert "Update verified" in result["message"]

    @pytest.mark.asyncio
    async def test_update_discrepancy_mismatch(self, monkeypatch):
        async def mock_tool(name, portal_id, **kwargs):
            return {
                "results": [
                    {"id": "1", "properties": {"firstname": "Bob", "email": "alice@example.com"}}
                ]
            }

        monkeypatch.setattr("hubspot_agent.agents.objects.invoke_tool", mock_tool)

        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="objects",
            request_text="update contact Alice",
            expected_payload={"properties": {"firstname": "Alice"}},
            portal_config=portal,
        )
        assert result["status"] == "discrepancy"
        assert "Property mismatches" in result["message"]
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["expected"] == "Alice"
        assert result["mismatches"][0]["actual"] == "Bob"

    @pytest.mark.asyncio
    async def test_delete_verified(self, monkeypatch):
        async def mock_tool(name, portal_id, **kwargs):
            return {"results": []}

        monkeypatch.setattr("hubspot_agent.agents.objects.invoke_tool", mock_tool)

        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="objects",
            request_text="delete contact Alice",
            expected_payload={"object_id": "1"},
            portal_config=portal,
        )
        assert result["status"] == "verified"
        assert "Delete verified" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_discrepancy_records_remain(self, monkeypatch):
        async def mock_tool(name, portal_id, **kwargs):
            return {
                "results": [
                    {"id": "1", "properties": {"firstname": "Alice"}}
                ]
            }

        monkeypatch.setattr("hubspot_agent.agents.objects.invoke_tool", mock_tool)

        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="objects",
            request_text="delete contact Alice",
            expected_payload={"object_id": "1"},
            portal_config=portal,
        )
        assert result["status"] == "discrepancy"
        assert "still exist" in result["message"]

    @pytest.mark.asyncio
    async def test_unsupported_agent(self, monkeypatch):
        portal = PortalConfig(portal_id="123", token="t")
        result = await reconcile_after_timeout(
            portal_id="123",
            agent_name="analytics",
            request_text="get report",
            expected_payload={},
            portal_config=portal,
        )
        assert result["status"] == "unknown"
        assert "not implemented" in result["message"]
