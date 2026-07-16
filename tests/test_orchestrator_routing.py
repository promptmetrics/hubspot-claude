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


def test_route_cross_object_associated_with():
    result = route_request("contacts associated with companies")
    assert "associations" in result
    assert "objects" in result


def test_route_cross_object_linked_to():
    result = route_request("deals linked to companies")
    assert "associations" in result
    assert "objects" in result


def test_route_cross_object_related_to():
    result = route_request("tickets related to contacts")
    assert "associations" in result
    assert "objects" in result


def test_route_cross_object_at_companies():
    # "at" is NOT an association verb — innocuous phrasing must not force
    # associations. Only objects routes (both nouns are object types, but no
    # explicit association verb means no associations agent).
    result = route_request("contacts at companies")
    assert result == ["objects"]
    assert "associations" not in result


def test_route_cross_object_for_company():
    # "for" is NOT an association verb — same rationale as above.
    result = route_request("deals for company")
    assert result == ["objects"]
    assert "associations" not in result


def test_route_association_verb_word_boundary_not_substring():
    # Association verbs are matched on word boundaries, so a word that merely
    # contains a verb as a substring ("correlate" contains "relate",
    # "interrelate" contains "relate") must NOT force associations. Otherwise an
    # analytics/correlation request over two object nouns misroutes to
    # associations instead of the intended domain.
    assert "associations" not in route_request("correlate contact activity with deal closures")
    assert "associations" not in route_request("interrelate contacts and deals")
    # Sanity: a real association verb still fires.
    assert "associations" in route_request("associate a deal with a company")
