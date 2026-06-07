import pytest

from hubspot_agent.agents.appointments import get_appointments_agent_prompt
from hubspot_agent.agents.commerce import get_commerce_agent_prompt
from hubspot_agent.agents.courses import get_courses_agent_prompt
from hubspot_agent.agents.data import get_data_agent_prompt
from hubspot_agent.agents.forms import get_forms_agent_prompt
from hubspot_agent.agents.listings import get_listings_agent_prompt
from hubspot_agent.agents.services import get_services_agent_prompt
from hubspot_agent.dispatch import (
    get_execute_dispatch,
    get_preview_builder,
    get_reconcile_dispatch,
)
from hubspot_agent.models import PreviewResult, RiskLevel, TaskIntent
from hubspot_agent.orchestrator import _build_preview_for_intent, dispatch_agent

# Trigger registration of all new agents
import hubspot_agent.agents.appointments  # noqa: F401
import hubspot_agent.agents.commerce  # noqa: F401
import hubspot_agent.agents.courses  # noqa: F401
import hubspot_agent.agents.data  # noqa: F401
import hubspot_agent.agents.forms  # noqa: F401
import hubspot_agent.agents.listings  # noqa: F401
import hubspot_agent.agents.services  # noqa: F401


class FakeClient:
    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Agent Prompt Tests
# ---------------------------------------------------------------------------

class TestFormsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_forms_agent_prompt()
        assert prompt.agent_name == "Forms Agent"
        assert "hubspot_list_forms" in prompt.tool_names
        assert "hubspot_get_form" in prompt.tool_names
        assert "hubspot_create_form" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("forms") is not None
        assert get_execute_dispatch("forms") is not None
        assert get_reconcile_dispatch("forms") is not None


class TestDataAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_data_agent_prompt()
        assert prompt.agent_name == "Data Agent"
        assert "hubspot_import_data" in prompt.tool_names
        assert "hubspot_export_data" in prompt.tool_names
        assert "hubspot_get_import_status" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("data") is not None
        assert get_execute_dispatch("data") is not None
        assert get_reconcile_dispatch("data") is not None


class TestCommerceAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_commerce_agent_prompt()
        assert prompt.agent_name == "Commerce Agent"
        assert "hubspot_list_payments" in prompt.tool_names
        assert "hubspot_get_payment" in prompt.tool_names
        assert "hubspot_create_refund" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("commerce") is not None
        assert get_execute_dispatch("commerce") is not None
        assert get_reconcile_dispatch("commerce") is not None


class TestAppointmentsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_appointments_agent_prompt()
        assert prompt.agent_name == "Appointments Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("appointments") is not None
        assert get_execute_dispatch("appointments") is not None
        assert get_reconcile_dispatch("appointments") is not None


class TestCoursesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_courses_agent_prompt()
        assert prompt.agent_name == "Courses Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("courses") is not None
        assert get_execute_dispatch("courses") is not None
        assert get_reconcile_dispatch("courses") is not None


class TestListingsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_listings_agent_prompt()
        assert prompt.agent_name == "Listings Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("listings") is not None
        assert get_execute_dispatch("listings") is not None
        assert get_reconcile_dispatch("listings") is not None


class TestServicesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_services_agent_prompt()
        assert prompt.agent_name == "Services Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("services") is not None
        assert get_execute_dispatch("services") is not None
        assert get_reconcile_dispatch("services") is not None


# ---------------------------------------------------------------------------
# Preview Tests
# ---------------------------------------------------------------------------

class TestFormsPreview:
    @pytest.mark.asyncio
    async def test_forms_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "name": "Contact Form"}]}

        monkeypatch.setattr("hubspot_agent.agents.forms.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            description="list forms",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("forms", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "forms" in preview.preview

    @pytest.mark.asyncio
    async def test_forms_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            description="create a contact form",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("forms", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "create" in preview.preview.get("message", "").lower()


class TestDataPreview:
    @pytest.mark.asyncio
    async def test_data_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            description="import contacts",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("data", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "import" in preview.preview.get("message", "").lower()


class TestCommercePreview:
    @pytest.mark.asyncio
    async def test_commerce_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "amount": 99.99}]}

        monkeypatch.setattr("hubspot_agent.agents.commerce.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            description="list payments",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("commerce", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "payments" in preview.preview


class TestPipelineObjectsPreview:
    @pytest.mark.asyncio
    async def test_appointments_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Showing"}}]}

        monkeypatch.setattr("hubspot_agent.agents.appointments.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="appointments",
            description="find appointments",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("appointments", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_courses_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="courses",
            description="create a course",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("courses", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "courses" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_listings_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"address": "123 Main"}}]}

        monkeypatch.setattr("hubspot_agent.agents.listings.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="listings",
            description="find listings",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("listings", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_services_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="services",
            description="create a service",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("services", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "services" in preview.preview.get("message", "").lower()


# ---------------------------------------------------------------------------
# Execute Tests
# ---------------------------------------------------------------------------

class TestFormsExecute:
    @pytest.mark.asyncio
    async def test_forms_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"id": "new-form-1"}

        monkeypatch.setattr("hubspot_agent.agents.forms.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "forms",
            "create a form",
            portal,
            mode="execute",
            proposed_payload={"name": "Test Form", "form_type": "HUBSPOT", "fields": []},
        )
        assert result.status == "success"


class TestPipelineObjectsExecute:
    @pytest.mark.asyncio
    async def test_appointments_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"id": "new-appt-1"}

        monkeypatch.setattr("hubspot_agent.agents.appointments.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "appointments",
            "create an appointment",
            portal,
            mode="execute",
            proposed_payload={"properties": {"name": "Showing"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_courses_search_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Intro"}}]}

        monkeypatch.setattr("hubspot_agent.agents.courses.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "courses", "find courses", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_listings_update_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"address": "123 Main"}}]}
            return {"id": "1"}

        monkeypatch.setattr("hubspot_agent.agents.listings.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "listings",
            "update listing price",
            portal,
            mode="execute",
            proposed_payload={"properties": {"price": 500000}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_services_delete_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Cleaning"}}]}
            return {}

        monkeypatch.setattr("hubspot_agent.agents.services.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "services", "delete cleaning service", portal, mode="execute"
        )
        assert result.status == "success"
