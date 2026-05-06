from __future__ import annotations

import hubspot_agent.tools.analytics  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_report",
    "hubspot_calculate_metrics",
    "hubspot_pipeline_velocity",
]

_DOMAIN = (
    "You provide analytics and reporting for HubSpot. "
    "You retrieve reports, calculate conversion and win rates, and measure pipeline velocity."
)


def get_analytics_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="Analytics Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
