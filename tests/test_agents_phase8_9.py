import pytest

from hubspot_agent.agents.carts import get_carts_agent_prompt
from hubspot_agent.agents.deal_splits import get_deal_splits_agent_prompt
from hubspot_agent.agents.discounts import get_discounts_agent_prompt
from hubspot_agent.agents.fees import get_fees_agent_prompt
from hubspot_agent.agents.goals import get_goals_agent_prompt
from hubspot_agent.agents.invoices import get_invoices_agent_prompt
from hubspot_agent.agents.orders import get_orders_agent_prompt
from hubspot_agent.agents.quotes import get_quotes_agent_prompt
from hubspot_agent.agents.subscriptions import get_subscriptions_agent_prompt
from hubspot_agent.agents.taxes import get_taxes_agent_prompt
from hubspot_agent.dispatch import (
    get_execute_dispatch,
    get_preview_builder,
    get_reconcile_dispatch,
)
from hubspot_agent.models import PreviewResult, RiskLevel, TaskIntent
from hubspot_agent.orchestrator import _build_preview_for_intent, dispatch_agent

# Trigger registration of all new agents
import hubspot_agent.agents.carts  # noqa: F401
import hubspot_agent.agents.deal_splits  # noqa: F401
import hubspot_agent.agents.discounts  # noqa: F401
import hubspot_agent.agents.fees  # noqa: F401
import hubspot_agent.agents.goals  # noqa: F401
import hubspot_agent.agents.invoices  # noqa: F401
import hubspot_agent.agents.orders  # noqa: F401
import hubspot_agent.agents.quotes  # noqa: F401
import hubspot_agent.agents.subscriptions  # noqa: F401
import hubspot_agent.agents.taxes  # noqa: F401


class FakeClient:
    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Agent Prompt Tests
# ---------------------------------------------------------------------------

class TestCartsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_carts_agent_prompt()
        assert prompt.agent_name == "Carts Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("carts") is not None
        assert get_execute_dispatch("carts") is not None
        assert get_reconcile_dispatch("carts") is not None


class TestOrdersAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_orders_agent_prompt()
        assert prompt.agent_name == "Orders Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("orders") is not None
        assert get_execute_dispatch("orders") is not None
        assert get_reconcile_dispatch("orders") is not None


class TestQuotesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_quotes_agent_prompt()
        assert prompt.agent_name == "Quotes Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("quotes") is not None
        assert get_execute_dispatch("quotes") is not None
        assert get_reconcile_dispatch("quotes") is not None


class TestSubscriptionsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_subscriptions_agent_prompt()
        assert prompt.agent_name == "Subscriptions Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("subscriptions") is not None
        assert get_execute_dispatch("subscriptions") is not None
        assert get_reconcile_dispatch("subscriptions") is not None


class TestInvoicesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_invoices_agent_prompt()
        assert prompt.agent_name == "Invoices Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("invoices") is not None
        assert get_execute_dispatch("invoices") is not None
        assert get_reconcile_dispatch("invoices") is not None


class TestDealSplitsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_deal_splits_agent_prompt()
        assert prompt.agent_name == "Deal Splits Agent"
        assert "hubspot_batch_read_deal_splits" in prompt.tool_names
        assert "hubspot_batch_upsert_deal_splits" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("deal_splits") is not None
        assert get_execute_dispatch("deal_splits") is not None
        assert get_reconcile_dispatch("deal_splits") is not None


class TestDiscountsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_discounts_agent_prompt()
        assert prompt.agent_name == "Discounts Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("discounts") is not None
        assert get_execute_dispatch("discounts") is not None
        assert get_reconcile_dispatch("discounts") is not None


class TestFeesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_fees_agent_prompt()
        assert prompt.agent_name == "Fees Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("fees") is not None
        assert get_execute_dispatch("fees") is not None
        assert get_reconcile_dispatch("fees") is not None


class TestTaxesAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_taxes_agent_prompt()
        assert prompt.agent_name == "Taxes Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("taxes") is not None
        assert get_execute_dispatch("taxes") is not None
        assert get_reconcile_dispatch("taxes") is not None


class TestGoalsAgent:
    def test_prompt_has_correct_tools(self):
        prompt = get_goals_agent_prompt()
        assert prompt.agent_name == "Goals Agent"
        assert "hubspot_search_objects" in prompt.tool_names
        assert "hubspot_create_object" in prompt.tool_names

    def test_dispatch_registered(self):
        assert get_preview_builder("goals") is not None
        assert get_execute_dispatch("goals") is not None
        assert get_reconcile_dispatch("goals") is not None


# ---------------------------------------------------------------------------
# Preview Tests
# ---------------------------------------------------------------------------

class TestPipelineObjectsPreview:
    @pytest.mark.asyncio
    async def test_carts_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Cart"}}]}

        monkeypatch.setattr("hubspot_agent.agents.carts.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="carts",
            description="find carts",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("carts", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_orders_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="orders",
            description="create an order",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("orders", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "orders" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_quotes_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Quote"}}]}

        monkeypatch.setattr("hubspot_agent.agents.quotes.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="quotes",
            description="find quotes",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("quotes", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_subscriptions_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="subscriptions",
            description="create a subscription",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("subscriptions", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "subscriptions" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_invoices_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Invoice"}}]}

        monkeypatch.setattr("hubspot_agent.agents.invoices.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="invoices",
            description="find invoices",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("invoices", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_discounts_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="discounts",
            description="create a discount",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("discounts", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "discounts" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_fees_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Fee"}}]}

        monkeypatch.setattr("hubspot_agent.agents.fees.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="fees",
            description="find fees",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("fees", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview

    @pytest.mark.asyncio
    async def test_taxes_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            target_object="taxes",
            description="create a tax",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("taxes", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "taxes" in preview.preview.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_goals_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Goal"}}]}

        monkeypatch.setattr("hubspot_agent.agents.goals.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            target_object="goals",
            description="find goals",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("goals", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "records" in preview.preview


class TestDealSplitsPreview:
    @pytest.mark.asyncio
    async def test_deal_splits_search_preview(self, monkeypatch):
        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"deal_id": "1"}}]}

        monkeypatch.setattr("hubspot_agent.agents.deal_splits.invoke_tool", mock_tool)

        intent = TaskIntent(
            intent_type="search",
            description="find deal splits",
            risk_level=RiskLevel.LOW,
        )
        preview = await _build_preview_for_intent("deal_splits", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "deal_splits" in preview.preview

    @pytest.mark.asyncio
    async def test_deal_splits_create_preview(self, monkeypatch):
        intent = TaskIntent(
            intent_type="create",
            description="create a deal split",
            risk_level=RiskLevel.MEDIUM,
        )
        preview = await _build_preview_for_intent("deal_splits", intent, FakeClient(), "123")
        assert preview.impact_count == 1
        assert "deal splits" in preview.preview.get("message", "").lower()


# ---------------------------------------------------------------------------
# Execute Tests
# ---------------------------------------------------------------------------

class TestPipelineObjectsExecute:
    @pytest.mark.asyncio
    async def test_carts_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"id": "new-cart-1"}

        monkeypatch.setattr("hubspot_agent.agents.carts.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "carts",
            "create a cart",
            portal,
            mode="execute",
            proposed_payload={"properties": {"name": "Cart"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_orders_search_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Order"}}]}

        monkeypatch.setattr("hubspot_agent.agents.orders.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "orders", "find orders", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_quotes_update_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Quote"}}]}
            return {"id": "1"}

        monkeypatch.setattr("hubspot_agent.agents.quotes.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "quotes",
            "update quote status",
            portal,
            mode="execute",
            proposed_payload={"properties": {"status": "approved"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_subscriptions_delete_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Subscription"}}]}
            return {}

        monkeypatch.setattr("hubspot_agent.agents.subscriptions.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "subscriptions", "delete subscription", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_invoices_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"id": "new-invoice-1"}

        monkeypatch.setattr("hubspot_agent.agents.invoices.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "invoices",
            "create an invoice",
            portal,
            mode="execute",
            proposed_payload={"properties": {"name": "Invoice"}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_discounts_search_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"results": [{"id": "1", "properties": {"name": "Discount"}}]}

        monkeypatch.setattr("hubspot_agent.agents.discounts.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "discounts", "find discounts", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_fees_update_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Fee"}}]}
            return {"id": "1"}

        monkeypatch.setattr("hubspot_agent.agents.fees.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "fees",
            "update fee amount",
            portal,
            mode="execute",
            proposed_payload={"properties": {"amount": 100}},
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_taxes_delete_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            if "search" in str(k):
                return {"results": [{"id": "1", "properties": {"name": "Tax"}}]}
            return {}

        monkeypatch.setattr("hubspot_agent.agents.taxes.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "taxes", "delete tax", portal, mode="execute"
        )
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_goals_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"id": "new-goal-1"}

        monkeypatch.setattr("hubspot_agent.agents.goals.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "goals",
            "create a goal",
            portal,
            mode="execute",
            proposed_payload={"properties": {"name": "Goal"}},
        )
        assert result.status == "success"


class TestDealSplitsExecute:
    @pytest.mark.asyncio
    async def test_deal_splits_create_execute(self, monkeypatch):
        from hubspot_agent.config import PortalConfig

        async def mock_tool(*a, **k):
            return {"results": [{"id": "new-split-1"}]}

        monkeypatch.setattr("hubspot_agent.agents.deal_splits.invoke_tool", mock_tool)
        monkeypatch.setattr(
            "hubspot_agent.orchestrator._store_pending_preview", lambda pid, aid, data: None
        )

        portal = PortalConfig(portal_id="123", token="test-token")
        result = await dispatch_agent(
            "deal_splits",
            "create a deal split",
            portal,
            mode="execute",
            proposed_payload={"splits": [{"deal_id": "1", "split_owner_id": "2", "split_percentage": 50}]},
        )
        assert result.status == "success"
