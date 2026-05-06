from __future__ import annotations

import hubspot_agent.tools.objects  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_object",
    "hubspot_search_objects",
    "hubspot_create_object",
    "hubspot_update_object",
    "hubspot_delete_object",
    "hubspot_batch_upsert_objects",
]

_DOMAIN = (
    "You manage contacts, companies, deals, and tickets in HubSpot. "
    "You retrieve, search, create, update, and delete records, "
    "and perform batch upserts with input-side deduplication."
)


def get_objects_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Objects Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
