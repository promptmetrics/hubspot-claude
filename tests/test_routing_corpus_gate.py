"""T5: routing corpus regression gate + `hubspot route` subcommand shape.

Loads tests/routing_corpus.yaml and locks `route_request` output for every
`mode: fast_path` entry.  `mode: llm` entries are aspirational targets for the
stub LLM router and are skipped (LLM router not live).  Also verifies the
`hubspot route '<request>'` CLI subcommand emits the frozen JSON shape
``{"agents": [...], "rationale": "..."}``.

Run via: pytest -k routing_corpus
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from hubspot_agent.cli import hubspot_command
from hubspot_agent.orchestrator import route_request

CORPUS_PATH = Path(__file__).parent / "routing_corpus.yaml"


def _load_corpus() -> list[dict]:
    with CORPUS_PATH.open() as fh:
        entries = yaml.safe_load(fh)
    assert entries is not None, "routing_corpus.yaml is empty"
    return entries


def _fast_path_entries() -> list[dict]:
    return [e for e in _load_corpus() if e.get("mode") == "fast_path"]


def _llm_entries() -> list[dict]:
    return [e for e in _load_corpus() if e.get("mode") == "llm"]


@pytest.mark.parametrize(
    "entry",
    _fast_path_entries(),
    ids=lambda e: f"{e['mode']}:{e['request'][:30]!r}",
)
def test_fast_path_corpus_matches_route_request(entry):
    """Every fast_path entry's expected_routes must equal live route_request output."""
    assert route_request(entry["request"]) == entry["expected_routes"]


@pytest.mark.parametrize(
    "entry",
    _llm_entries(),
    ids=lambda e: f"llm:{e['request'][:30]!r}",
)
def test_llm_corpus_entries_skipped(entry):
    """LLM-router entries are not gated against the keyword router (stub not live)."""
    pytest.skip("LLM router is a stub; llm corpus entries are not gated")


def test_corpus_has_fast_path_and_edge_cases():
    entries = _load_corpus()
    modes = {e.get("mode") for e in entries}
    assert "fast_path" in modes
    by_req = {e["request"]: e for e in entries}
    assert by_req[""]["expected_routes"] == []
    assert by_req["hello"]["expected_routes"] == []


def test_hubspot_route_subcommand_emits_frozen_json_shape(tmp_path):
    """`hubspot route '<request>'` returns JSON {agents, rationale} wrapping route_request."""
    out = hubspot_command("route find all contacts", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert set(payload.keys()) == {"agents", "rationale"}
    assert payload["agents"] == route_request("find all contacts", portal_id=None)
    assert isinstance(payload["rationale"], str) and payload["rationale"]


def test_hubspot_route_empty_request(tmp_path):
    # _parse_flags strips trailing whitespace, so bare `route` is the empty-arg form.
    out = hubspot_command("route", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert payload == {"agents": [], "rationale": "empty request; no agents routed"}


def test_hubspot_route_no_match(tmp_path):
    out = hubspot_command("route hello", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert payload["agents"] == []
    assert "no keyword match" in payload["rationale"]


def test_hubspot_route_multi_agent_rationale(tmp_path):
    out = hubspot_command("route list workflows", working_dir=str(tmp_path))
    payload = json.loads(out)
    assert payload["agents"] == route_request("list workflows", portal_id=None)
    assert "dependency order" in payload["rationale"]