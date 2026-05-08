from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hubspot_agent.config import PortalConfig
from hubspot_agent.errors import HubSpotError
from hubspot_agent.reflection import (
    ReflectionResult,
    _normalize_value,
    _values_match,
    reflect_on_write,
)


@pytest.fixture
def portal_config() -> PortalConfig:
    return PortalConfig(portal_id="123", token="fake-token")


class TestNormalizeValue:
    def test_boolean_strings(self):
        assert _normalize_value("true") is True
        assert _normalize_value("yes") is True
        assert _normalize_value("1") is True
        assert _normalize_value("false") is False
        assert _normalize_value("no") is False
        assert _normalize_value("0") is False

    def test_numeric_strings(self):
        assert _normalize_value("42") == 42
        assert _normalize_value("3.14") == 3.14

    def test_json_string_parsing(self):
        assert _normalize_value('{"a": 1}') == {"a": 1}
        assert _normalize_value('[1, 2]') == [1, 2]

    def test_plain_string_stripped(self):
        assert _normalize_value("  hello  ") == "hello"

    def test_passthrough(self):
        assert _normalize_value(42) == 42
        assert _normalize_value([1, 2]) == [1, 2]


class TestValuesMatch:
    def test_exact_match(self):
        assert _values_match("hello", "hello")
        assert _values_match(42, 42)
        assert _values_match(True, True)

    def test_string_number_coercion(self):
        assert _values_match("42", 42)
        assert _values_match(42, "42")
        assert _values_match("3.14", 3.14)

    def test_string_bool_coercion(self):
        assert _values_match("true", True)
        assert _values_match("false", False)

    def test_dict_match(self):
        assert _values_match({"a": 1, "b": 2}, {"b": 2, "a": 1})

    def test_dict_mismatch(self):
        assert not _values_match({"a": 1}, {"a": 2})
        assert not _values_match({"a": 1}, {"a": 1, "b": 2})

    def test_list_match(self):
        assert _values_match([1, 2, 3], [1, 2, 3])

    def test_list_mismatch(self):
        assert not _values_match([1, 2], [1, 3])
        assert not _values_match([1, 2], [1, 2, 3])


@pytest.mark.asyncio
async def test_reflect_on_write_success(portal_config):
    mock_body = {"properties": {"email": "test@example.com", "firstname": "Alice"}}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=AsyncMock(body=mock_body))

    result = await reflect_on_write(
        portal_config,
        object_type="contacts",
        object_id="101",
        expected_properties={"email": "test@example.com", "firstname": "Alice"},
        client=mock_client,
    )

    assert result.verified is True
    assert result.mismatches == []
    assert result.missing_fields == []
    assert result.object_id == "101"
    assert result.object_type == "contacts"
    mock_client.get.assert_awaited_once_with(
        "/crm/v3/objects/contacts/101",
        portal_id="123",
    )


@pytest.mark.asyncio
async def test_reflect_on_write_mismatch(portal_config):
    mock_body = {"properties": {"email": "test@example.com", "firstname": "Bob"}}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=AsyncMock(body=mock_body))

    result = await reflect_on_write(
        portal_config,
        object_type="contacts",
        object_id="102",
        expected_properties={"email": "test@example.com", "firstname": "Alice"},
        client=mock_client,
    )

    assert result.verified is False
    assert len(result.mismatches) == 1
    assert result.mismatches[0]["field"] == "firstname"
    assert result.mismatches[0]["expected"] == "Alice"
    assert result.mismatches[0]["actual"] == "Bob"


@pytest.mark.asyncio
async def test_reflect_on_write_missing_field(portal_config):
    mock_body = {"properties": {"email": "test@example.com"}}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=AsyncMock(body=mock_body))

    result = await reflect_on_write(
        portal_config,
        object_type="contacts",
        object_id="103",
        expected_properties={"email": "test@example.com", "lastname": "Smith"},
        client=mock_client,
    )

    assert result.verified is False
    assert result.missing_fields == ["lastname"]


@pytest.mark.asyncio
async def test_reflect_on_write_type_coercion(portal_config):
    mock_body = {"properties": {"email": "test@example.com", "age": "30"}}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=AsyncMock(body=mock_body))

    result = await reflect_on_write(
        portal_config,
        object_type="contacts",
        object_id="104",
        expected_properties={"email": "test@example.com", "age": 30},
        client=mock_client,
    )

    assert result.verified is True
    assert result.mismatches == []


@pytest.mark.asyncio
async def test_reflect_on_write_hubspot_error(portal_config):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=HubSpotError("Not found", status_code=404))

    result = await reflect_on_write(
        portal_config,
        object_type="contacts",
        object_id="999",
        expected_properties={"email": "test@example.com"},
        client=mock_client,
    )

    assert result.verified is False
    assert result.mismatches[0]["field"] == "__fetch__"
    assert "Not found" in result.mismatches[0]["error"]


@pytest.mark.asyncio
async def test_reflect_on_write_creates_client(portal_config):
    mock_body = {"properties": {"email": "test@example.com"}}

    with patch("hubspot_agent.reflection.HubSpotClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=AsyncMock(body=mock_body))
        MockClient.return_value = instance

        result = await reflect_on_write(
            portal_config,
            object_type="contacts",
            object_id="105",
            expected_properties={"email": "test@example.com"},
        )

        assert result.verified is True
        instance.close.assert_awaited_once()


def test_reflection_result_to_dict():
    result = ReflectionResult(
        object_id="1",
        object_type="contacts",
        verified=True,
        mismatches=[],
        missing_fields=[],
        fetched_properties={"email": "a@b.com"},
    )
    d = result.to_dict()
    assert d["object_id"] == "1"
    assert d["object_type"] == "contacts"
    assert d["verified"] is True
    assert d["fetched_properties"] == {"email": "a@b.com"}
    assert "timestamp" in d
