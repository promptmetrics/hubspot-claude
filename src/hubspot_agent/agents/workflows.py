from __future__ import annotations

import hubspot_agent.tools.workflows  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.blueprints.workflows import build_blueprint_context
from hubspot_agent.config import PortalConfig

# Import blueprint modules to trigger self-registration
from hubspot_agent.blueprints.workflows import (  # noqa: F401
    deal_stage_task,
    lead_scoring,
    re_engagement,
    welcome_email,
)
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_get_workflow",
    "hubspot_list_workflows",
    "hubspot_create_workflow",
    "hubspot_update_workflow",
    "hubspot_enroll_workflow",
    "hubspot_toggle_workflow",
]

_DOMAIN = (
    "You manage HubSpot automation workflows. "
    "You retrieve, list, create, update, enroll records in, and toggle workflow states."
)


def get_workflows_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    prompt = build_agent_prompt(
        agent_name="Workflows Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
    blueprint_ctx = build_blueprint_context()
    prompt.system_prompt += f"\n\n{blueprint_ctx}"
    return prompt
