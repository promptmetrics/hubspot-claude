from __future__ import annotations

import hubspot_agent.tools.associations  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_association_schema",
    "hubspot_create_association_schema",
    "hubspot_associate_records",
    "hubspot_disassociate_records",
]

_DOMAIN = (
    "You manage HubSpot associations between objects. "
    "You retrieve and create association schemas, and link or unlink records."
)


def get_associations_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Associations Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
