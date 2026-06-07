#!/usr/bin/env python3
"""
Build Real Estate CRM Lists, Reports, and Dashboards in HubSpot portal 148408595.
Implements Section 10 (Reporting) and supporting lists from the architecture doc.
Run with: PYTHONPATH=src .venv/bin/python scripts/build_realestate_lists_reports.py
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

# ---------------------------------------------------------------------------
# Static lists for segmentation (used by workflows and nurture cadences)
# ---------------------------------------------------------------------------

STATIC_LISTS: list[dict[str, Any]] = [
    {"name": "[RE] All Buyers", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] All Sellers", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] Past Clients", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] Sphere of Influence", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] Investors", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] Referral Partners", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] Active Listings", "objectTypeId": "listings", "processingType": "STATIC"},
    {"name": "[RE] Open House Attendees", "objectTypeId": "contacts", "processingType": "STATIC"},
    {"name": "[RE] Pending Commissions", "objectTypeId": "commissions", "processingType": "STATIC"},
    {"name": "[RE] Preferred Vendors", "objectTypeId": "companies", "processingType": "STATIC"},
]

# ---------------------------------------------------------------------------
# Dynamic lists (auto-segmentation)
# ---------------------------------------------------------------------------

DYNAMIC_LISTS: list[dict[str, Any]] = [
    {
        "name": "[RE] Active Buyers — Touring",
        "objectTypeId": "contacts",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "lifecyclestage", "operator": "IS_EQUAL_TO", "value": "opportunity"},
            {"property": "contact_role", "operator": "CONTAINS_ANY_OF", "value": ["Buyer"]},
        ],
    },
    {
        "name": "[RE] Hot Leads — 0-30 Days",
        "objectTypeId": "contacts",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "timeline_to_buy", "operator": "IS_EQUAL_TO", "value": "0-30 days"},
            {"property": "lifecyclestage", "operator": "IS_ANY_OF", "value": ["lead", "marketingqualifiedlead", "salesqualifiedlead"]},
        ],
    },
    {
        "name": "[RE] Nurture — 12+ Months",
        "objectTypeId": "contacts",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "timeline_to_buy", "operator": "IS_EQUAL_TO", "value": "12+ months"},
            {"property": "lifecyclestage", "operator": "IS_EQUAL_TO", "value": "lead"},
        ],
    },
    {
        "name": "[RE] Stale Listings — 21+ DOM",
        "objectTypeId": "listings",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "listing_status", "operator": "IS_EQUAL_TO", "value": "Active"},
            {"property": "days_on_market", "operator": "IS_GREATER_THAN", "value": "21"},
        ],
    },
    {
        "name": "[RE] Under Contract — Buyer Side",
        "objectTypeId": "deals",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "undercontract"},
            {"property": "buyer_side_or_seller_side", "operator": "IS_EQUAL_TO", "value": "Buyer Side"},
        ],
    },
    {
        "name": "[RE] Under Contract — Seller Side",
        "objectTypeId": "deals",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "undercontract"},
            {"property": "buyer_side_or_seller_side", "operator": "IS_EQUAL_TO", "value": "Seller Side"},
        ],
    },
    {
        "name": "[RE] Closed Won — This Quarter",
        "objectTypeId": "deals",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "closedwon"},
            {"property": "closedate", "operator": "IN_THIS_QUARTER"},
        ],
    },
    {
        "name": "[RE] Customers for Anniversary",
        "objectTypeId": "contacts",
        "processingType": "DYNAMIC",
        "filters": [
            {"property": "lifecyclestage", "operator": "IS_EQUAL_TO", "value": "customer"},
            {"property": "anniversary_date", "operator": "IS_KNOWN"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Reports (Section 10 dashboards)
# ---------------------------------------------------------------------------

REPORTS: list[dict[str, Any]] = [
    # Pipeline Health Dashboard
    {
        "name": "[RE] Weighted Pipeline by Stage",
        "data_source": "deals",
        "metrics": ["amount", "dealstage"],
        "filters": [{"property": "dealstage", "operator": "IS_NOT_EQUAL_TO", "value": "closedlost"}],
        "group_by": ["dealstage", "pipeline"],
        "visualization": "funnel",
        "dashboard": "Pipeline Health",
    },
    {
        "name": "[RE] Projected Close (Next 90 Days)",
        "data_source": "deals",
        "metrics": ["amount", "closedate"],
        "filters": [{"property": "closedate", "operator": "IN_NEXT_X_DAYS", "value": "90"}],
        "group_by": ["closedate"],
        "visualization": "line",
        "dashboard": "Pipeline Health",
    },
    {
        "name": "[RE] Reason Lost (Trailing 90 Days)",
        "data_source": "deals",
        "metrics": ["reason_lost"],
        "filters": [{"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "closedlost"}],
        "group_by": ["reason_lost"],
        "visualization": "pie",
        "dashboard": "Pipeline Health",
    },
    # Listing Performance Dashboard
    {
        "name": "[RE] Median DOM by Neighborhood",
        "data_source": "listings",
        "metrics": ["days_on_market", "subdivision"],
        "filters": [{"property": "listing_status", "operator": "IS_ANY_OF", "value": ["Active", "Sold"]}],
        "group_by": ["subdivision"],
        "visualization": "bar",
        "dashboard": "Listing Performance",
    },
    {
        "name": "[RE] List-to-Sale Price Ratio",
        "data_source": "deals",
        "metrics": ["list_price", "amount"],
        "filters": [{"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "closedwon"}],
        "group_by": ["buyer_side_or_seller_side"],
        "visualization": "bar",
        "dashboard": "Listing Performance",
    },
    {
        "name": "[RE] Showings per Listing",
        "data_source": "listings",
        "metrics": ["total_showings_count", "mls_number"],
        "filters": [],
        "group_by": ["listing_agent_contact_id"],
        "visualization": "bar",
        "dashboard": "Listing Performance",
    },
    # Lead Source ROI Dashboard
    {
        "name": "[RE] Leads by Source Detail",
        "data_source": "contacts",
        "metrics": ["source_detail"],
        "filters": [],
        "group_by": ["source_detail"],
        "visualization": "bar",
        "dashboard": "Lead Source ROI",
    },
    {
        "name": "[RE] Conversion Rate by Source",
        "data_source": "contacts",
        "metrics": ["source_detail", "lifecyclestage"],
        "filters": [],
        "group_by": ["source_detail", "lifecyclestage"],
        "visualization": "stacked_bar",
        "dashboard": "Lead Source ROI",
    },
    # Agent Performance Dashboard
    {
        "name": "[RE] Agent Pipeline Value",
        "data_source": "deals",
        "metrics": ["amount"],
        "filters": [{"property": "dealstage", "operator": "IS_NOT_EQUAL_TO", "value": "closedlost"}],
        "group_by": ["hubspot_owner_id"],
        "visualization": "bar",
        "dashboard": "Agent Performance",
    },
    {
        "name": "[RE] Agent Closed YTD Revenue",
        "data_source": "deals",
        "metrics": ["commission_total"],
        "filters": [
            {"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "closedwon"},
            {"property": "closedate", "operator": "IN_THIS_YEAR"},
        ],
        "group_by": ["hubspot_owner_id"],
        "visualization": "bar",
        "dashboard": "Agent Performance",
    },
    # Service / Quality Dashboard
    {
        "name": "[RE] Open Tickets by Category",
        "data_source": "tickets",
        "metrics": ["ticket_category"],
        "filters": [{"property": "hs_ticket_priority", "operator": "IS_ANY_OF", "value": ["HIGH", "MEDIUM", "LOW"]}],
        "group_by": ["ticket_category"],
        "visualization": "pie",
        "dashboard": "Service Quality",
    },
    {
        "name": "[RE] Client Satisfaction Rating",
        "data_source": "tickets",
        "metrics": ["client_satisfaction_rating"],
        "filters": [{"property": "client_satisfaction_rating", "operator": "IS_KNOWN"}],
        "group_by": ["client_satisfaction_rating"],
        "visualization": "bar",
        "dashboard": "Service Quality",
    },
    # Referral Engine Dashboard
    {
        "name": "[RE] Top Referral Sources by GCI",
        "data_source": "deals",
        "metrics": ["commission_total"],
        "filters": [{"property": "dealstage", "operator": "IS_EQUAL_TO", "value": "closedwon"}],
        "group_by": ["referred_by_contact_id"],
        "visualization": "bar",
        "dashboard": "Referral Engine",
    },
    {
        "name": "[RE] Customers vs Evangelists",
        "data_source": "contacts",
        "metrics": ["lifecyclestage"],
        "filters": [{"property": "lifecyclestage", "operator": "IS_ANY_OF", "value": ["customer", "evangelist"]}],
        "group_by": ["lifecyclestage"],
        "visualization": "donut",
        "dashboard": "Referral Engine",
    },
]

DASHBOARDS: list[dict[str, Any]] = [
    {"name": "[RE] Pipeline Health"},
    {"name": "[RE] Listing Performance"},
    {"name": "[RE] Lead Source ROI"},
    {"name": "[RE] Agent Performance"},
    {"name": "[RE] Service Quality"},
    {"name": "[RE] Referral Engine"},
]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class ListReportBuilder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.created_lists: list[str] = []
        self.created_reports: list[str] = []
        self.created_dashboards: list[str] = []
        self.errors: list[str] = []
        self.dashboard_map: dict[str, str] = {}
        self.report_map: dict[str, str] = {}

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body)
        return resp.body

    async def _get(self, path: str) -> dict[str, Any]:
        resp = await self.client.get(path, portal_id=self.portal_id)
        return resp.body

    async def create_list(self, lst: dict[str, Any]) -> str | None:
        try:
            body = {
                "name": lst["name"],
                "objectTypeId": lst["objectTypeId"],
                "processingType": lst["processingType"],
            }
            if lst.get("filters"):
                body["filters"] = lst["filters"]
            result = await self._post("/crm/v3/lists", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"List '{lst['name']}': {result.get('message', result)}")
                return None
            list_id = result.get("id")
            self.created_lists.append(lst["name"])
            print(f"  Created list: {lst['name']} (id={list_id})")
            return list_id
        except Exception as exc:
            self.errors.append(f"List '{lst['name']}': {exc}")
            return None

    async def create_report(self, report: dict[str, Any]) -> str | None:
        try:
            body = {
                "name": report["name"],
                "dataSource": report["data_source"],
                "metrics": report["metrics"],
                "filters": report.get("filters", []),
                "groupBy": report.get("group_by", []),
                "visualization": report.get("visualization", "table"),
            }
            result = await self._post("/analytics/v2/reports", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"Report '{report['name']}': {result.get('message', result)}")
                return None
            report_id = result.get("id")
            self.created_reports.append(report["name"])
            self.report_map[report["name"]] = report_id
            print(f"  Created report: {report['name']} (id={report_id})")
            return report_id
        except Exception as exc:
            self.errors.append(f"Report '{report['name']}': {exc}")
            return None

    async def create_dashboard(self, dashboard: dict[str, Any]) -> str | None:
        try:
            # Collect report IDs that belong to this dashboard
            report_ids = [
                self.report_map[r["name"]]
                for r in REPORTS
                if r.get("dashboard") == dashboard["name"] and r["name"] in self.report_map
            ]
            body = {"name": dashboard["name"], "reportIds": report_ids}
            result = await self._post("/analytics/v2/dashboards", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"Dashboard '{dashboard['name']}': {result.get('message', result)}")
                return None
            dash_id = result.get("id")
            self.created_dashboards.append(dashboard["name"])
            self.dashboard_map[dashboard["name"]] = dash_id
            print(f"  Created dashboard: {dashboard['name']} (id={dash_id}, {len(report_ids)} reports)")
            return dash_id
        except Exception as exc:
            self.errors.append(f"Dashboard '{dashboard['name']}': {exc}")
            return None


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"Portal {PORTAL_ID} not configured. Run /hubspot portal token {PORTAL_ID}")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = ListReportBuilder(client, PORTAL_ID)

    try:
        # 1. Static lists
        print(f"\n=== Creating {len(STATIC_LISTS)} static lists ===")
        for lst in STATIC_LISTS:
            await builder.create_list(lst)

        # 2. Dynamic lists
        print(f"\n=== Creating {len(DYNAMIC_LISTS)} dynamic lists ===")
        for lst in DYNAMIC_LISTS:
            await builder.create_list(lst)

        # 3. Reports
        print(f"\n=== Creating {len(REPORTS)} reports ===")
        for report in REPORTS:
            await builder.create_report(report)

        # 4. Dashboards
        print(f"\n=== Creating {len(DASHBOARDS)} dashboards ===")
        for dashboard in DASHBOARDS:
            await builder.create_dashboard(dashboard)

        print("\n=== Summary ===")
        print(f"  Lists created: {len(builder.created_lists)}")
        print(f"  Reports created: {len(builder.created_reports)}")
        print(f"  Dashboards created: {len(builder.created_dashboards)}")
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
