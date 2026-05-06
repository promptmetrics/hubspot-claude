from __future__ import annotations

import hubspot_agent.tools.engagements  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_engagement",
    "hubspot_search_engagements",
    "hubspot_create_note",
    "hubspot_create_task",
    "hubspot_create_email",
    "hubspot_create_meeting",
    "hubspot_create_call",
]

_DOMAIN = (
    "You manage HubSpot engagements (notes, tasks, emails, meetings, calls). "
    "You retrieve, search, and create engagement records."
)


def get_engagements_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Engagements Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
