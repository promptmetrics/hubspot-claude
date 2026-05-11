import pytest

from hubspot_agent.models import PreviewResult, RiskLevel, TaskIntent
from hubspot_agent.orchestrator import (
    _build_preview_for_intent,
    _extract_search_term,
    _parse_agent_intent,
)


class TestPreviewEngineObjects:
    @pytest.mark.asyncio
    async def test_search_preview_returns_records(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {
                "results": [
                    {"id": "1", "properties": {"firstname": "Alice", "email": "alice@example.com"}},
                    {"id": "2", "properties": {"firstname": "Bob", "email": "bob@example.com"}},
                ]
            }

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("objects", "find contacts in northeast")
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 2
        assert preview.risk_level == RiskLevel.LOW
        assert "1" in preview.original_values
        assert preview.original_values["1"]["firstname"] == "Alice"

    @pytest.mark.asyncio
    async def test_create_preview_returns_message(self, monkeypatch):
        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("objects", "create a new contact")
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.MEDIUM
        assert "create" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_update_preview_searches_first(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "10", "properties": {"firstname": "Alice"}}]}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("objects", "update contact alice")
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.MEDIUM
        assert "10" in preview.original_values

    @pytest.mark.asyncio
    async def test_delete_preview_searches_first(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "99", "properties": {"firstname": "Old"}}]}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("objects", "delete old contacts")
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.DESTRUCTIVE
        assert "99" in preview.original_values

    @pytest.mark.asyncio
    async def test_search_preview_handles_tool_error(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"error": "rate_limited"}

        monkeypatch.setattr(
            "hubspot_agent.orchestrator.invoke_tool",
            mock_tool,
        )

        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("objects", "find contacts")
        preview = await _build_preview_for_intent("objects", intent, FakeClient(), "123")
        assert preview.impact_count == 0
        assert "error" in preview.preview


class TestPreviewEngineOtherAgents:
    @pytest.mark.asyncio
    async def test_workflows_preview(self, monkeypatch):
        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("workflows", "create a workflow")
        preview = await _build_preview_for_intent("workflows", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_properties_preview(self, monkeypatch):
        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("properties", "add a property field")
        preview = await _build_preview_for_intent("properties", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_analytics_preview(self, monkeypatch):
        class FakeClient:
            async def close(self):
                pass

        intent = _parse_agent_intent("analytics", "show me the dashboard")
        preview = await _build_preview_for_intent("analytics", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert preview.risk_level == RiskLevel.LOW
