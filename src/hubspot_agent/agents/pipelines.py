from __future__ import annotations

import hubspot_agent.tools.pipelines  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_pipeline",
    "hubspot_list_pipelines",
    "hubspot_create_pipeline",
    "hubspot_update_pipeline",
    "hubspot_reorder_stages",
]

_DOMAIN = (
    "You manage HubSpot CRM pipelines and their stages for deals, tickets, and custom objects. "
    "You retrieve, list, create, update pipelines and reorder stages."
)


def get_pipelines_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Pipelines Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
