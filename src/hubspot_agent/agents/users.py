from __future__ import annotations

import hubspot_agent.tools.users  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_user",
    "hubspot_list_users",
    "hubspot_create_user",
    "hubspot_update_user",
    "hubspot_deactivate_user",
]

_DOMAIN = (
    "You manage HubSpot users and their roles. "
    "You retrieve, list, create, update, and deactivate user accounts."
)


def get_users_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Users Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
