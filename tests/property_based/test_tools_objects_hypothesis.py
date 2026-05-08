from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hubspot_agent.client import HubSpotClient
from hubspot_agent.tools.objects import (
    hubspot_create_object,
    hubspot_delete_object,
    hubspot_get_object,
    hubspot_search_objects,
    hubspot_update_object,
)


def _mock_client(response_body: dict[str, Any] | None = None) -> HubSpotClient:
    client = AsyncMock(spec=HubSpotClient)
    if response_body is not None:
        mock_resp = AsyncMock()
        mock_resp.body = response_body
        client.get.return_value = mock_resp
        client.post.return_value = mock_resp
        client.patch.return_value = mock_resp
        client.delete.return_value = mock_resp
    return client


_VALID_OBJECT_TYPES = ["contacts", "companies", "deals", "tickets"]


class TestGetObject:
    @pytest.mark.asyncio
    @given(
        object_id=st.text(min_size=1, max_size=64),
        object_type=st.sampled_from(_VALID_OBJECT_TYPES),
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_crash_with_valid_types(self, object_id: str, object_type: str):
        client = _mock_client({"id": object_id})
        result = await hubspot_get_object(
            object_id=object_id,
            object_type=object_type,
            client=client,
            portal_id="123",
        )
        assert isinstance(result, dict)
        if "error" in result:
            assert "tool" in result

    @pytest.mark.asyncio
    @given(
        object_id=st.text(min_size=1, max_size=64),
        object_type=st.text(min_size=1, max_size=32),
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_crash_with_any_type(self, object_id: str, object_type: str):
        client = _mock_client({"id": object_id})
        try:
            result = await hubspot_get_object(
                object_id=object_id,
                object_type=object_type,
                client=client,
                portal_id="123",
            )
            assert isinstance(result, dict)
            if "error" in result:
                assert "tool" in result
        except ValueError:
            pass  # Expected for invalid object types


class TestSearchObjects:
    @pytest.mark.asyncio
    @given(
        object_type=st.sampled_from(_VALID_OBJECT_TYPES),
        query=st.dictionaries(
            st.text(min_size=1, max_size=32),
            st.one_of(st.text(), st.integers(), st.booleans(), st.lists(st.text())),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_crash(self, object_type: str, query: dict[str, Any]):
        client = _mock_client({"results": []})
        result = await hubspot_search_objects(
            object_type=object_type,
            query=query,
            client=client,
            portal_id="123",
        )
        assert isinstance(result, dict)
        if "error" in result:
            assert "tool" in result


class TestCreateObject:
    @pytest.mark.asyncio
    @given(
        object_type=st.sampled_from(_VALID_OBJECT_TYPES),
        properties=st.dictionaries(
            st.text(min_size=1, max_size=32),
            st.one_of(st.text(), st.integers(), st.booleans()),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_crash(self, object_type: str, properties: dict[str, Any]):
        client = _mock_client({"id": "new_id"})
        result = await hubspot_create_object(
            object_type=object_type,
            properties=properties,
            client=client,
            portal_id="123",
        )
        assert isinstance(result, dict)
        if "error" in result:
            assert "tool" in result


class TestUpdateObject:
    @pytest.mark.asyncio
    @given(
        object_type=st.sampled_from(_VALID_OBJECT_TYPES),
        object_id=st.text(min_size=1, max_size=64),
        properties=st.dictionaries(
            st.text(min_size=1, max_size=32),
            st.one_of(st.text(), st.integers(), st.booleans()),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_crash(self, object_type: str, object_id: str, properties: dict[str, Any]):
        client = _mock_client({"id": object_id})
        result = await hubspot_update_object(
            object_type=object_type,
            object_id=object_id,
            properties=properties,
            client=client,
            portal_id="123",
        )
        assert isinstance(result, dict)
        if "error" in result:
            assert "tool" in result


class TestDeleteObject:
    @pytest.mark.asyncio
    @given(
        object_type=st.sampled_from(_VALID_OBJECT_TYPES),
        object_id=st.text(min_size=1, max_size=64),
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_crash(self, object_type: str, object_id: str):
        client = _mock_client({})
        result = await hubspot_delete_object(
            object_type=object_type,
            object_id=object_id,
            client=client,
            portal_id="123",
        )
        assert isinstance(result, dict)
        if "error" in result:
            assert "tool" in result
