from __future__ import annotations

import hubspot_agent.tools.raw_api  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = ["hubspot_raw_api"]

_DOMAIN = (
    "You are the power-user escape hatch for HubSpot. "
    "You make direct API calls to any uncovered HubSpot endpoint using the raw API tool. "
    "Use this only when no other specialist agent covers the required endpoint."
)


def get_raw_api_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Raw API Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
