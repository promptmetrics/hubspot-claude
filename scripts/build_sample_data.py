#!/usr/bin/env python3
"""
Create sample records across all object types in HubSpot portal 148408595
for team validation. Uses only properties confirmed to exist with valid enum values.
Run with: PYTHONPATH=src .venv/bin/python scripts/build_sample_data.py
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

LISTINGS = "0-420"
OFFERS = "2-202484492"
SHOWINGS = "2-202484491"
OPEN_HOUSES = "2-202481647"
COMMISSIONS = "2-202481648"

BUYER_PIPELINE = "3802390752"
SELLER_PIPELINE = "3802299622"
INVESTOR_PIPELINE = "3802390753"

BS_ACTIVE = "5331537139"
BS_OFFER = "5331537140"
BS_CLOSED_WON = "5331538106"

SS_LISTING = "5331599564"
SS_CLOSED_WON = "5331599569"

TICKET_PIPELINE = "0"
TK_NEW = "1"
TK_WAITING = "3"
TK_CLOSED = "4"


SAMPLE_CONTACTS: list[dict[str, Any]] = [
    {
        "email": "sarah.johnson@example.com",
        "firstname": "Sarah",
        "lastname": "Johnson",
        "phone": "555-0101",
        "lifecyclestage": "opportunity",
        "contact_role": "Buyer",
        "buyer_qualification_status": "Pre-Approved",
        "bedrooms_min": "3",
        "bathrooms_min": "2",
        "city": "Springfield",
        "country": "United States",
        "company": "Acme Corp",
        "company_size": "50-200",
        "current_home_address": "123 Oak Street, Springfield, IL",
        "current_home_estimated_value": "320000",
        "current_home_owned": "true",
    },
    {
        "email": "michael.chen@example.com",
        "firstname": "Michael",
        "lastname": "Chen",
        "phone": "555-0102",
        "lifecyclestage": "opportunity",
        "contact_role": "Buyer",
        "buyer_qualification_status": "Pre-Qualified",
        "bedrooms_min": "4",
        "bathrooms_min": "3",
        "city": "Springfield",
        "country": "United States",
        "company": "TechSoft Inc",
        "company_size": "200-500",
    },
    {
        "email": "james.anderson@example.com",
        "firstname": "James",
        "lastname": "Anderson",
        "phone": "555-0103",
        "lifecyclestage": "opportunity",
        "contact_role": "Seller",
        "city": "Springfield",
        "country": "United States",
        "company": "Anderson Family",
        "current_home_address": "123 Oak Street, Springfield, IL",
        "current_home_estimated_value": "450000",
        "current_home_owned": "true",
    },
    {
        "email": "emily.davis@example.com",
        "firstname": "Emily",
        "lastname": "Davis",
        "phone": "555-0104",
        "lifecyclestage": "customer",
        "contact_role": "Past Client",
        "city": "Springfield",
        "country": "United States",
        "anniversary_date": "2025-08-15",
        "nps_score": "9",
        "client_satisfaction_rating": "5",
    },
    {
        "email": "david.rodriguez@example.com",
        "firstname": "David",
        "lastname": "Rodriguez",
        "phone": "555-0105",
        "lifecyclestage": "lead",
        "contact_role": "Investor",
        "city": "Springfield",
        "country": "United States",
        "company": "DR Investments LLC",
    },
    {
        "email": "lisa.williams@example.com",
        "firstname": "Lisa",
        "lastname": "Williams",
        "phone": "555-0106",
        "lifecyclestage": "lead",
        "contact_role": "Referral Partner",
        "city": "Springfield",
        "country": "United States",
        "company": "Prime Mortgage Lending",
    },
    {
        "email": "agent.jessica.martinez@premierrealty.com",
        "firstname": "Jessica",
        "lastname": "Martinez",
        "phone": "555-0107",
        "lifecyclestage": "lead",
        "contact_role": "Internal Agent",
        "city": "Springfield",
        "country": "United States",
        "company": "Premier Realty Group",
    },
    {
        "email": "robert.brown@example.com",
        "firstname": "Robert",
        "lastname": "Brown",
        "phone": "555-0108",
        "lifecyclestage": "lead",
        "contact_role": "Vendor",
        "city": "Springfield",
        "country": "United States",
        "company": "Brown Home Inspections",
    },
]

SAMPLE_COMPANIES: list[dict[str, Any]] = [
    {
        "name": "Premier Realty Group",
        "domain": "premierrealty.com",
        "company_type": "Brokerage (Cooperating)",
        "license_number": "BRK-2024-001",
        "city": "Springfield",
        "country": "United States",
        "phone": "555-0201",
    },
    {
        "name": "Elite Home Staging",
        "domain": "elitehomestaging.com",
        "company_type": "Staging Company",
        "license_number": "VEN-2024-112",
        "insurance_expiry_date": "2026-12-31",
        "city": "Springfield",
        "country": "United States",
        "phone": "555-0202",
    },
]

SAMPLE_LISTINGS: list[dict[str, Any]] = [
    {
        "hs_name": "456 Maple Avenue",
        "hs_address_1": "456 Maple Avenue",
        "hs_address_2": "",
        "hs_city": "Springfield",
        "hs_state_province": "IL",
        "hs_zip": "62701",
        "hs_bedrooms": "3",
        "hs_bathrooms": "2",
        "hs_square_footage": "2100",
        "hs_price": "425000",
        "hs_listing_type": "house",
        "hs_year_built": "2015",
        "mls_number": "MLS-2026-001",
        "unit_number": "",
        "county": "Sangamon",
        "subdivision": "Maple Grove Estates",
        "parcel_id": "14-22-33-444-555",
        "latitude": "39.7817",
        "longitude": "-89.6501",
        "google_place_id": "ChIJ001",
        "listing_status": "Active",
        "original_list_price": "435000",
        "list_date": "2026-04-01",
        "expiration_date": "2026-10-01",
        "days_on_market": "40",
        "price_per_square_foot": "202",
        "listing_commission_offered_buyer_side": "2.5",
        "listing_commission_offered_seller_side": "2.5",
        "professional_photos_url": "https://photos.example.com/001",
        "virtual_tour_url": "https://tour.example.com/001",
        "mls_remarks_public": "Beautiful 3BR/2BA home in sought-after Maple Grove Estates. Updated kitchen, hardwood floors, fenced yard.",
        "mls_remarks_agent": "Motivated seller. Will consider reasonable offers. Pre-inspection completed.",
        "marketing_started_date": "2026-04-01",
        "signage_installed_date": "2026-04-02",
        "total_showings_count": "12",
        "total_offers_count": "2",
        "last_showing_date": "2026-05-08",
        "total_open_houses_count": "3",
        "last_price_change_date": "2026-04-15",
        "price_changes_count": "1",
        "is_off_market": "false",
        "estimated_arv": "450000",
    },
    {
        "hs_name": "789 Lake Shore Drive",
        "hs_address_1": "789 Lake Shore Drive",
        "hs_address_2": "Unit 12B",
        "hs_city": "Springfield",
        "hs_state_province": "IL",
        "hs_zip": "62704",
        "hs_bedrooms": "2",
        "hs_bathrooms": "2",
        "hs_square_footage": "1500",
        "hs_price": "310000",
        "hs_listing_type": "condos_co_ops",
        "hs_year_built": "2010",
        "mls_number": "MLS-2026-002",
        "unit_number": "12B",
        "county": "Sangamon",
        "subdivision": "Lakeside Condos",
        "parcel_id": "14-22-33-444-556",
        "latitude": "39.7921",
        "longitude": "-89.6445",
        "google_place_id": "ChIJ002",
        "listing_status": "Pending",
        "original_list_price": "325000",
        "list_date": "2026-03-15",
        "expiration_date": "2026-09-15",
        "days_on_market": "57",
        "price_per_square_foot": "207",
        "listing_commission_offered_buyer_side": "2.5",
        "listing_commission_offered_seller_side": "2.5",
        "professional_photos_url": "https://photos.example.com/002",
        "virtual_tour_url": "https://tour.example.com/002",
        "mls_remarks_public": "Stunning lake views from this 2BR/2BA condo. Granite counters, stainless appliances, balcony.",
        "mls_remarks_agent": "Offer accepted. Awaiting inspection. Backup offers welcome.",
        "marketing_started_date": "2026-03-15",
        "signage_installed_date": "2026-03-16",
        "total_showings_count": "18",
        "total_offers_count": "3",
        "last_showing_date": "2026-05-01",
        "total_open_houses_count": "2",
        "last_price_change_date": "2026-04-01",
        "price_changes_count": "1",
        "is_off_market": "false",
        "sold_date": "2026-05-15",
        "sold_price": "305000",
    },
]

SAMPLE_DEALS: list[dict[str, Any]] = [
    {
        "dealname": "Sarah Johnson - 456 Maple Ave",
        "pipeline": BUYER_PIPELINE,
        "dealstage": BS_ACTIVE,
        "amount": "425000",
        "closedate": "2026-06-15",
        "buyer_side_or_seller_side": "Buyer Side",
        "dealtype": "newbusiness",
        "financing_type": "Conventional",
        "earnest_money_amount": "5000",
        "contingency_inspection_deadline": "2026-05-20",
        "contingency_appraisal_deadline": "2026-05-25",
        "contingency_financing_deadline": "2026-06-01",
        "commission_total": "12750",
        "commission_percent": "3",
        "mls_number": "MLS-2026-001",
        "list_price": "425000",
    },
    {
        "dealname": "James Anderson - Listing Sale",
        "pipeline": SELLER_PIPELINE,
        "dealstage": SS_LISTING,
        "amount": "475000",
        "closedate": "2026-07-01",
        "buyer_side_or_seller_side": "Seller Side",
        "dealtype": "newbusiness",
        "commission_total": "14250",
        "commission_percent": "3",
        "mls_number": "MLS-2026-001",
        "list_price": "475000",
    },
    {
        "dealname": "David Rodriguez - Investment Property",
        "pipeline": INVESTOR_PIPELINE,
        "dealstage": "5331538108",
        "amount": "350000",
        "closedate": "2026-06-30",
        "buyer_side_or_seller_side": "Buyer Side",
        "dealtype": "newbusiness",
        "financing_type": "Cash",
        "commission_total": "0",
        "commission_percent": "0",
        "mls_number": "MLS-2026-002",
        "list_price": "350000",
    },
]

SAMPLE_TICKETS: list[dict[str, Any]] = [
    {
        "subject": "Inspection report concerns - 456 Maple Ave",
        "content": "Buyer Sarah Johnson has concerns about the roof condition noted in the inspection report. Requesting contractor estimate.",
        "hs_pipeline": TICKET_PIPELINE,
        "hs_pipeline_stage": TK_NEW,
        "hs_ticket_priority": "HIGH",
        "ticket_category": "Inspection Repair",
        "source_type": "EMAIL",
        "nps_score": "8",
        "client_satisfaction_rating": "4",
    },
    {
        "subject": "HOA document delivery delay",
        "content": "Seller James Anderson's HOA is taking longer than expected to deliver resale documents. May delay closing.",
        "hs_pipeline": TICKET_PIPELINE,
        "hs_pipeline_stage": TK_WAITING,
        "hs_ticket_priority": "MEDIUM",
        "ticket_category": "Compliance Issue",
        "source_type": "PHONE",
        "nps_score": "6",
        "client_satisfaction_rating": "3",
    },
]

SAMPLE_SHOWINGS: list[dict[str, Any]] = [
    {
        "showing_date": "2026-05-08T14:00:00Z",
        "showing_type": "Private Showing",
        "showing_status": "Completed",
        "duration_minutes": "45",
        "feedback_received": "true",
        "feedback_rating": "Liked It",
        "feedback_likes": "Loved the kitchen and backyard",
        "feedback_concerns": "Bathroom is small",
        "resulted_in_offer": "true",
        "would_consider_at_lower_price": "true",
        "target_price": "410000",
    },
    {
        "showing_date": "2026-05-01T10:00:00Z",
        "showing_type": "Open House Attendance",
        "showing_status": "Completed",
        "duration_minutes": "180",
        "feedback_received": "false",
        "resulted_in_offer": "false",
    },
]

SAMPLE_OFFERS: list[dict[str, Any]] = [
    {
        "offer_date": "2026-05-09",
        "offer_amount": "415000",
        "offer_type": "Initial",
        "offer_status": "Submitted",
        "down_payment_percent": "10",
        "down_payment_amount": "41500",
        "financing_type": "Conventional",
        "contingency_inspection": "true",
        "contingency_inspection_days": "10",
        "contingency_appraisal": "true",
        "contingency_appraisal_days": "10",
        "contingency_financing": "true",
        "contingency_financing_days": "21",
        "earnest_money_amount": "5000",
        "expiration_date": "2026-05-12",
        "pre_approval_attached": "true",
        "seller_concessions_requested": "3000",
        "closing_date_proposed": "2026-06-15",
    },
]

SAMPLE_COMMISSIONS: list[dict[str, Any]] = [
    {
        "commission_gross": "12750",
        "commission_split_basis": "Gross",
        "brokerage_split_percent": "50",
        "brokerage_amount": "6375",
        "referral_fee_amount": "0",
        "transaction_fee": "495",
        "e_o_insurance_fee": "50",
        "payment_status": "Pending Close",
        "closed_date": "2026-06-15",
        "payment_date": "2026-06-30",
        "disbursement_authorization_signed_date": "2026-06-10",
    },
]

SAMPLE_OPEN_HOUSES: list[dict[str, Any]] = [
    {
        "event_date": "2026-04-12T13:00:00Z",
        "event_type": "Public Open House",
        "event_status": "Completed",
        "duration_minutes": "180",
        "attendee_count": "23",
        "sign_ins_collected": "18",
        "qualified_leads_generated": "5",
        "offers_received_within_72hrs": "2",
        "marketing_spend": "150",
        "marketing_channels_used": "MLS",
    },
]


class SampleDataBuilder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.ids: dict[str, list[str]] = {}
        self.errors: list[str] = []

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body)
        return resp.body

    async def _get(self, path: str) -> dict[str, Any]:
        resp = await self.client.get(path, portal_id=self.portal_id)
        return resp.body

    async def find_existing(self, object_type: str, search_field: str, search_value: str) -> str | None:
        try:
            body = {
                "filterGroups": [{"filters": [{"propertyName": search_field, "operator": "EQ", "value": search_value}]}],
                "limit": 1,
            }
            result = await self._post(f"/crm/v3/objects/{object_type}/search", body=body)
            results = result.get("results", [])
            if results:
                return str(results[0]["id"])
        except Exception:
            pass
        return None

    async def create_record(self, object_type: str, properties: dict[str, Any], label: str, search_field: str | None = None, search_value: str | None = None) -> str | None:
        # Check if exists
        if search_field and search_value:
            existing = await self.find_existing(object_type, search_field, search_value)
            if existing:
                print(f"  Skipped (exists): {label}")
                return existing
        else:
            # For objects without search_field, we can't check duplicates — still return None
            pass
        try:
            result = await self._post(f"/crm/v3/objects/{object_type}", body={"properties": properties})
            if "error" in result or "message" in result:
                self.errors.append(f"{label}: {result.get('message', result)}")
                return None
            rid = result.get("id")
            print(f"  Created {label}: {rid}")
            return rid
        except Exception as exc:
            self.errors.append(f"{label}: {exc}")
            return None

    async def create_association(self, from_type: str, from_id: str | None, to_type: str, to_id: str | None, type_id: int = 1, category: str = "HUBSPOT_DEFINED") -> None:
        if not from_id or not to_id:
            return
        try:
            body = {
                "inputs": [
                    {
                        "from": {"id": from_id},
                        "to": {"id": to_id},
                        "types": [{"associationCategory": category, "associationTypeId": type_id}],
                    }
                ]
            }
            await self._post(f"/crm/v4/associations/{from_type}/{to_type}/batch/create", body=body)
            print(f"  Associated {from_type}:{from_id} -> {to_type}:{to_id}")
        except Exception as exc:
            self.errors.append(f"Assoc {from_type}->{to_type}: {exc}")

    async def create_engagement(self, engagement_type: str, properties: dict[str, Any], associated_id: str | None, associated_type: str) -> str | None:
        if not associated_id:
            return None
        try:
            body = {"properties": properties}
            result = await self._post(f"/crm/v3/objects/{engagement_type}", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"Engagement {engagement_type}: {result.get('message', result)}")
                return None
            eid = result.get("id")
            print(f"  Created {engagement_type}: {eid}")
            try:
                await self._post(
                    f"/crm/v3/objects/{engagement_type}/{eid}/associations/{associated_type}/{associated_id}/1",
                    body={},
                )
            except Exception:
                pass
            return eid
        except Exception as exc:
            self.errors.append(f"Engagement {engagement_type}: {exc}")
            return None


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"Portal {PORTAL_ID} not configured.")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = SampleDataBuilder(client, PORTAL_ID)

    try:
        print("\n=== Creating contacts ===")
        contact_ids = []
        for c in SAMPLE_CONTACTS:
            rid = await builder.create_record("contacts", c, f"contact {c['email']}", "email", c["email"])
            if rid:
                contact_ids.append(rid)
        builder.ids["contacts"] = contact_ids

        print("\n=== Creating companies ===")
        company_ids = []
        for c in SAMPLE_COMPANIES:
            rid = await builder.create_record("companies", c, f"company {c['name']}", "name", c["name"])
            if rid:
                company_ids.append(rid)
        builder.ids["companies"] = company_ids

        print("\n=== Creating listings ===")
        listing_ids = []
        for l in SAMPLE_LISTINGS:
            rid = await builder.create_record(LISTINGS, l, f"listing {l['mls_number']}", "mls_number", l["mls_number"])
            if rid:
                listing_ids.append(rid)
        builder.ids["listings"] = listing_ids

        print("\n=== Creating deals ===")
        deal_ids = []
        for d in SAMPLE_DEALS:
            rid = await builder.create_record("deals", d, f"deal {d['dealname']}", "dealname", d["dealname"])
            if rid:
                deal_ids.append(rid)
        builder.ids["deals"] = deal_ids

        print("\n=== Creating tickets ===")
        ticket_ids = []
        for t in SAMPLE_TICKETS:
            rid = await builder.create_record("tickets", t, f"ticket {t['subject'][:40]}", "subject", t["subject"])
            if rid:
                ticket_ids.append(rid)
        builder.ids["tickets"] = ticket_ids

        print("\n=== Creating showings ===")
        showing_ids = []
        for s in SAMPLE_SHOWINGS:
            rid = await builder.create_record(SHOWINGS, s, "showing")
            if rid:
                showing_ids.append(rid)
        builder.ids["showings"] = showing_ids

        print("\n=== Creating offers ===")
        offer_ids = []
        for o in SAMPLE_OFFERS:
            rid = await builder.create_record(OFFERS, o, "offer")
            if rid:
                offer_ids.append(rid)
        builder.ids["offers"] = offer_ids

        print("\n=== Creating commissions ===")
        commission_ids = []
        for c in SAMPLE_COMMISSIONS:
            rid = await builder.create_record(COMMISSIONS, c, "commission")
            if rid:
                commission_ids.append(rid)
        builder.ids["commissions"] = commission_ids

        print("\n=== Creating open houses ===")
        open_house_ids = []
        for o in SAMPLE_OPEN_HOUSES:
            rid = await builder.create_record(OPEN_HOUSES, o, "open house")
            if rid:
                open_house_ids.append(rid)
        builder.ids["open_houses"] = open_house_ids

        # Associations
        print("\n=== Creating associations ===")
        if len(contact_ids) >= 8 and len(company_ids) >= 2:
            # contacts -> companies (default type 279 for company association)
            await builder.create_association("contacts", contact_ids[0], "companies", company_ids[0], type_id=279)
            await builder.create_association("contacts", contact_ids[2], "companies", company_ids[0], type_id=279)
            await builder.create_association("contacts", contact_ids[6], "companies", company_ids[0], type_id=279)
            await builder.create_association("contacts", contact_ids[7], "companies", company_ids[1], type_id=279)
            # contacts -> deals (type 4)
            await builder.create_association("contacts", contact_ids[0], "deals", deal_ids[0], type_id=4)
            await builder.create_association("contacts", contact_ids[2], "deals", deal_ids[1], type_id=4)
            await builder.create_association("contacts", contact_ids[4], "deals", deal_ids[2], type_id=4)
            # contacts -> listings (type 883)
            await builder.create_association("contacts", contact_ids[2], LISTINGS, listing_ids[0], type_id=883)
            await builder.create_association("contacts", contact_ids[6], LISTINGS, listing_ids[0], type_id=883)
            await builder.create_association("contacts", contact_ids[0], LISTINGS, listing_ids[0], type_id=883)
            # showings -> listings (no schema — skip)
            # contacts -> showings (no schema — skip)
            # offers -> listings (no schema — skip)
            # contacts -> offers (no schema — skip)
            # commissions -> deals (no schema — skip)
            # open_houses -> listings (no schema — skip)
            # tickets -> deals (type 28)
            await builder.create_association("tickets", ticket_ids[0], "deals", deal_ids[0], type_id=28)
            # contacts -> contacts (type 449)
            await builder.create_association("contacts", contact_ids[3], "contacts", contact_ids[5], type_id=449)

        # Engagements
        print("\n=== Creating engagements ===")
        if contact_ids:
            await builder.create_engagement(
                "notes",
                {
                    "hs_note_body": "Sarah is pre-approved for $500K and wants to close by June 15. She has two kids and needs a fenced yard. Showed her 456 Maple Ave today.",
                    "hs_timestamp": "2026-05-08T14:30:00Z",
                },
                contact_ids[0], "contacts",
            )
            if len(contact_ids) > 6:
                await builder.create_engagement(
                    "tasks",
                    {
                        "hs_task_body": "Follow up with Sarah on inspection report concerns",
                        "hs_task_subject": "Inspection follow-up - Sarah Johnson",
                        "hs_task_status": "NOT_STARTED",
                        "hs_task_priority": "HIGH",
                        "hs_task_type": "TODO",
                        "hs_timestamp": "2026-05-09T09:00:00Z",
                    },
                    contact_ids[6], "contacts",
                )
            await builder.create_engagement(
                "meetings",
                {
                    "hs_meeting_title": "Initial Buyer Consultation - Sarah Johnson",
                    "hs_meeting_body": "Discussed budget, timeline, and preferred neighborhoods. Pre-approval letter received.",
                    "hs_meeting_start_time": "2026-04-20T10:00:00Z",
                    "hs_meeting_end_time": "2026-04-20T11:00:00Z",
                    "hs_meeting_outcome": "SCHEDULED",
                    "hs_timestamp": "2026-04-20T10:00:00Z",
                },
                contact_ids[0], "contacts",
            )
            if len(contact_ids) > 2:
                await builder.create_engagement(
                    "calls",
                    {
                        "hs_call_title": "Follow-up call - James Anderson listing prep",
                        "hs_call_body": "Discussed staging timeline and professional photo shoot. Confirmed MLS entry date.",
                        "hs_call_duration": "900000",
                        "hs_call_status": "COMPLETED",
                        "hs_call_direction": "OUTBOUND",
                        "hs_timestamp": "2026-04-25T16:00:00Z",
                    },
                    contact_ids[2], "contacts",
                )
            await builder.create_engagement(
                "emails",
                {
                    "hs_email_subject": "Your offer on 456 Maple Ave",
                    "hs_email_text": "Hi Sarah, I wanted to update you on the offer we submitted yesterday. The seller has countered at $420K. Let's discuss strategy.",
                    "hs_email_direction": "EMAIL",
                    "hs_email_status": "SENT",
                    "hs_timestamp": "2026-05-10T08:30:00Z",
                },
                contact_ids[0], "contacts",
            )

        print("\n=== Summary ===")
        for obj_type, ids in builder.ids.items():
            print(f"  {obj_type}: {len(ids)} created")
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
