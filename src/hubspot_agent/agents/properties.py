from __future__ import annotations

import hubspot_agent.tools.properties  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_property",
    "hubspot_list_properties",
    "hubspot_create_property",
    "hubspot_update_property",
    "hubspot_delete_property",
]

_DOMAIN = (
    "You manage custom property definitions for HubSpot object types (contacts, companies, deals, tickets). "
    "You retrieve, list, create, update, and delete properties and their field types."
)


def get_properties_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Properties Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
