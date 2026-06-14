from __future__ import annotations

from typing import Callable

from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.agents.account_info import get_account_info_agent_prompt
from hubspot_agent.agents.analytics import get_analytics_agent_prompt
from hubspot_agent.agents.appointments import get_appointments_agent_prompt
from hubspot_agent.agents.associations import get_associations_agent_prompt
from hubspot_agent.agents.audit_logs import get_audit_logs_agent_prompt
from hubspot_agent.agents.carts import get_carts_agent_prompt
from hubspot_agent.agents.commerce import get_commerce_agent_prompt
from hubspot_agent.agents.communications import get_communications_agent_prompt
from hubspot_agent.agents.courses import get_courses_agent_prompt
from hubspot_agent.agents.custom_objects import get_custom_objects_agent_prompt
from hubspot_agent.agents.data import get_data_agent_prompt
from hubspot_agent.agents.deal_splits import get_deal_splits_agent_prompt
from hubspot_agent.agents.discounts import get_discounts_agent_prompt
from hubspot_agent.agents.email_events import get_email_events_agent_prompt
from hubspot_agent.agents.engagements import get_engagements_agent_prompt
from hubspot_agent.agents.fees import get_fees_agent_prompt
from hubspot_agent.agents.forecasts import get_forecasts_agent_prompt
from hubspot_agent.agents.forms import get_forms_agent_prompt
from hubspot_agent.agents.goals import get_goals_agent_prompt
from hubspot_agent.agents.hygiene import get_hygiene_agent_prompt
from hubspot_agent.agents.invoices import get_invoices_agent_prompt
from hubspot_agent.agents.leads import get_leads_agent_prompt
from hubspot_agent.agents.lists import get_lists_agent_prompt
from hubspot_agent.agents.listings import get_listings_agent_prompt
from hubspot_agent.agents.object_library import get_object_library_agent_prompt
from hubspot_agent.agents.objects import get_objects_agent_prompt
from hubspot_agent.agents.orders import get_orders_agent_prompt
from hubspot_agent.agents.pipelines import get_pipelines_agent_prompt
from hubspot_agent.agents.projects import get_projects_agent_prompt
from hubspot_agent.agents.properties import get_properties_agent_prompt
from hubspot_agent.agents.quotes import get_quotes_agent_prompt
from hubspot_agent.agents.raw_api import get_raw_api_agent_prompt
from hubspot_agent.agents.scheduler import get_scheduler_agent_prompt
from hubspot_agent.agents.security_history import get_security_history_agent_prompt
from hubspot_agent.agents.sequences import get_sequences_agent_prompt
from hubspot_agent.agents.service import get_service_agent_prompt
from hubspot_agent.agents.services import get_services_agent_prompt
from hubspot_agent.agents.subscriptions import get_subscriptions_agent_prompt
from hubspot_agent.agents.taxes import get_taxes_agent_prompt
from hubspot_agent.agents.timeline_events import get_timeline_events_agent_prompt
from hubspot_agent.agents.triage import get_triage_agent_prompt
from hubspot_agent.agents.users import get_users_agent_prompt
from hubspot_agent.agents.verify import get_verify_agent_prompt
from hubspot_agent.agents.workflows import get_workflows_agent_prompt

_AGENT_REGISTRY: dict[str, Callable[..., AgentPrompt]] = {
    "objects": get_objects_agent_prompt,
    "properties": get_properties_agent_prompt,
    "workflows": get_workflows_agent_prompt,
    "lists": get_lists_agent_prompt,
    "pipelines": get_pipelines_agent_prompt,
    "users": get_users_agent_prompt,
    "hygiene": get_hygiene_agent_prompt,
    "analytics": get_analytics_agent_prompt,
    "associations": get_associations_agent_prompt,
    "engagements": get_engagements_agent_prompt,
    "custom_objects": get_custom_objects_agent_prompt,
    "service": get_service_agent_prompt,
    "raw_api": get_raw_api_agent_prompt,
    "forms": get_forms_agent_prompt,
    "data": get_data_agent_prompt,
    "commerce": get_commerce_agent_prompt,
    "carts": get_carts_agent_prompt,
    "orders": get_orders_agent_prompt,
    "quotes": get_quotes_agent_prompt,
    "subscriptions": get_subscriptions_agent_prompt,
    "invoices": get_invoices_agent_prompt,
    "deal_splits": get_deal_splits_agent_prompt,
    "discounts": get_discounts_agent_prompt,
    "fees": get_fees_agent_prompt,
    "taxes": get_taxes_agent_prompt,
    "goals": get_goals_agent_prompt,
    "appointments": get_appointments_agent_prompt,
    "courses": get_courses_agent_prompt,
    "listings": get_listings_agent_prompt,
    "services": get_services_agent_prompt,
    "communications": get_communications_agent_prompt,
    "leads": get_leads_agent_prompt,
    "projects": get_projects_agent_prompt,
    "object_library": get_object_library_agent_prompt,
    "sequences": get_sequences_agent_prompt,
    "scheduler": get_scheduler_agent_prompt,
    "account_info": get_account_info_agent_prompt,
    "audit_logs": get_audit_logs_agent_prompt,
    "security_history": get_security_history_agent_prompt,
    "email_events": get_email_events_agent_prompt,
    "forecasts": get_forecasts_agent_prompt,
    "timeline_events": get_timeline_events_agent_prompt,
    "triage": get_triage_agent_prompt,
    "verify": get_verify_agent_prompt,
}

# Category taxonomy for visual grouping and CLI organization
_AGENT_CATEGORIES: dict[str, tuple[str, str]] = {
    # Core CRM
    "objects": ("Core CRM", "🧩"),
    "properties": ("Core CRM", "🧩"),
    "custom_objects": ("Core CRM", "🧩"),
    "associations": ("Core CRM", "🧩"),
    "lists": ("Core CRM", "📋"),
    # Automation
    "workflows": ("Automation", "⚙️"),
    "pipelines": ("Automation", "⚙️"),
    "sequences": ("Automation", "⚙️"),
    "scheduler": ("Automation", "⚙️"),
    # Engagement
    "engagements": ("Engagement", "💬"),
    "communications": ("Engagement", "💬"),
    "leads": ("Engagement", "💬"),
    # Users
    "users": ("Users & Access", "👤"),
    # Analytics & Data
    "analytics": ("Analytics & Data", "📊"),
    "hygiene": ("Analytics & Data", "📊"),
    "forecasts": ("Analytics & Data", "📊"),
    "data": ("Analytics & Data", "📊"),
    # Service Hub
    "service": ("Service Hub", "🛎️"),
    "forms": ("Service Hub", "🛎️"),
    # Commerce
    "commerce": ("Commerce", "🛒"),
    "carts": ("Commerce", "🛒"),
    "orders": ("Commerce", "🛒"),
    "quotes": ("Commerce", "🛒"),
    "subscriptions": ("Commerce", "🛒"),
    "invoices": ("Commerce", "🛒"),
    "deal_splits": ("Commerce", "🛒"),
    "discounts": ("Commerce", "🛒"),
    "fees": ("Commerce", "🛒"),
    "taxes": ("Commerce", "🛒"),
    "services": ("Commerce", "🛒"),
    # Content & Projects
    "projects": ("Content & Projects", "📝"),
    "object_library": ("Content & Projects", "📝"),
    "courses": ("Content & Projects", "📝"),
    "listings": ("Content & Projects", "📝"),
    "appointments": ("Content & Projects", "📝"),
    "goals": ("Content & Projects", "📝"),
    # System & Audit
    "raw_api": ("System & Audit", "🔒"),
    "account_info": ("System & Audit", "🔒"),
    "audit_logs": ("System & Audit", "🔒"),
    "security_history": ("System & Audit", "🔒"),
    "email_events": ("System & Audit", "🔒"),
    "timeline_events": ("System & Audit", "🔒"),
    "triage": ("Loop", "🔁"),
    "verify": ("Loop", "✅"),
}


def get_agent_category(agent_name: str) -> str:
    return _AGENT_CATEGORIES.get(agent_name, ("Unknown", "❓"))[0]


def get_agent_emoji(agent_name: str) -> str:
    return _AGENT_CATEGORIES.get(agent_name, ("Unknown", "❓"))[1]


def group_agents_by_category(agent_names: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for name in agent_names:
        category = get_agent_category(name)
        groups.setdefault(category, []).append(name)
    return dict(sorted(groups.items()))


def get_agent_prompt(agent_name: str, portal_config=None) -> AgentPrompt | None:
    builder = _AGENT_REGISTRY.get(agent_name)
    if builder is None:
        return None
    return builder(portal_config)


def list_agent_names() -> list[str]:
    return list(_AGENT_REGISTRY.keys())


__all__ = [
    "AgentPrompt",
    "build_agent_prompt",
    "get_agent_prompt",
    "list_agent_names",
    "_AGENT_REGISTRY",
    "get_agent_category",
    "get_agent_emoji",
    "group_agents_by_category",
    "_AGENT_CATEGORIES",
]
