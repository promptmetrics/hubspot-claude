from __future__ import annotations

import hubspot_agent.tools.hygiene  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_find_duplicates",
    "hubspot_merge_objects",
    "hubspot_bulk_update_objects",
    "hubspot_preview_segment",
]

_DOMAIN = (
    "You manage data hygiene in HubSpot. "
    "You find duplicate records, merge objects, perform bulk updates, and preview segments before changes."
)


def get_hygiene_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Hygiene Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
