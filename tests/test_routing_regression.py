from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from hubspot_agent.orchestrator import (
    _fast_path_route,
    build_routing_prompt,
    parse_llm_routing_response,
    route_request,
)


_CORPUS_PATH = Path(__file__).parent / "routing_corpus.yaml"


@pytest.fixture(scope="session")
def corpus():
    with _CORPUS_PATH.open("r") as f:
        return yaml.safe_load(f)


class TestFastPathRegression:
    def test_fast_path_cases(self, corpus):
        for case in corpus:
            if case.get("mode") != "fast_path":
                continue
            request = case["request"]
            expected = case["expected_routes"]
            result = _fast_path_route(request)
            # _fast_path_route returns None for no match / ambiguity;
            # normalize to [] for comparison with expected routes.
            if result is None:
                result = []
            assert result == expected, f"Fast-path routing failed for '{request}': got {result}, expected {expected}"

    def test_empty_request_returns_none(self):
        assert _fast_path_route("") is None

    def test_gibberish_returns_none(self):
        assert _fast_path_route("xyz abc 123 !!!") is None


class TestLLMRoutingRegression:
    def test_llm_response_parsing(self, corpus):
        for case in corpus:
            if case.get("mode") != "llm":
                continue
            expected = case["expected_routes"]
            # Simulate a well-formed LLM response
            llm_response = f'Here is my analysis.\n\n```json\n{json.dumps(expected)}\n```'
            result = parse_llm_routing_response(llm_response)
            assert result == expected, f"LLM parsing failed for '{case['request']}': got {result}, expected {expected}"

    def test_parse_llm_routing_response_variations(self):
        # Plain JSON array
        assert parse_llm_routing_response('["objects"]') == ["objects"]
        # Markdown code block
        assert parse_llm_routing_response('```json\n["workflows"]\n```') == ["workflows"]
        # Text surrounding JSON
        assert parse_llm_routing_response('I think you should use ["engagements"] for this.') == ["engagements"]
        # Invalid agent names are filtered
        assert parse_llm_routing_response('["objects", "fake_agent"]') == ["objects"]
        # Malformed JSON returns empty
        assert parse_llm_routing_response('not json') == []


class TestRoutingPromptStability:
    def test_prompt_contains_all_agents(self):
        prompt = build_routing_prompt("test request")
        assert "objects" in prompt
        assert "workflows" in prompt
        assert "contacts" in prompt
        assert "test request" in prompt

    def test_prompt_structure(self):
        prompt = build_routing_prompt("find contacts")
        assert "{{" not in prompt, "Unreplaced template variable in prompt"
        assert "}}" not in prompt, "Unreplaced template variable in prompt"

    def test_prompt_with_routing_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hubspot_agent.routing.Path.home", lambda: tmp_path)
        from hubspot_agent.routing import save_routing_overrides

        save_routing_overrides("123", {"aliases": {"lead": "contact"}})
        prompt = build_routing_prompt("find leads", portal_id="123")
        assert "lead" in prompt or "contact" in prompt


class TestRouteRequestIntegration:
    def test_route_request_fast_path(self, corpus):
        for case in corpus:
            if case.get("mode") != "fast_path":
                continue
            result = route_request(case["request"])
            assert result == case["expected_routes"]

    def test_route_request_with_llm_response(self):
        result = route_request("complex request", llm_response='["analytics", "objects"]')
        assert result == ["analytics", "objects"]

    def test_route_request_ambiguous_returns_empty(self):
        # A request that doesn't match any fast-path keywords and has no LLM response
        result = route_request("completely ambiguous request xyz")
        assert result == []
