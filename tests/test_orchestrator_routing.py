from hubspot_agent.orchestrator import route_request


def test_route_objects_keywords():
    result = route_request("find contacts in northeast")
    assert "objects" in result


def test_route_properties_keywords():
    result = route_request("add a property field")
    assert "properties" in result


def test_route_workflows_keywords():
    result = route_request("build an automation workflow")
    assert "workflows" in result


def test_route_lists_keywords():
    result = route_request("remove from list")
    assert "lists" in result


def test_route_engagements_keywords():
    result = route_request("log a call with the prospect")
    assert "engagements" in result


def test_route_ambiguous_returns_empty():
    result = route_request("hello world")
    assert result == []


def test_route_non_fast_path_agents():
    assert route_request("reorder stages in the sales pipeline") == ["pipelines"]
    assert route_request("onboard a new user") == ["users"]
    assert route_request("clean up duplicates") == ["hygiene"]
    assert route_request("show me the analytics dashboard") == ["analytics"]
    result = route_request("link records to companies")
    assert set(result) == {"objects", "associations"}
    assert route_request("use raw api for custom endpoint") == ["raw_api"]
