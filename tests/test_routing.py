import json
from pathlib import Path

import pytest

from hubspot_agent.routing import (
    apply_routing_overrides,
    build_routing_overrides_context,
    load_routing_overrides,
    save_routing_overrides,
)


def _fake_portal_dir(tmp_path: Path):
    def inner(portal_id: str) -> Path:
        return tmp_path / portal_id
    return inner


class TestLoadRoutingOverrides:
    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "hubspot_agent.maintenance._portal_dir", _fake_portal_dir(tmp_path)
        )
        assert load_routing_overrides("123") == {}

    def test_loads_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "hubspot_agent.maintenance._portal_dir", _fake_portal_dir(tmp_path)
        )
        overrides = {"aliases": {"deal": "transaction"}}
        portal_dir = tmp_path / "123"
        portal_dir.mkdir()
        (portal_dir / "routing_overrides.json").write_text(json.dumps(overrides))
        assert load_routing_overrides("123") == overrides

    def test_bad_json_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "hubspot_agent.maintenance._portal_dir", _fake_portal_dir(tmp_path)
        )
        portal_dir = tmp_path / "123"
        portal_dir.mkdir()
        (portal_dir / "routing_overrides.json").write_text("not json")
        assert load_routing_overrides("123") == {}


class TestSaveRoutingOverrides:
    def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "hubspot_agent.maintenance._portal_dir", _fake_portal_dir(tmp_path)
        )
        save_routing_overrides("456", {"aliases": {"foo": "bar"}})
        path = tmp_path / "456" / "routing_overrides.json"
        assert path.exists()
        assert json.loads(path.read_text()) == {"aliases": {"foo": "bar"}}


class TestApplyRoutingOverrides:
    def test_no_aliases_returns_unchanged(self):
        assert apply_routing_overrides("hello world", {}) == "hello world"

    def test_applies_aliases(self):
        overrides = {"aliases": {"world": "universe"}}
        assert apply_routing_overrides("hello world", overrides) == "hello universe"

    def test_longer_phrases_first(self):
        overrides = {"aliases": {"custom object": "CO", "object": "obj"}}
        assert apply_routing_overrides("custom object", overrides) == "CO"

    def test_multiple_aliases(self):
        overrides = {"aliases": {"a": "1", "b": "2"}}
        assert apply_routing_overrides("a b", overrides) == "1 2"


class TestBuildRoutingOverridesContext:
    def test_empty_overrides(self):
        assert build_routing_overrides_context({}) == ""

    def test_aliases_only(self):
        overrides = {"aliases": {"deal": "transaction"}}
        ctx = build_routing_overrides_context(overrides)
        assert 'Portal-specific vocabulary:' in ctx
        assert '"deal" means "transaction"' in ctx

    def test_agent_overrides_only(self):
        overrides = {"agent_overrides": {"report": ["analytics", "reporting"]}}
        ctx = build_routing_overrides_context(overrides)
        assert 'Portal-specific agent overrides:' in ctx
        assert '"report"' in ctx
        assert str(["analytics", "reporting"]) in ctx

    def test_both(self):
        overrides = {
            "aliases": {"deal": "transaction"},
            "agent_overrides": {"report": ["analytics"]},
        }
        ctx = build_routing_overrides_context(overrides)
        assert 'Portal-specific vocabulary:' in ctx
        assert 'Portal-specific agent overrides:' in ctx
