"""T7: `hubspot agents list` / `tools list` / `agent-prompt <name>`.

Catalog introspection subcommands.  Counts are derived from the live registries
(never hardcoded).  Verifies ``agents``/``tools``/``agent-prompt`` do not
collide with the ``tool`` (T6) or other existing subcommand prefixes.
"""
from __future__ import annotations

import json

from hubspot_agent.agents import list_agent_names
from hubspot_agent.cli import hubspot_command
from hubspot_agent.tools import list_tools


def test_agents_list_emits_registry(tmp_path):
    out = hubspot_command("agents list", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert payload["count"] == len(list_agent_names())
    names = {a["name"] for a in payload["agents"]}
    assert "objects" in names
    for entry in payload["agents"]:
        assert {"name", "category", "emoji"} <= set(entry.keys())


def test_agents_list_bare_matches_list_form(tmp_path):
    assert json.loads(hubspot_command("agents", working_dir=str(tmp_path))) == json.loads(
        hubspot_command("agents list", working_dir=str(tmp_path))
    )


def test_tools_list_emits_registry(tmp_path):
    out = hubspot_command("tools list", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert payload["count"] == len(list_tools())
    names = {t["name"] for t in payload["tools"]}
    assert "hubspot_get_object" in names
    for entry in payload["tools"]:
        assert {"name", "description", "async"} <= set(entry.keys())


def test_agent_prompt_known(tmp_path):
    out = hubspot_command("agent-prompt objects", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert payload["name"] == "objects"
    assert payload["agent_name"]  # display name (e.g. "Objects Agent")
    assert payload["system_prompt"]
    assert "hubspot_get_object" in payload["tool_names"]


def test_agent_prompt_unknown_lists_known(tmp_path):
    out = hubspot_command("agent-prompt bogus", working_dir=str(tmp_path))
    assert "Unknown agent: bogus" in out
    assert "objects" in out  # known-agents listing


def test_agent_prompt_bare_returns_usage(tmp_path):
    out = hubspot_command("agent-prompt", working_dir=str(tmp_path))
    assert "Usage: /hubspot agent-prompt <name>" in out


def test_agents_list_needs_no_portal(tmp_path):
    # No .hubspot-portal; catalog listing must still work.
    out = hubspot_command("agents list", working_dir=str(tmp_path))
    assert json.loads(out)["count"] == len(list_agent_names())


def test_tools_prefix_does_not_collide_with_tool(tmp_path):
    """`tools list` hits the catalog handler, not the T6 `tool` dispatcher."""
    out = hubspot_command("tools list", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert "tools" in payload and "agents" not in payload

    # And `tool <name>` still routes to the tool dispatcher (unknown-tool path).
    out2 = hubspot_command("tool hubspot_bogus", working_dir=str(tmp_path))
    assert "Unknown tool: hubspot_bogus" in out2