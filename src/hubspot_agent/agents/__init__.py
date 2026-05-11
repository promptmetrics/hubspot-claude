from __future__ import annotations

from typing import Callable

from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.agents.analytics import get_analytics_agent_prompt
from hubspot_agent.agents.associations import get_associations_agent_prompt
from hubspot_agent.agents.custom_objects import get_custom_objects_agent_prompt
from hubspot_agent.agents.engagements import get_engagements_agent_prompt
from hubspot_agent.agents.hygiene import get_hygiene_agent_prompt
from hubspot_agent.agents.lists import get_lists_agent_prompt
from hubspot_agent.agents.objects import get_objects_agent_prompt
from hubspot_agent.agents.pipelines import get_pipelines_agent_prompt
from hubspot_agent.agents.properties import get_properties_agent_prompt
from hubspot_agent.agents.raw_api import get_raw_api_agent_prompt
from hubspot_agent.agents.service import get_service_agent_prompt
from hubspot_agent.agents.users import get_users_agent_prompt
from hubspot_agent.agents.workflows import get_workflows_agent_prompt

_AGENT_REGISTRY: dict[str, Callable[..., AgentPrompt]] = {
    "objects": get_objects_agent_prompt,
    "properties": get_properties_agent_prompt,
    "workflows": get_workflows_agent_prompt,
    "lists": get_lists_agent_prompt,
    "pipelines": get_pipelines_agent_prompt,
    "users": get_users_agent_prompt,
    "hygiene": get_hygiene_agent_prompt,
    "analytics": get_analytics_agent_prompt,
    "associations": get_associations_agent_prompt,
    "engagements": get_engagements_agent_prompt,
    "custom_objects": get_custom_objects_agent_prompt,
    "service": get_service_agent_prompt,
    "raw_api": get_raw_api_agent_prompt,
}


def get_agent_prompt(agent_name: str, portal_config=None) -> AgentPrompt | None:
    builder = _AGENT_REGISTRY.get(agent_name)
    if builder is None:
        return None
    return builder(portal_config)


def list_agent_names() -> list[str]:
    return list(_AGENT_REGISTRY.keys())


__all__ = [
    "AgentPrompt",
    "build_agent_prompt",
    "get_agent_prompt",
    "list_agent_names",
    "_AGENT_REGISTRY",
]
