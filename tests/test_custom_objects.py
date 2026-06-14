import httpx
import pytest

from hubspot_agent.cache import (
    SchemaCache,
    WARM_DOMAINS,
    discover_custom_schemas,
    warm_standard_schemas,
)
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.orchestrator import route_request, _fast_path_route
from hubspot_agent.tools.objects import _validate_object_type
from hubspot_agent.validation import validate_object_type, validate_properties


@pytest.mark.asyncio
async def test_discover_custom_schemas_caches_and_returns_names(
    respx_mock, tmp_path, monkeypatch
):
    monkeypatch.setattr("hubspot_agent.cache.Path.home", lambda: tmp_path)
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "pets",
                        "properties": [
                            {"name": "pet_name", "type": "string"},
                            {"name": "age", "type": "number"},
                        ],
                    },
                    {
                        "name": "vehicles",
                        "properties": [
                            {"name": "make", "type": "string"},
                            {"name": "year", "type": "number"},
                        ],
                    },
                ]
            },
        )
    )

    portal = PortalConfig(portal_id="123", token="test-token")
    names = await discover_custom_schemas(portal)

    assert sorted(names) == ["pets", "vehicles"]

    cache = SchemaCache("123")
    pets = cache.get("pets")
    assert pets is not None
    assert pets["results"] == [
        {"name": "pet_name", "type": "string"},
        {"name": "age", "type": "number"},
    ]

    vehicles = cache.get("vehicles")
    assert vehicles is not None
    assert vehicles["results"] == [
        {"name": "make", "type": "string"},
        {"name": "year", "type": "number"},
    ]


@pytest.mark.asyncio
async def test_discover_custom_schemas_skips_standard_objects(
    respx_mock, tmp_path, monkeypatch
):
    monkeypatch.setattr("hubspot_agent.cache.Path.home", lambda: tmp_path)
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "contacts",
                        "properties": [{"name": "email", "type": "string"}],
                    },
                    {
                        "name": "pets",
                        "properties": [{"name": "pet_name", "type": "string"}],
                    },
                ]
            },
        )
    )

    portal = PortalConfig(portal_id="123", token="test-token")
    names = await discover_custom_schemas(portal)

    assert names == ["pets"]
    cache = SchemaCache("123")
    assert cache.get("contacts") is None


@pytest.mark.asyncio
async def test_discover_custom_schemas_graceful_empty(respx_mock, tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.cache.Path.home", lambda: tmp_path)
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    portal = PortalConfig(portal_id="123", token="test-token")
    names = await discover_custom_schemas(portal)

    assert names == []


@pytest.mark.asyncio
async def test_discover_custom_schemas_graceful_on_error(
    respx_mock, tmp_path, monkeypatch
):
    monkeypatch.setattr("hubspot_agent.cache.Path.home", lambda: tmp_path)
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )

    portal = PortalConfig(portal_id="123", token="test-token")
    names = await discover_custom_schemas(portal)

    assert names == []


def test_schema_cache_list_custom_object_names(tmp_path):
    cache = SchemaCache("123", base_dir=tmp_path)
    cache.set("pets", {"results": [{"name": "pet_name", "type": "string"}]})
    cache.set("contacts", {"results": [{"name": "email", "type": "string"}]})

    names = cache.list_custom_object_names()
    assert names == ["pets"]


def test_validate_object_type_accepts_standard():
    assert validate_object_type("contacts", "123") is True
    assert validate_object_type("companies", "123") is True
    assert validate_object_type("deals", "123") is True
    assert validate_object_type("tickets", "123") is True


def test_validate_object_type_accepts_custom_from_cache(tmp_path):
    cache = SchemaCache("123", base_dir=tmp_path)
    cache.set("pets", {"results": [{"name": "pet_name", "type": "string"}]})

    assert validate_object_type("pets", "123", base_dir=tmp_path) is True


def test_validate_object_type_rejects_unknown():
    assert validate_object_type("aliens", "123") is False


def test_tools_validate_object_type_accepts_standard():
    _validate_object_type("contacts", "123")
    _validate_object_type("deals", "123")


def test_tools_validate_object_type_accepts_custom_from_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.cache.Path.home", lambda: tmp_path)
    cache = SchemaCache("123")
    cache.set("pets", {"results": [{"name": "pet_name", "type": "string"}]})

    _validate_object_type("pets", "123")


def test_tools_validate_object_type_rejects_unknown():
    with pytest.raises(ValueError) as exc:
        _validate_object_type("aliens", "123")
    assert "aliens" in str(exc.value)


def test_validate_properties_works_with_custom_object(tmp_path):
    cache = SchemaCache("123", base_dir=tmp_path)
    cache.set(
        "pets",
        {"results": [{"name": "pet_name", "type": "string"}, {"name": "age", "type": "number"}]},
    )

    result = validate_properties(
        "pets",
        {"pet_name": "Fido", "age": 3},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is True
    assert result["errors"] == []


def test_routing_fast_path_matches_custom_object(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.orchestrator.Path.home", lambda: tmp_path)
    cache = SchemaCache("123")
    cache.set("pets", {"results": [{"name": "pet_name", "type": "string"}]})

    result = _fast_path_route("find all pets", portal_id="123")
    assert result is not None
    assert "objects" in result


def test_routing_route_request_matches_custom_object(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.orchestrator.Path.home", lambda: tmp_path)
    cache = SchemaCache("123")
    cache.set("pets", {"results": [{"name": "pet_name", "type": "string"}]})

    result = route_request("find all pets", portal_id="123")
    assert "objects" in result


def test_routing_fast_path_without_portal_id_ignores_custom_objects():
    result = _fast_path_route("find all pets")
    assert result is None


def test_objects_agent_prompt_includes_custom_objects(tmp_path, monkeypatch):
    from hubspot_agent.agents.objects import get_objects_agent_prompt

    monkeypatch.setattr("hubspot_agent.cache.Path.home", lambda: tmp_path)
    cache = SchemaCache("123")
    cache.set("pets", {"results": [{"name": "pet_name", "type": "string"}]})

    portal = PortalConfig(portal_id="123", token="test-token")
    prompt = get_objects_agent_prompt(portal)

    assert "pets" in prompt.system_prompt
    assert "custom object" in prompt.system_prompt.lower()
