from pathlib import Path

from hubspot_agent.query_cache import QueryCache, is_read_tool


def test_is_read_tool():
    assert is_read_tool("hubspot_get_object") is True
    assert is_read_tool("hubspot_search_objects") is True
    assert is_read_tool("hubspot_list_pipelines") is True
    assert is_read_tool("hubspot_create_object") is False
    assert is_read_tool("hubspot_update_object") is False
    assert is_read_tool("hubspot_delete_object") is False


def test_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    assert cache.get("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}) is None


def test_cache_set_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    kwargs = {"object_type": "contacts", "object_id": "1"}
    result = {"id": "1", "email": "test@example.com"}
    cache.set("hubspot_get_object", kwargs, result, domain="contacts")

    cached = cache.get("hubspot_get_object", kwargs)
    assert cached == result


def test_cache_ignores_client_and_portal_id(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    kwargs_a = {"object_type": "contacts", "object_id": "1", "client": "some_client", "portal_id": "123"}
    kwargs_b = {"object_type": "contacts", "object_id": "1", "client": "other_client", "portal_id": "456"}
    result = {"id": "1"}
    cache.set("hubspot_get_object", kwargs_a, result)

    cached = cache.get("hubspot_get_object", kwargs_b)
    assert cached == result


def test_cache_ttl_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    kwargs = {"object_type": "contacts", "object_id": "1"}
    cache.set("hubspot_get_object", kwargs, {"id": "1"})

    # Simulate time passing beyond TTL
    import time
    original_time = time.time
    time.time = lambda: original_time() + 400  # 400 seconds > 300 TTL
    try:
        cached = cache.get("hubspot_get_object", kwargs)
        assert cached is None
    finally:
        time.time = original_time


def test_invalidate_domain(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    cache.set("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}, {"id": "1"}, domain="contacts")
    cache.set("hubspot_get_object", {"object_type": "companies", "object_id": "2"}, {"id": "2"}, domain="companies")

    cache.invalidate_domain("contacts")

    assert cache.get("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}) is None
    assert cache.get("hubspot_get_object", {"object_type": "companies", "object_id": "2"}) is not None


def test_invalidate_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    cache.set("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}, {"id": "1"})
    cache.set("hubspot_search_objects", {"object_type": "contacts"}, {"results": []})

    cache.invalidate_tool("hubspot_get_object")

    assert cache.get("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}) is None
    assert cache.get("hubspot_search_objects", {"object_type": "contacts"}) is not None


def test_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    cache.set("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}, {"id": "1"})
    cache.clear()
    assert cache.get("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}) is None


def test_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache = QueryCache("123")
    cache.set("hubspot_get_object", {"object_type": "contacts", "object_id": "1"}, {"id": "1"})
    cache.set("hubspot_search_objects", {"object_type": "contacts"}, {"results": []})

    stats = cache.stats()
    assert stats["valid"] == 2
    assert stats["expired"] == 0
    assert stats["total"] == 2
    assert stats["by_tool"]["hubspot_get_object"] == 1
    assert stats["by_tool"]["hubspot_search_objects"] == 1


def test_different_portals_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cache_a = QueryCache("123")
    cache_b = QueryCache("456")
    kwargs = {"object_type": "contacts", "object_id": "1"}
    cache_a.set("hubspot_get_object", kwargs, {"id": "1"})

    assert cache_a.get("hubspot_get_object", kwargs) is not None
    assert cache_b.get("hubspot_get_object", kwargs) is None
