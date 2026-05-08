from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _overrides_path(portal_id: str) -> Path:
    return Path.home() / ".claude" / "hubspot" / portal_id / "routing_overrides.json"


def load_routing_overrides(portal_id: str) -> dict[str, Any]:
    path = _overrides_path(portal_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_routing_overrides(portal_id: str, overrides: dict[str, Any]) -> None:
    path = _overrides_path(portal_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2))


def apply_routing_overrides(request_text: str, overrides: dict[str, Any]) -> str:
    """Replace vocabulary aliases in the request text.

    Aliases are applied in descending length order so that longer phrases
    are replaced before shorter ones (e.g. "custom object" before "object").
    """
    aliases: dict[str, str] = overrides.get("aliases", {})
    if not aliases:
        return request_text
    text = request_text
    for phrase, replacement in sorted(aliases.items(), key=lambda kv: len(kv[0]), reverse=True):
        text = text.replace(phrase, replacement)
    return text


def build_routing_overrides_context(overrides: dict[str, Any]) -> str:
    """Build a prompt snippet that injects custom routing context."""
    parts: list[str] = []
    aliases = overrides.get("aliases", {})
    if aliases:
        parts.append("Portal-specific vocabulary:")
        for phrase, replacement in aliases.items():
            parts.append(f'- "{phrase}" means "{replacement}"')
    agent_overrides = overrides.get("agent_overrides", {})
    if agent_overrides:
        parts.append("Portal-specific agent overrides:")
        for pattern, agents in agent_overrides.items():
            parts.append(f'- If the request mentions "{pattern}", always include: {agents}')
    return "\n".join(parts) if parts else ""
