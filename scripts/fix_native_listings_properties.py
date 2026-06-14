#!/usr/bin/env python3
"""
Add missing custom properties to HubSpot's NATIVE listings object.
The previous build script incorrectly tried to create a custom listings object;
HubSpot already has a native one. This script adds the architecture-specific
properties that the native object lacks.
Run with: PYTHONPATH=src .venv/bin/python scripts/fix_native_listings_properties.py
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

# Custom properties to add to the NATIVE listings object
LISTING_CUSTOM_PROPERTIES: list[dict[str, Any]] = [
    {"name": "mls_number", "label": "MLS Number", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "unit_number", "label": "Unit Number", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "county", "label": "County", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "subdivision", "label": "Subdivision", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "parcel_id", "label": "Parcel ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "latitude", "label": "Latitude", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "longitude", "label": "Longitude", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "google_place_id", "label": "Google Place ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "listing_status", "label": "Listing Status", "type": "enumeration", "fieldType": "select", "groupName": "listing_information", "options": [
        {"label": "Coming Soon", "value": "Coming Soon", "displayOrder": 0},
        {"label": "Active", "value": "Active", "displayOrder": 1},
        {"label": "Active Under Contract / Backup", "value": "Active Under Contract / Backup", "displayOrder": 2},
        {"label": "Pending", "value": "Pending", "displayOrder": 3},
        {"label": "Sold", "value": "Sold", "displayOrder": 4},
        {"label": "Withdrawn", "value": "Withdrawn", "displayOrder": 5},
        {"label": "Expired", "value": "Expired", "displayOrder": 6},
        {"label": "Off-Market — Pre-Listing", "value": "Off-Market - Pre-Listing", "displayOrder": 7},
        {"label": "Off-Market — Investor", "value": "Off-Market - Investor", "displayOrder": 8},
        {"label": "Cancelled", "value": "Cancelled", "displayOrder": 9},
    ]},
    {"name": "original_list_price", "label": "Original List Price", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "list_date", "label": "List Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "expiration_date", "label": "Expiration Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "withdrawal_date", "label": "Withdrawal Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "sold_date", "label": "Sold Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "sold_price", "label": "Sold Price", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "days_on_market", "label": "Days on Market", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "price_per_square_foot", "label": "Price per Square Foot", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "listing_agent_contact_id", "label": "Listing Agent Contact ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "co_listing_agent_contact_id", "label": "Co-Listing Agent Contact ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "listing_brokerage_company_id", "label": "Listing Brokerage Company ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "listing_commission_offered_buyer_side", "label": "Listing Commission Offered Buyer Side", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "listing_commission_offered_seller_side", "label": "Listing Commission Offered Seller Side", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "seller_contact_id", "label": "Seller Contact ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "professional_photos_url", "label": "Professional Photos URL", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "virtual_tour_url", "label": "Virtual Tour URL", "type": "string", "fieldType": "text", "groupName": "listing_information"},
    {"name": "mls_remarks_public", "label": "MLS Remarks Public", "type": "string", "fieldType": "textarea", "groupName": "listing_information"},
    {"name": "mls_remarks_agent", "label": "MLS Remarks Agent", "type": "string", "fieldType": "textarea", "groupName": "listing_information"},
    {"name": "marketing_started_date", "label": "Marketing Started Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "signage_installed_date", "label": "Signage Installed Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "total_showings_count", "label": "Total Showings Count", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "total_offers_count", "label": "Total Offers Count", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "last_showing_date", "label": "Last Showing Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "total_open_houses_count", "label": "Total Open Houses Count", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "last_price_change_date", "label": "Last Price Change Date", "type": "date", "fieldType": "date", "groupName": "listing_information"},
    {"name": "price_changes_count", "label": "Price Changes Count", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "is_off_market", "label": "Is Off Market", "type": "bool", "fieldType": "booleancheckbox", "groupName": "listing_information", "options": [
        {"label": "Yes", "value": "true"},
        {"label": "No", "value": "false"},
    ]},
    {"name": "off_market_reason", "label": "Off Market Reason", "type": "enumeration", "fieldType": "select", "groupName": "listing_information", "options": [
        {"label": "Pre-Listing", "value": "Pre-Listing", "displayOrder": 0},
        {"label": "Pocket Listing", "value": "Pocket Listing", "displayOrder": 1},
        {"label": "Investor Hold", "value": "Investor Hold", "displayOrder": 2},
        {"label": "FSBO Watch", "value": "FSBO Watch", "displayOrder": 3},
        {"label": "Foreclosure Watch", "value": "Foreclosure Watch", "displayOrder": 4},
        {"label": "Probate Watch", "value": "Probate Watch", "displayOrder": 5},
        {"label": "Distressed", "value": "Distressed", "displayOrder": 6},
        {"label": "Expired Listing — Working Owner", "value": "Expired Listing - Working Owner", "displayOrder": 7},
    ]},
    {"name": "estimated_arv", "label": "Estimated ARV", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "estimated_rehab_cost", "label": "Estimated Rehab Cost", "type": "number", "fieldType": "number", "groupName": "listing_information"},
    {"name": "current_owner_contact_id", "label": "Current Owner Contact ID", "type": "string", "fieldType": "text", "groupName": "listing_information"},
]


class PropertyBuilder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.created: list[str] = []
        self.errors: list[str] = []

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body)
        return resp.body

    async def create_custom_property(self, object_type: str, prop: dict[str, Any]) -> None:
        try:
            body = {
                "name": prop["name"],
                "label": prop["label"],
                "type": prop["type"],
                "fieldType": prop["fieldType"],
                "groupName": prop.get("groupName", "contactinformation"),
            }
            if prop.get("options"):
                body["options"] = prop["options"]
            result = await self._post(f"/crm/v3/properties/{object_type}", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"Property '{prop['name']}': {result.get('message', result)}")
            else:
                self.created.append(prop["name"])
                print(f"  Created property: {prop['name']}")
        except Exception as exc:
            self.errors.append(f"Property '{prop['name']}': {exc}")


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"Portal {PORTAL_ID} not configured. Run /hubspot portal token {PORTAL_ID}")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = PropertyBuilder(client, PORTAL_ID)

    try:
        print(f"\n=== Creating {len(LISTING_CUSTOM_PROPERTIES)} custom properties on native listings ===")
        for prop in LISTING_CUSTOM_PROPERTIES:
            await builder.create_custom_property("listings", prop)

        print("\n=== Summary ===")
        print(f"  Created: {len(builder.created)} properties")
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
