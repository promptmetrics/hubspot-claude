import pytest

from hubspot_agent.agents.account_info import get_account_info_agent_prompt
from hubspot_agent.agents.audit_logs import get_audit_logs_agent_prompt
from hubspot_agent.agents.communications import get_communications_agent_prompt
from hubspot_agent.agents.email_events import get_email_events_agent_prompt
from hubspot_agent.agents.forecasts import get_forecasts_agent_prompt
from hubspot_agent.agents.leads import get_leads_agent_prompt
from hubspot_agent.agents.object_library import get_object_library_agent_prompt
from hubspot_agent.agents.projects import get_projects_agent_prompt
from hubspot_agent.agents.scheduler import get_scheduler_agent_prompt
from hubspot_agent.agents.security_history import get_security_history_agent_prompt
from hubspot_agent.agents.sequences import get_sequences_agent_prompt
from hubspot_agent.agents.timeline_events import get_timeline_events_agent_prompt
from hubspot_agent.dispatch import (
    get_execute_dispatch,
    get_preview_builder,
    get_reconcile_dispatch,
)
from hubspot_agent.models import PreviewResult, RiskLevel, TaskIntent
from hubspot_agent.orchestrator import _build_preview_for_intent, dispatch_agent

# Trigger registration of all new agents
import hubspot_agent.agents.account_info  # noqa: F401
import hubspot_agent.agents.audit_logs  # noqa: F401
import hubspot_agent.agents.communications  # noqa: F401
import hubspot_agent.agents.email_events  # noqa: F401
import hubspot_agent.agents.forecasts  # noqa: F401
import hubspot_agent.agents.leads  # noqa: F401
import hubspot_agent.agents.object_library  # noqa: F401
import hubspot_agent.agents.projects  # noqa: F401
import hubspot_agent.agents.scheduler  # noqa: F401
import hubspot_agent.agents.security_history  # noqa: F401
import hubspot_agent.agents.sequences  # noqa: F401
import hubspot_agent.agents.timeline_events  # noqa: F401


class FakeClient:
    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Agent Prompt Tests
# ---------------------------------------------------------------------------

class TestCommunicationsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_communications_agent_prompt()
        assert prompt.agent_name == "Communications Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("communications") is not None
        assert get_execute_dispatch("communications") is not None
        assert get_reconcile_dispatch("communications") is not None


class TestLeadsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_leads_agent_prompt()
        assert prompt.agent_name == "Leads Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("leads") is not None
        assert get_execute_dispatch("leads") is not None
        assert get_reconcile_dispatch("leads") is not None


class TestProjectsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_projects_agent_prompt()
        assert prompt.agent_name == "Projects Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("projects") is not None
        assert get_execute_dispatch("projects") is not None
        assert get_reconcile_dispatch("projects") is not None


class TestTimelineEventsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_timeline_events_agent_prompt()
        assert prompt.agent_name == "Timeline Events Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("timeline_events") is not None
        assert get_execute_dispatch("timeline_events") is not None
        assert get_reconcile_dispatch("timeline_events") is not None


class TestObjectLibraryAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_object_library_agent_prompt()
        assert prompt.agent_name == "Object Library Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("object_library") is not None


class TestAccountInfoAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_account_info_agent_prompt()
        assert prompt.agent_name == "Account Info Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("account_info") is not None


class TestAuditLogsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_audit_logs_agent_prompt()
        assert prompt.agent_name == "Audit Logs Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("audit_logs") is not None


class TestSecurityHistoryAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_security_history_agent_prompt()
        assert prompt.agent_name == "Security History Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("security_history") is not None


class TestEmailEventsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_email_events_agent_prompt()
        assert prompt.agent_name == "Email Events Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("email_events") is not None


class TestForecastsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_forecasts_agent_prompt()
        assert prompt.agent_name == "Forecasts Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("forecasts") is not None


class TestSequencesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_sequences_agent_prompt()
        assert prompt.agent_name == "Sequences Agent"

    def test_dispatch_registered(self):
        assert get_preview_builder("sequences") is not None
        assert get_execute_dispatch("sequences") is not None
        assert get_reconcile_dispatch("sequences") is not None


class TestSchedulerAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_scheduler_agent_prompt()
        assert prompt.agent_name == "Scheduler Agent"

    def test_preview_dispatch_registered(self):
        assert get_preview_builder("scheduler") is not None


# ---------------------------------------------------------------------------
# Preview Tests
# ---------------------------------------------------------------------------

class TestStandardObjectsPreview:
    @pytest.mark.asyncio
    async def test_communications_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Comm"}}]}

        monkeypatch.setattr("hubspot_agent.agents.communications.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="communications",
            description="find communications",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("communications", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_leads_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="leads",
            description="create a lead",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("leads", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "leads" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_projects_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Project"}}]}

        monkeypatch.setattr("hubspot_agent.agents.projects.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="projects",
            description="find projects",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("projects", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_timeline_events_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="timeline_events",
            description="create a timeline event",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("timeline_events", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "timeline_events" in preview.preview.get("message", "").lower()


class TestReadOnlyAgentsPreview:
    @pytest.mark.asyncio
    async def test_object_library_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="list available objects",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("object_library", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0

    @pytest.mark.asyncio
    async def test_account_info_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="get portal details",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("account_info", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0

    @pytest.mark.asyncio
    async def test_audit_logs_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="get audit logs",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("audit_logs", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0

    @pytest.mark.asyncio
    async def test_security_history_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="get security history",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("security_history", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0

    @pytest.mark.asyncio
    async def test_email_events_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="get email events",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("email_events", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0

    @pytest.mark.asyncio
    async def test_forecasts_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="get forecasts",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("forecasts", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0

    @pytest.mark.asyncio
    async def test_scheduler_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="get meeting links",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("scheduler", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 0


class TestSequencesPreview:
    @pytest.mark.asyncio
    async def test_sequences_search_preview(self):
        intent = TaskIntent(
            intent_type="search",
            description="find sequences",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("sequences", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 1

    @pytest.mark.asyncio
    async def test_sequences_create_preview(self):
        intent = TaskIntent(
            intent_type="create",
            description="enroll contact in sequence",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("sequences", intent, FakeClient(), "123")
        assert isinstance(preview, PreviewResult)
        assert preview.impact_count == 1
        assert "enroll" in preview.preview.get("message", "").lower()


# ---------------------------------------------------------------------------
# Execute Tests
# ---------------------------------------------------------------------------

class TestStandardObjectsExecute:
    @pytest.mark.asyncio
    async def test_communications_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"id": "new-comm-1"}

        monkeypatch.setattr("hubspot_agent.agents.communications.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "communications",
            "create a communication",
            portal,
            mode="execute",
            proposed_payload={"properties": {"name": "Comm"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_leads_search_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Lead"}}]}

        monkeypatch.setattr("hubspot_agent.agents.leads.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "leads", "find leads", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_projects_update_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Project"}}]}
            return {"id": "1"}

        monkeypatch.setattr("hubspot_agent.agents.projects.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "projects",
            "update project status",
            portal,
            mode="execute",
            proposed_payload={"properties": {"status": "in_progress"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_timeline_events_delete_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Event"}}]}
            return {}

        monkeypatch.setattr("hubspot_agent.agents.timeline_events.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "timeline_events", "delete event", portal, mode="execute"
        )
        assert result.status == "success"


class TestSequencesExecute:
    @pytest.mark.asyncio
    async def test_sequences_search_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "sequences", "find sequences", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_sequences_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "sequences",
            "enroll contact in sequence",
            portal,
            mode="execute",
            proposed_payload={"sequence_id": "seq-1", "contact_ids": ["1"]},
        )
        assert result.status == "success"
