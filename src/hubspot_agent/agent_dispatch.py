from __future__ import annotations

from typing import Any

from hubspot_agent.agents.triage import get_triage_agent_prompt
from hubspot_agent.agents.verify import get_verify_agent_prompt
from hubspot_agent.config import PortalConfig


DEFAULT_TIMEOUT_MS = 120000


def spawn_agent(agent_name: str, prompt: str, context: dict[str, Any] | None = None) -> str:
    """Spawn a sub-agent via Claude Code's Agent tool and return its raw response text.

    Args:
        agent_name: The loop-level agent role, e.g. "triage" or "verify".
        prompt: The full prompt to send to the sub-agent.
        context: Optional extra context (currently unused but reserved for future routing).

    Returns:
        Raw text returned by the sub-agent, or an empty string on timeout/no response.
    """
    context = context or {}

    # We use the Explore agent type by default for isolated reasoning tasks.
    subagent_type = "Explore"
    description = f"Spawn {agent_name} agent"

    # This function is designed to be called from within Claude Code. The Agent tool
    # is provided by the runtime; we avoid importing it at module load so the file can
    # still be unit-tested outside a Claude Code session.
    try:
        from claude_code import Agent as RuntimeAgent  # type: ignore[import-not-found]
    except ImportError:
        RuntimeAgent = None  # type: ignore[misc,assignment]

    if RuntimeAgent is None:
        # When not running inside Claude Code, return a deterministic placeholder
        # that unit tests can patch or assert against.
        return f"[agent:{agent_name}:no_runtime]"

    agent_result = RuntimeAgent(
        description=description,
        prompt=prompt,
        subagent_type=subagent_type,
    )
    # Tool results are strings in this environment.
    if not agent_result:
        return ""
    return str(agent_result)


def build_triage_prompt(request_text: str, portal_config: PortalConfig | None = None) -> str:
    prompt = get_triage_agent_prompt(portal_config)
    return f"{prompt.system_prompt}\n\nUser request: {request_text}\n\nReturn a LoopPlan JSON or clarifying questions."


def build_verify_prompt(
    step: dict[str, Any],
    expected_state: dict[str, Any],
    portal_config: PortalConfig | None = None,
) -> str:
    prompt = get_verify_agent_prompt(portal_config)
    return (
        f"{prompt.system_prompt}\n\n"
        f"Step executed: {step}\n\n"
        f"Expected state: {expected_state}\n\n"
        f"Return a VerificationResult JSON comparing actual HubSpot state to the expected state."
    )
