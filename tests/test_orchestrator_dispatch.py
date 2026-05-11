import pytest

from hubspot_agent.models import BatchApprovalMode, RiskLevel, TaskIntent
from hubspot_agent.orchestrator import (
    _build_preview_for_intent,
    _extract_search_term,
    _parse_agent_intent,
    dispatch_agent,
    dispatch_agents_parallel,
)


class TestParseAgentIntent:
    def test_search_intent(self):
        intent = _parse_agent_intent("objects", "find contacts in northeast")
        assert intent.intent_type == "search"
        assert intent.target_object == "contacts"
        assert intent.risk_level == RiskLevel.LOW

    def test_create_intent(self):
        intent = _parse_agent_intent("objects", "create a new company")
        assert intent.intent_type == "create"
        assert intent.target_object == "companies"
        assert intent.risk_level == RiskLevel.MEDIUM

    def test_update_intent(self):
        intent = _parse_agent_intent("objects", "update deal stage")
        assert intent.intent_type == "update"
        assert intent.target_object == "deals"
        assert intent.risk_level == RiskLevel.MEDIUM

    def test_delete_intent(self):
        intent = _parse_agent_intent("objects", "delete old tickets")
        assert intent.intent_type == "delete"
        assert intent.target_object == "tickets"
        assert intent.risk_level == RiskLevel.DESTRUCTIVE

    def test_unknown_intent(self):
        intent = _parse_agent_intent("objects", "hello world")
        assert intent.intent_type == "unknown"

    def test_non_objects_agent(self):
        intent = _parse_agent_intent("workflows", "create a workflow")
        assert intent.intent_type == "create"
        assert intent.target_object is None


class TestExtractSearchTerm:
    def test_basic_extraction(self):
        intent = TaskIntent(
            intent_type="search",
            target_object="contacts",
            description="find contacts in northeast",
            risk_level=RiskLevel.LOW,
        )
        term = _extract_search_term(intent)
        assert "northeast" in term

    def test_empty_after_stop_words(self):
        intent = TaskIntent(
            intent_type="search",
            target_object="contacts",
            description="find the contact",
            risk_level=RiskLevel.LOW,
        )
        term = _extract_search_term(intent)
        assert term == "*"


class TestBuildPreviewForIntent:
    @pytest.mark.asyncio
    async def test_objects_create_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = TaskIntent(
            intent_type="create",
            target_object="contacts",
            description="create a contact",
            risk_level=RiskLevel.MEDIUM,
            estimated_impact=1,
        )
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.MEDIUM
        assert "create" in preview.preview.get("message", "")

    @pytest.mark.asyncio
    async def test_objects_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {
                "results": [
                    {"id": "1", "properties": {"firstname": "Alice"}},
                    {"id": "2", "properties": {"firstname": "Bob"}},
                ]
            }

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = TaskIntent(
            intent_type="search",
            target_object="contacts",
            description="find contacts",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 2
        assert preview.risk_level == RiskLevel.LOW
        assert "1" in preview.original_values

    @pytest.mark.asyncio
    async def test_objects_search_error(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"error": "scope_missing"}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = TaskIntent(
            intent_type="search",
            target_object="contacts",
            description="find contacts",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 0
        assert "error" in preview.preview

    @pytest.mark.asyncio
    async def test_other_agent_preview(self, monkeypatch):
        class FakeClient:
            async def close(self):
                pass

        intent = TaskIntent(
            intent_type="create",
            description="create a workflow",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("workflows", intent, FakeClient(), "123")
        assert preview.impact_count == 1


class TestDispatchAgent:
    @pytest.mark.asyncio
    async def test_preview_mode_returns_preview(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview",
            lambda pid, aid, data: None,
        )

        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        from hubspot_agent.config import PortalConfig

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "objects",
            "find contacts",
            portal,
            mode="preview",
        )
        assert result.status == "preview"
        assert "action_id" in result.data
        assert result.data.get("risk_level") == "low"

    @pytest.mark.asyncio
    async def test_execute_mode_search(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1"}]}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        from hubspot_agent.config import PortalConfig

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "objects",
            "find contacts",
            portal,
            mode="execute",
        )
        assert result.status == "success"
        assert "result" in result.data

    @pytest.mark.asyncio
    async def test_execute_mode_create(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"id": "1", "properties": {}}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        from hubspot_agent.config import PortalConfig

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "objects",
            "create a contact",
            portal,
            mode="execute",
            proposed_payload={"properties": {"firstname": "Alice"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_execute_mode_update_no_records(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        from hubspot_agent.config import PortalConfig

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "objects",
            "update contact",
            portal,
            mode="execute",
        )
        assert result.status == "error"
        assert "No matching records" in result.error_message

    @pytest.mark.asyncio
    async def test_unknown_agent(self):
        from hubspot_agent.config import PortalConfig

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "nonexistent",
            "do something",
            portal,
        )
        assert result.status == "error"
        assert "Unknown agent" in result.error_message


class TestDispatchAgentsParallel:
    @pytest.mark.asyncio
    async def test_parallel_dispatch(self, monkeypatch):
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview",
            lambda pid, aid, data: None,
        )

        async def mock_tool(*a, **k):
            return {"results": []}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        from hubspot_agent.config import PortalConfig

        portal = PortalConfig(portal_id="123", token="test-token")
        results = await dispatch_agents_parallel(
            ["objects", "properties"],
            "find contacts",
            portal,
            mode="preview",
        )
        assert len(results) == 2
        assert all(r.status == "preview" for r in results)
