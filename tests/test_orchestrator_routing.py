from hubspot_agent.orchestrator import route_request


def test_route_objects_keywords():
    result = route_request("find contacts in northeast")
    assert "objects" in result


def test_route_properties_keywords():
    result = route_request("create a custom field for deals")
    assert "properties" in result


def test_route_workflows_keywords():
    result = route_request("build an automation workflow")
    assert "workflows" in result


def test_route_lists_keywords():
    # "list" scores lists=1; no other fast-path agent scores, so it wins
    result = route_request("remove from list")
    assert "lists" in result


def test_route_engagements_keywords():
    result = route_request("log a call with the prospect")
    assert "engagements" in result


def test_route_ambiguous_returns_empty():
    result = route_request("hello world")
    assert result == []


def test_route_non_fast_path_returns_empty_without_llm():
    # pipelines, users, hygiene, analytics, associations, raw_api are not in fast-path.
    # Requests are phrased to avoid accidental fast-path keyword matches.
    assert route_request("reorder stages in the sales pipeline") == []
    assert route_request("onboard a new user") == []
    assert route_request("find duplicate records") == []
    assert route_request("how many closed this month") == []
    assert route_request("link records to companies") == []
    assert route_request("use raw api for custom endpoint") == []


def test_route_multi_agent_ambiguous_without_llm():
    # "property" scores properties=1, "workflow" scores workflows=1
    # Both score 1, so fast-path sees ambiguity (1 < 2*1) and returns None.
    result = route_request("create a property and then build a workflow")
    assert result == []


def test_route_multi_agent_with_llm_response():
    result = route_request(
        "create a property and then build a workflow",
        llm_response='["workflows", "properties"]',
    )
    assert result.index("properties") < result.index("workflows")


def test_route_llm_response_takes_priority():
    # When llm_response is provided it is used directly, bypassing fast-path
    result = route_request("find contacts", llm_response='["properties"]')
    assert "properties" in result
    assert "objects" not in result
