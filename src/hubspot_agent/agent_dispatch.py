from __future__ import annotations

from typing import Any

from hubspot_agent.agents.verify import get_verify_agent_prompt
from hubspot_agent.config import PortalConfig


def spawn_agent(agent_name: str, prompt: str, context: dict[str, Any] | None = None) -> str:
    """No-op stub: there is no in-process Python runtime for spawning sub-agents.

    The durable loop's reasoning steps (triage, verify) are performed by
    **Claude in-session** — Claude produces the ``LoopPlan`` and the
    ``VerificationResult`` and feeds them to the deterministic Python executor
    through the ``hubspot loop start --plan`` / ``hubspot loop verify --result``
    CLI subcommands.  There is no Anthropic SDK call and no ``claude_code``
    module to import here (the old ``from claude_code import Agent`` seam never
    resolved in production and has been removed).

    This stub is retained only so ``sequential_dispatch.verify_step`` — the
    legacy, non-durable ``execute_plan`` path — still has a callable that
    returns a deterministic ``[agent:<name>:no_runtime]`` placeholder (which it
    treats as "assumed verified").  It always returns that placeholder.
    """
    return f"[agent:{agent_name}:no_runtime]"


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
