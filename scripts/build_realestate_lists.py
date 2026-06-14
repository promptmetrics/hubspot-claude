#!/usr/bin/env python3
"""
Build Real Estate CRM Lists in HubSpot portal 148408595.
Implements list segmentation from the architecture doc.
Run with: PYTHONPATH=src .venv/bin/python scripts/build_realestate_lists.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hubspot_agent.config import load_portal_config
from hubspot_agent.client import HubSpotClient

PORTAL_ID = "148408595"

# Object type ID mapping
CONTACTS = "0-1"
COMPANIES = "0-2"
DEALS = "0-3"
TICKETS = "0-5"
LISTINGS = "0-420"
OFFERS = "2-202484492"
SHOWINGS = "2-202484491"
OPEN_HOUSES = "2-202481647"
COMMISSIONS = "2-202481648"


# ---------------------------------------------------------------------------
# Manual lists for segmentation (static memberships)
# ---------------------------------------------------------------------------

MANUAL_LISTS: list[dict[str, Any]] = [
    {"name": "[RE] All Buyers", "objectTypeId": CONTACTS},
    {"name": "[RE] All Sellers", "objectTypeId": CONTACTS},
    {"name": "[RE] Past Clients", "objectTypeId": CONTACTS},
    {"name": "[RE] Sphere of Influence", "objectTypeId": CONTACTS},
    {"name": "[RE] Investors", "objectTypeId": CONTACTS},
    {"name": "[RE] Referral Partners", "objectTypeId": CONTACTS},
    {"name": "[RE] Active Listings", "objectTypeId": LISTINGS},
    {"name": "[RE] Open House Attendees", "objectTypeId": CONTACTS},
    {"name": "[RE] Pending Commissions", "objectTypeId": COMMISSIONS},
    {"name": "[RE] Preferred Vendors", "objectTypeId": COMPANIES},
]

# ---------------------------------------------------------------------------
# Dynamic lists (auto-segmentation)
# ---------------------------------------------------------------------------

DYNAMIC_LISTS: list[dict[str, Any]] = [
    {
        "name": "[RE] Active Buyers — Touring",
        "objectTypeId": CONTACTS,
        "filters": [
            {"property": "lifecyclestage", "op": "IS_ANY_OF", "values": ["opportunity"], "type": "ENUMERATION"},
            {"property": "contact_role", "op": "IS_ANY_OF", "values": ["Buyer"], "type": "ENUMERATION"},
        ],
    },
    {
        "name": "[RE] Hot Leads — 0-30 Days",
        "objectTypeId": CONTACTS,
        "filters": [
            {"property": "timeline_to_buy", "op": "IS_ANY_OF", "values": ["0-30 days"], "type": "ENUMERATION"},
            {"property": "lifecyclestage", "op": "IS_ANY_OF", "values": ["lead", "marketingqualifiedlead", "salesqualifiedlead"], "type": "ENUMERATION"},
        ],
    },
    {
        "name": "[RE] Nurture — 12+ Months",
        "objectTypeId": CONTACTS,
        "filters": [
            {"property": "timeline_to_buy", "op": "IS_ANY_OF", "values": ["12+ months"], "type": "ENUMERATION"},
            {"property": "lifecyclestage", "op": "IS_ANY_OF", "values": ["lead"], "type": "ENUMERATION"},
        ],
    },
    {
        "name": "[RE] Stale Listings — 21+ DOM",
        "objectTypeId": LISTINGS,
        "filters": [
            {"property": "listing_status", "op": "IS_ANY_OF", "values": ["Active"], "type": "ENUMERATION"},
            {"property": "days_on_market", "op": "IS_GREATER_THAN", "value": "21", "type": "NUMBER"},
        ],
    },
    {
        "name": "[RE] Under Contract — Buyer Side",
        "objectTypeId": DEALS,
        "filters": [
            {"property": "dealstage", "op": "IS_ANY_OF", "values": ["undercontract"], "type": "ENUMERATION"},
            {"property": "buyer_side_or_seller_side", "op": "IS_ANY_OF", "values": ["Buyer Side"], "type": "ENUMERATION"},
        ],
    },
    {
        "name": "[RE] Under Contract — Seller Side",
        "objectTypeId": DEALS,
        "filters": [
            {"property": "dealstage", "op": "IS_ANY_OF", "values": ["undercontract"], "type": "ENUMERATION"},
            {"property": "buyer_side_or_seller_side", "op": "IS_ANY_OF", "values": ["Seller Side"], "type": "ENUMERATION"},
        ],
    },
    {
        "name": "[RE] Closed Won — This Quarter",
        "objectTypeId": DEALS,
        "filters": [
            {"property": "dealstage", "op": "IS_ANY_OF", "values": ["closedwon"], "type": "ENUMERATION"},
            {"property": "closedate", "op": "IS_KNOWN", "type": "ALL_PROPERTY"},
        ],
    },
    {
        "name": "[RE] Customers for Anniversary",
        "objectTypeId": CONTACTS,
        "filters": [
            {"property": "lifecyclestage", "op": "IS_ANY_OF", "values": ["customer"], "type": "ENUMERATION"},
            {"property": "anniversary_date", "op": "IS_KNOWN", "type": "ALL_PROPERTY"},
        ],
    },
]


def build_filter_branch(filters: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert simplified filters to HubSpot list filterBranch structure."""
    property_filters = []
    for f in filters:
        op_type = f["type"]
        operator = f["op"]
        prop = f["property"]

        operation: dict[str, Any] = {
            "operationType": op_type,
            "operator": operator,
            "includeObjectsWithNoValueSet": False,
        }

        if op_type == "ALL_PROPERTY":
            pass  # IS_KNOWN has no value
        elif op_type == "TIME_RANGED":
            if operator == "IN_THIS_QUARTER":
                operation["referenceType"] = "CURRENT_QUARTER"
                operation["timeType"] = "QUARTER"
                operation["timezoneSource"] = "PORTAL"
            else:
                operation["value"] = f.get("value")
        elif op_type == "NUMBER":
            operation["value"] = f.get("value")
        elif "value" in f:
            if operator in ("IS_ANY_OF", "IS_NOT_ANY_OF"):
                operation["values"] = [f["value"]] if isinstance(f["value"], str) else f["value"]
            else:
                operation["value"] = f["value"]
        elif "values" in f:
            operation["values"] = f["values"]

        property_filters.append({
            "filterType": "PROPERTY",
            "property": prop,
            "operation": operation,
        })

    return {
        "filterBranchType": "OR",
        "filterBranches": [
            {
                "filterBranchType": "AND",
                "filters": property_filters,
            }
        ],
    }


class ListBuilder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.created: list[str] = []
        self.errors: list[str] = []
        self.existing_names: set[str] = set()

    async def load_existing(self) -> None:
        try:
            resp = await self.client.get("/crm/v3/lists?limit=250", portal_id=self.portal_id)
            for lst in resp.body.get("lists", []):
                self.existing_names.add(lst.get("name", ""))
        except Exception:
            pass

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body)
        return resp.body

    async def create_manual_list(self, lst: dict[str, Any]) -> str | None:
        if lst["name"] in self.existing_names:
            print(f"  Skipped (exists): {lst['name']}")
            return None
        try:
            body = {
                "name": lst["name"],
                "objectTypeId": lst["objectTypeId"],
                "processingType": "MANUAL",
            }
            result = await self._post("/crm/v3/lists", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"List '{lst['name']}': {result.get('message', result)}")
                return None
            list_id = result.get("list", {}).get("listId")
            self.created.append(lst["name"])
            print(f"  Created list: {lst['name']} (id={list_id})")
            return list_id
        except Exception as exc:
            self.errors.append(f"List '{lst['name']}': {exc}")
            return None

    async def create_dynamic_list(self, lst: dict[str, Any]) -> str | None:
        if lst["name"] in self.existing_names:
            print(f"  Skipped (exists): {lst['name']}")
            return None
        try:
            body = {
                "name": lst["name"],
                "objectTypeId": lst["objectTypeId"],
                "processingType": "DYNAMIC",
                "filterBranch": build_filter_branch(lst["filters"]),
            }
            result = await self._post("/crm/v3/lists", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"List '{lst['name']}': {result.get('message', result)}")
                return None
            list_id = result.get("list", {}).get("listId")
            self.created.append(lst["name"])
            print(f"  Created list: {lst['name']} (id={list_id})")
            return list_id
        except Exception as exc:
            self.errors.append(f"List '{lst['name']}': {exc}")
            return None


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"Portal {PORTAL_ID} not configured. Run /hubspot portal token {PORTAL_ID}")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = ListBuilder(client, PORTAL_ID)

    try:
        await builder.load_existing()
        print(f"\n=== Creating {len(MANUAL_LISTS)} manual lists ===")
        for lst in MANUAL_LISTS:
            await builder.create_manual_list(lst)

        print(f"\n=== Creating {len(DYNAMIC_LISTS)} dynamic lists ===")
        for lst in DYNAMIC_LISTS:
            await builder.create_dynamic_list(lst)

        print("\n=== Summary ===")
        print(f"  Lists created: {len(builder.created)}")
        if builder.errors:
            print(f"  Errors: {len(builder.errors)}")
            for err in builder.errors[:20]:
                print(f"    - {err}")
        else:
            print("  No errors!")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
