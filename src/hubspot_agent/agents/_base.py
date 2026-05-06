from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hubspot_agent.config import PortalConfig
from hubspot_agent.tools import ToolDef, list_tools


@dataclass
class AgentPrompt:
    agent_name: str
    system_prompt: str
    tool_names: list[str] = field(default_factory=list)


def format_tool_descriptions(tools: list[ToolDef]) -> str:
    lines: list[str] = []
    for t in tools:
        lines.append(f"- {t.name}: {t.description}")
    return "\n".join(lines)


def build_agent_prompt(
    agent_name: str,
    domain_description: str,
    available_tools: list[ToolDef],
    portal_config: PortalConfig | None = None,
) -> AgentPrompt:
    tool_list = format_tool_descriptions(available_tools)
    portal_info = ""
    if portal_config:
        portal_info = (
            f"\nPortal context:\n"
            f"- Portal ID: {portal_config.portal_id}\n"
            f"- Tier: {portal_config.tier}\n"
        )

    system_prompt = (
        f"You are the {agent_name} for HubSpot CRM.\n\n"
        f"{domain_description}\n\n"
        f"Available tools:\n{tool_list}\n"
        f"{portal_info}\n"
        f"Instructions:\n"
        f"- Use the available tools to fulfill the user's request.\n"
        f"- Always return results as structured JSON.\n"
        f"- If a tool returns an error, surface it clearly with the tool name.\n"
        f"- For write operations, confirm the action before executing.\n"
        f"- If the request is ambiguous, ask for clarification.\n"
    )

    return AgentPrompt(
        agent_name=agent_name,
        system_prompt=system_prompt,
        tool_names=[t.name for t in available_tools],
    )
