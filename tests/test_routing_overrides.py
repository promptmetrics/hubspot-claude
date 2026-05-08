from hubspot_agent.routing import (
    apply_routing_overrides,
    build_routing_overrides_context,
    load_routing_overrides,
    save_routing_overrides,
)


def test_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.routing.Path.home", lambda: tmp_path)
    assert load_routing_overrides("123") == {}


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.routing.Path.home", lambda: tmp_path)
    data = {"aliases": {"lead": "contact"}, "agent_overrides": {"custom object": ["objects"]}}
    save_routing_overrides("123", data)
    loaded = load_routing_overrides("123")
    assert loaded == data


def test_load_corrupt_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.routing.Path.home", lambda: tmp_path)
    path = tmp_path / ".claude" / "hubspot" / "123" / "routing_overrides.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json")
    assert load_routing_overrides("123") == {}


def test_apply_aliases_simple():
    overrides = {"aliases": {"lead": "contact"}}
    assert apply_routing_overrides("find leads", overrides) == "find contacts"


def test_apply_aliases_longest_first():
    overrides = {"aliases": {"custom object": "company", "object": "contact"}}
    assert apply_routing_overrides("create custom object", overrides) == "create company"


def test_apply_aliases_no_match():
    overrides = {"aliases": {"lead": "contact"}}
    assert apply_routing_overrides("find deals", overrides) == "find deals"


def test_build_context_aliases_only():
    overrides = {"aliases": {"lead": "contact"}}
    ctx = build_routing_overrides_context(overrides)
    assert "Portal-specific vocabulary:" in ctx
    assert '"lead" means "contact"' in ctx


def test_build_context_agent_overrides_only():
    overrides = {"agent_overrides": {"custom object": ["objects"]}}
    ctx = build_routing_overrides_context(overrides)
    assert "Portal-specific agent overrides:" in ctx
    assert 'If the request mentions "custom object"' in ctx


def test_build_context_empty():
    assert build_routing_overrides_context({}) == ""
    assert build_routing_overrides_context({"aliases": {}, "agent_overrides": {}}) == ""


def test_build_context_both():
    overrides = {
        "aliases": {"lead": "contact"},
        "agent_overrides": {"custom object": ["objects"]},
    }
    ctx = build_routing_overrides_context(overrides)
    assert "Portal-specific vocabulary:" in ctx
    assert "Portal-specific agent overrides:" in ctx
