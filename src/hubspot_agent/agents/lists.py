from __future__ import annotations

import hubspot_agent.tools.lists  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_list",
    "hubspot_list_lists",
    "hubspot_create_list",
    "hubspot_update_list",
    "hubspot_add_to_list",
    "hubspot_remove_from_list",
]

_DOMAIN = (
    "You manage HubSpot CRM lists (static and dynamic). "
    "You retrieve, list, create, update lists and add or remove memberships."
)


def get_lists_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Lists Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
