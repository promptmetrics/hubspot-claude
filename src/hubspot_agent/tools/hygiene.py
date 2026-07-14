from __future__ import annotations

from typing import Any

from hubspot_agent.client import HubSpotClient
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError
from hubspot_agent.tools import tool
from hubspot_agent.tools.objects import _validate_object_type


_BATCH_SIZE = 100
# HubSpot /search caps a single page at 100 results; duplicate detection must
# page through all matches (bug 3) instead of inspecting only the first page.
_SEARCH_PAGE_SIZE = 100
# Cap on total records scanned so a huge portal can't exhaust the rate budget;
# a search reaching this cap reports ``truncated: true`` rather than silently
# looking duplicate-free past the cap.
_MAX_SCAN_RECORDS = 2000


@tool(name="hubspot_find_duplicates", description="Find duplicate HubSpot contacts by email, phone, or domain.")
async def hubspot_find_duplicates(
    object_type: str,
    search_field: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type, portal_id)
    try:
        # Bug 3: the search body previously omitted ``properties``, so HubSpot
        # returned records with an empty properties map — phone/domain values
        # never came back (email only worked because it's a default-returned
        # property) and the grouping step saw "" for every record → 0 groups.
        # Request the search field explicitly, plus the normalized phone field
        # when searching by phone (HubSpot stores the searchable normalized
        # value there; ``phone`` itself is the display value we group on).
        properties = [search_field]
        if search_field == "phone":
            properties.append("hs_searchable_calculated_phone_number")
        query: dict[str, Any] = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": search_field,
                            "operator": "HAS_PROPERTY",
                        }
                    ]
                }
            ],
            "properties": properties,
            "limit": _SEARCH_PAGE_SIZE,
        }

        # Paginate via ``paging.next.after`` — a single search page returns at
        # most 100 records, so a portal with more matching records than that
        # would silently look duplicate-free past the first page.  Cap the total
        # scanned so a giant portal can't exhaust the rate budget, and report
        # the cap so a silent truncation is visible rather than a false "no
        # duplicates".
        seen: dict[str, list[dict[str, Any]]] = {}
        records_scanned = 0
        truncated = False
        after: str | None = None
        while records_scanned < _MAX_SCAN_RECORDS:
            page_query = dict(query)
            if after is not None:
                page_query["after"] = after
            resp = await client.post(
                f"/crm/v3/objects/{object_type}/search",
                portal_id=portal_id,
                body=page_query,
                expected_scopes=[f"crm.objects.{object_type}.read"],
            )
            body = resp.body
            results = body.get("results", [])
            for record in results:
                val = record.get("properties", {}).get(search_field, "").lower().strip()
                if val:
                    seen.setdefault(val, []).append(record)
            records_scanned += len(results)
            next_after = (body.get("paging") or {}).get("next", {}).get("after")
            if not next_after or not results:
                break
            after = next_after
        else:
            truncated = True

        duplicates = {k: v for k, v in seen.items() if len(v) > 1}
        return {
            "object_type": object_type,
            "search_field": search_field,
            "duplicate_groups": duplicates,
            "total_duplicates": sum(len(v) for v in duplicates.values()),
            "records_scanned": records_scanned,
            "truncated": truncated,
        }
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_find_duplicates"}


@tool(name="hubspot_merge_objects", description="Merge two HubSpot object records of the same object type.")
async def hubspot_merge_objects(
    primary_object_id: str,
    object_id_to_merge: str,
    client: HubSpotClient,
    portal_id: str,
    object_type: str = "contacts",
) -> dict[str, Any]:
    _validate_object_type(object_type, portal_id)
    try:
        resp = await client.post(
            f"/crm/v3/objects/{object_type}/merge",
            portal_id=portal_id,
            body={
                "primaryObjectId": primary_object_id,
                "objectIdToMerge": object_id_to_merge,
            },
            # Matches the registry's write+delete classification for merge —
            # the secondary record is destroyed, so a 403 should name both.
            expected_scopes=[
                f"crm.objects.{object_type}.write",
                f"crm.objects.{object_type}.delete",
            ],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_merge_objects"}


@tool(name="hubspot_bulk_update_objects", description="Bulk update HubSpot objects.")
async def hubspot_bulk_update_objects(
    object_type: str,
    records: list[dict[str, Any]],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type, portal_id)
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    succeeded = 0

    for i in range(0, len(records), _BATCH_SIZE):
        chunk = records[i : i + _BATCH_SIZE]
        try:
            resp = await client.post(
                f"/crm/v3/objects/{object_type}/batch/update",
                portal_id=portal_id,
                body={"inputs": chunk},
                expected_scopes=[f"crm.objects.{object_type}.write"],
            )
            body = resp.body
            results.extend(body.get("results", []))
            errors.extend(body.get("errors", []))
            succeeded += len(body.get("results", []))
        except (HubSpotError, RateLimitError, ScopeError) as exc:
            errors.append({"message": str(exc), "category": "BATCH_UPDATE"})

    return {
        "succeeded": succeeded,
        "failed": len(errors),
        "total": len(records),
        "results": results,
        "errors": errors,
    }


@tool(name="hubspot_preview_segment", description="Preview a segment of HubSpot objects matching filters.")
async def hubspot_preview_segment(
    object_type: str,
    query: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type, portal_id)
    try:
        resp = await client.post(
            f"/crm/v3/objects/{object_type}/search",
            portal_id=portal_id,
            body=query,
            expected_scopes=[f"crm.objects.{object_type}.read"],
        )
        body = resp.body
        return {
            "object_type": object_type,
            "total": body.get("total", 0),
            "results": body.get("results", []),
            "preview": True,
        }
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_preview_segment"}
