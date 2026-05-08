from hubspot_agent.orchestrator import (
    _AGENT_DESCRIPTIONS,
    _order_with_dependencies,
    build_routing_prompt,
    parse_llm_routing_response,
    route_request,
)


def test_build_routing_prompt_contains_descriptions():
    prompt = build_routing_prompt("find contacts in northeast")
    assert "Available agents:" in prompt
    for name, desc in _AGENT_DESCRIPTIONS.items():
        assert f"- {name}: {desc}" in prompt


def test_build_routing_prompt_contains_request():
    prompt = build_routing_prompt("find contacts in northeast")
    assert "find contacts in northeast" in prompt


def test_parse_llm_routing_response_simple():
    result = parse_llm_routing_response('["objects"]')
    assert result == ["objects"]


def test_parse_llm_routing_response_multiple():
    result = parse_llm_routing_response('["properties", "workflows"]')
    assert result.index("properties") < result.index("workflows")


def test_parse_llm_routing_response_with_explanation():
    result = parse_llm_routing_response('Based on the request, I will use ["objects"]')
    assert result == ["objects"]


def test_parse_llm_routing_response_empty_array():
    result = parse_llm_routing_response("[]")
    assert result == []


def test_parse_llm_routing_response_invalid_json():
    result = parse_llm_routing_response("not json at all")
    assert result == []


def test_parse_llm_routing_response_unknown_agent_filtered():
    result = parse_llm_routing_response('["objects", "fake_agent"]')
    assert result == ["objects"]


def test_parse_llm_routing_response_dependencies_applied():
    result = parse_llm_routing_response('["workflows", "properties"]')
    assert result.index("properties") < result.index("workflows")


def test_route_request_with_llm_response():
    # Phrased to avoid fast-path keywords ("deal" would match objects)
    result = route_request("how many closed this month", llm_response='["analytics"]')
    assert "analytics" in result


def test_route_request_llm_with_dependency():
    result = route_request("create a workflow", llm_response='["workflows", "properties"]')
    assert "properties" in result
    assert result.index("properties") < result.index("workflows")


def test_order_with_dependencies_no_deps():
    assert _order_with_dependencies(["objects", "properties"]) == ["objects", "properties"]


def test_order_with_dependencies_with_deps():
    assert _order_with_dependencies(["workflows", "properties"]) == ["properties", "workflows"]


def test_order_with_dependencies_multiple_deps():
    # objects is not in the input, so it is not inserted
    assert _order_with_dependencies(["workflows", "lists", "properties"]) == ["properties", "workflows", "lists"]
