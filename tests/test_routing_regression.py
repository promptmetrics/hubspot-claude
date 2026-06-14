from hubspot_agent.orchestrator import (
    _fast_path_route,
    build_routing_prompt,
    parse_llm_routing_response,
    route_request,
)


class TestFastPathRegression:
    def test_empty_request_returns_none(self):
        assert _fast_path_route("") is None

    def test_gibberish_returns_none(self):
        assert _fast_path_route("xyz abc 123 !!!") is None

    def test_fast_path_no_portal_returns_none(self):
        assert _fast_path_route("find contacts") is None

    def test_fast_path_custom_object_match(self, tmp_path, monkeypatch):
        import time
        monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
        from hubspot_agent.cache import SchemaCache

        cache = SchemaCache("123")
        cache._data = {
            "rental_property": {"_timestamp": time.time(), "data": {}},
            "investment_deal": {"_timestamp": time.time(), "data": {}},
        }
        cache._save()

        result = _fast_path_route("find rental_property records", portal_id="123")
        assert result == ["objects"]


class TestLLMRoutingRegression:
    def test_parse_llm_routing_response_basic(self):
        assert parse_llm_routing_response('objects, properties') == ["objects", "properties"]

    def test_parse_llm_routing_response_single(self):
        assert parse_llm_routing_response('workflows') == ["workflows"]


class TestRoutingPromptStability:
    def test_prompt_contains_request(self):
        prompt = build_routing_prompt("find contacts")
        assert "find contacts" in prompt


class TestRouteRequestIntegration:
    def test_route_request_objects(self):
        result = route_request("find contacts")
        assert result == ["objects"]

    def test_route_request_ambiguous_returns_empty(self):
        result = route_request("completely ambiguous request xyz")
        assert result == []
