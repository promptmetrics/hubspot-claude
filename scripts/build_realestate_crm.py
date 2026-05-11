#!/usr/bin/env python3
"""
Build the full Real Estate CRM architecture in HubSpot portal 148408595.
Run with: PYTHONPATH=src .venv/bin/python scripts/build_realestate_crm.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hubspot_agent.config import load_portal_config
from hubspot_agent.client import HubSpotClient

PORTAL_ID = "148408595"

# ---------------------------------------------------------------------------
# Property definitions for standard objects
# ---------------------------------------------------------------------------

CONTACT_PROPERTIES: list[dict[str, Any]] = [
    {"name": "contact_role", "label": "Contact Role", "type": "enumeration", "fieldType": "checkbox", "groupName": "realestate", "options": [
        {"label": "Buyer", "value": "Buyer", "displayOrder": 0},
        {"label": "Seller", "value": "Seller", "displayOrder": 1},
        {"label": "Tenant", "value": "Tenant", "displayOrder": 2},
        {"label": "Landlord", "value": "Landlord", "displayOrder": 3},
        {"label": "Investor", "value": "Investor", "displayOrder": 4},
        {"label": "Past Client", "value": "Past Client", "displayOrder": 5},
        {"label": "Sphere of Influence", "value": "Sphere of Influence", "displayOrder": 6},
        {"label": "Referral Partner", "value": "Referral Partner", "displayOrder": 7},
        {"label": "Vendor", "value": "Vendor", "displayOrder": 8},
        {"label": "Attorney", "value": "Attorney", "displayOrder": 9},
        {"label": "Lender Loan Officer", "value": "Lender Loan Officer", "displayOrder": 10},
        {"label": "Title Officer", "value": "Title Officer", "displayOrder": 11},
        {"label": "Inspector", "value": "Inspector", "displayOrder": 12},
        {"label": "Appraiser", "value": "Appraiser", "displayOrder": 13},
        {"label": "Photographer", "value": "Photographer", "displayOrder": 14},
        {"label": "Stager", "value": "Stager", "displayOrder": 15},
        {"label": "Contractor", "value": "Contractor", "displayOrder": 16},
        {"label": "Internal Agent", "value": "Internal Agent", "displayOrder": 17},
    ]},
    {"name": "buyer_qualification_status", "label": "Buyer Qualification Status", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Not Qualified", "value": "Not Qualified", "displayOrder": 0},
        {"label": "Pre-Qualified", "value": "Pre-Qualified", "displayOrder": 1},
        {"label": "Pre-Approved", "value": "Pre-Approved", "displayOrder": 2},
        {"label": "Cash Buyer", "value": "Cash Buyer", "displayOrder": 3},
        {"label": "Lost — Couldn't Qualify", "value": "Lost - Couldn't Qualify", "displayOrder": 4},
    ]},
    {"name": "seller_motivation", "label": "Seller Motivation", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Upgrading", "value": "Upgrading", "displayOrder": 0},
        {"label": "Downsizing", "value": "Downsizing", "displayOrder": 1},
        {"label": "Relocating", "value": "Relocating", "displayOrder": 2},
        {"label": "Investment Sale", "value": "Investment Sale", "displayOrder": 3},
        {"label": "Distressed", "value": "Distressed", "displayOrder": 4},
        {"label": "Estate Sale", "value": "Estate Sale", "displayOrder": 5},
        {"label": "Other", "value": "Other", "displayOrder": 6},
    ]},
    {"name": "price_range_min", "label": "Price Range Min", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "price_range_max", "label": "Price Range Max", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "preferred_areas", "label": "Preferred Areas", "type": "string", "fieldType": "textarea", "groupName": "realestate"},
    {"name": "bedrooms_min", "label": "Bedrooms Min", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "bathrooms_min", "label": "Bathrooms Min", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "square_feet_min", "label": "Square Feet Min", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "year_built_min", "label": "Year Built Min", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "property_types_of_interest", "label": "Property Types of Interest", "type": "enumeration", "fieldType": "checkbox", "groupName": "realestate", "options": [
        {"label": "Single Family", "value": "Single Family", "displayOrder": 0},
        {"label": "Condo", "value": "Condo", "displayOrder": 1},
        {"label": "Townhome", "value": "Townhome", "displayOrder": 2},
        {"label": "Multi-Family", "value": "Multi-Family", "displayOrder": 3},
        {"label": "Land", "value": "Land", "displayOrder": 4},
        {"label": "Commercial", "value": "Commercial", "displayOrder": 5},
        {"label": "New Construction", "value": "New Construction", "displayOrder": 6},
    ]},
    {"name": "timeline_to_buy", "label": "Timeline to Buy", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "0–30 days", "value": "0-30 days", "displayOrder": 0},
        {"label": "30–90 days", "value": "30-90 days", "displayOrder": 1},
        {"label": "3–6 months", "value": "3-6 months", "displayOrder": 2},
        {"label": "6–12 months", "value": "6-12 months", "displayOrder": 3},
        {"label": "12+ months", "value": "12+ months", "displayOrder": 4},
        {"label": "Just Browsing", "value": "Just Browsing", "displayOrder": 5},
    ]},
    {"name": "current_home_owned", "label": "Current Home Owned", "type": "bool", "fieldType": "booleancheckbox", "groupName": "realestate"},
    {"name": "current_home_address", "label": "Current Home Address", "type": "string", "fieldType": "textarea", "groupName": "realestate"},
    {"name": "current_home_estimated_value", "label": "Current Home Estimated Value", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "source_detail", "label": "Source Detail", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Zillow Tech Connect", "value": "Zillow Tech Connect", "displayOrder": 0},
        {"label": "Realtor.com lead", "value": "Realtor.com lead", "displayOrder": 1},
        {"label": "Open House Sign-In", "value": "Open House Sign-In", "displayOrder": 2},
        {"label": "Past Client Referral", "value": "Past Client Referral", "displayOrder": 3},
        {"label": "Sphere Referral", "value": "Sphere Referral", "displayOrder": 4},
        {"label": "Vendor Referral", "value": "Vendor Referral", "displayOrder": 5},
        {"label": "Walk-In", "value": "Walk-In", "displayOrder": 6},
        {"label": "Sign Call", "value": "Sign Call", "displayOrder": 7},
        {"label": "Online Form", "value": "Online Form", "displayOrder": 8},
        {"label": "Cold Call", "value": "Cold Call", "displayOrder": 9},
        {"label": "Door Knocking", "value": "Door Knocking", "displayOrder": 10},
        {"label": "Geographic Farm", "value": "Geographic Farm", "displayOrder": 11},
    ]},
    {"name": "anniversary_date", "label": "Anniversary Date", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "do_not_contact_reason", "label": "Do Not Contact Reason", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Marketing Only", "value": "Marketing Only", "displayOrder": 0},
        {"label": "All Contact", "value": "All Contact", "displayOrder": 1},
        {"label": "Hostile", "value": "Hostile", "displayOrder": 2},
        {"label": "Deceased", "value": "Deceased", "displayOrder": 3},
        {"label": "Moved Out of Service Area", "value": "Moved Out of Service Area", "displayOrder": 4},
    ]},
]

COMPANY_PROPERTIES: list[dict[str, Any]] = [
    {"name": "company_type", "label": "Company Type", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Brokerage (Cooperating)", "value": "Brokerage (Cooperating)", "displayOrder": 0},
        {"label": "Lender — Bank", "value": "Lender - Bank", "displayOrder": 1},
        {"label": "Lender — Mortgage Broker", "value": "Lender - Mortgage Broker", "displayOrder": 2},
        {"label": "Lender — Hard Money", "value": "Lender - Hard Money", "displayOrder": 3},
        {"label": "Title Company", "value": "Title Company", "displayOrder": 4},
        {"label": "Escrow Company", "value": "Escrow Company", "displayOrder": 5},
        {"label": "Law Firm", "value": "Law Firm", "displayOrder": 6},
        {"label": "Inspection Company", "value": "Inspection Company", "displayOrder": 7},
        {"label": "Appraisal Firm", "value": "Appraisal Firm", "displayOrder": 8},
        {"label": "Photography / Media", "value": "Photography / Media", "displayOrder": 9},
        {"label": "Staging Company", "value": "Staging Company", "displayOrder": 10},
        {"label": "General Contractor", "value": "General Contractor", "displayOrder": 11},
        {"label": "Specialty Trade", "value": "Specialty Trade", "displayOrder": 12},
        {"label": "HOA / Property Manager", "value": "HOA / Property Manager", "displayOrder": 13},
        {"label": "Builder / Developer", "value": "Builder / Developer", "displayOrder": 14},
        {"label": "Investor — Individual LLC", "value": "Investor - Individual LLC", "displayOrder": 15},
        {"label": "Investor — Institutional", "value": "Investor - Institutional", "displayOrder": 16},
        {"label": "Insurance", "value": "Insurance", "displayOrder": 17},
        {"label": "Home Warranty", "value": "Home Warranty", "displayOrder": 18},
        {"label": "Marketing Vendor", "value": "Marketing Vendor", "displayOrder": 19},
        {"label": "Referral Partner", "value": "Referral Partner", "displayOrder": 20},
        {"label": "Other", "value": "Other", "displayOrder": 21},
    ]},
    {"name": "preferred_partner", "label": "Preferred Partner", "type": "bool", "fieldType": "booleancheckbox", "groupName": "realestate"},
    {"name": "partnership_tier", "label": "Partnership Tier", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Tier 1", "value": "Tier 1", "displayOrder": 0},
        {"label": "Tier 2", "value": "Tier 2", "displayOrder": 1},
        {"label": "Backup", "value": "Backup", "displayOrder": 2},
        {"label": "Avoid", "value": "Avoid", "displayOrder": 3},
    ]},
    {"name": "partnership_notes", "label": "Partnership Notes", "type": "string", "fieldType": "textarea", "groupName": "realestate"},
    {"name": "co_brokerage_split_default", "label": "Co-Brokerage Split Default", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "license_number", "label": "License Number", "type": "string", "fieldType": "text", "groupName": "realestate"},
    {"name": "license_state", "label": "License State", "type": "string", "fieldType": "text", "groupName": "realestate"},
    {"name": "insurance_expiry_date", "label": "Insurance Expiry Date", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "hoa_management_company", "label": "HOA Management Company", "type": "bool", "fieldType": "booleancheckbox", "groupName": "realestate"},
    {"name": "hoa_dues_amount", "label": "HOA Dues Amount", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "hoa_dues_frequency", "label": "HOA Dues Frequency", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Monthly", "value": "Monthly", "displayOrder": 0},
        {"label": "Quarterly", "value": "Quarterly", "displayOrder": 1},
        {"label": "Annually", "value": "Annually", "displayOrder": 2},
        {"label": "None", "value": "None", "displayOrder": 3},
    ]},
    {"name": "investor_focus", "label": "Investor Focus", "type": "enumeration", "fieldType": "checkbox", "groupName": "realestate", "options": [
        {"label": "Buy-and-Hold", "value": "Buy-and-Hold", "displayOrder": 0},
        {"label": "Flip", "value": "Flip", "displayOrder": 1},
        {"label": "Wholesale", "value": "Wholesale", "displayOrder": 2},
        {"label": "BRRRR", "value": "BRRRR", "displayOrder": 3},
        {"label": "Multifamily", "value": "Multifamily", "displayOrder": 4},
        {"label": "Commercial", "value": "Commercial", "displayOrder": 5},
        {"label": "New Construction", "value": "New Construction", "displayOrder": 6},
    ]},
]

DEAL_PROPERTIES: list[dict[str, Any]] = [
    {"name": "commission_total", "label": "Commission Total", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "commission_percent", "label": "Commission Percent", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "buyer_side_or_seller_side", "label": "Buyer Side or Seller Side", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Buyer Side", "value": "Buyer Side", "displayOrder": 0},
        {"label": "Seller Side", "value": "Seller Side", "displayOrder": 1},
        {"label": "Both Sides (Double End)", "value": "Both Sides (Double End)", "displayOrder": 2},
        {"label": "Lease Side", "value": "Lease Side", "displayOrder": 3},
    ]},
    {"name": "property_address", "label": "Property Address", "type": "string", "fieldType": "text", "groupName": "realestate"},
    {"name": "mls_number", "label": "MLS Number", "type": "string", "fieldType": "text", "groupName": "realestate"},
    {"name": "contract_date", "label": "Contract Date", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "contingency_inspection_deadline", "label": "Contingency Inspection Deadline", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "contingency_appraisal_deadline", "label": "Contingency Appraisal Deadline", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "contingency_financing_deadline", "label": "Contingency Financing Deadline", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "earnest_money_amount", "label": "Earnest Money Amount", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "earnest_money_held_by", "label": "Earnest Money Held By", "type": "string", "fieldType": "text", "groupName": "realestate"},
    {"name": "financing_type", "label": "Financing Type", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Cash", "value": "Cash", "displayOrder": 0},
        {"label": "Conventional", "value": "Conventional", "displayOrder": 1},
        {"label": "FHA", "value": "FHA", "displayOrder": 2},
        {"label": "VA", "value": "VA", "displayOrder": 3},
        {"label": "USDA", "value": "USDA", "displayOrder": 4},
        {"label": "Jumbo", "value": "Jumbo", "displayOrder": 5},
        {"label": "Hard Money", "value": "Hard Money", "displayOrder": 6},
        {"label": "Seller Financing", "value": "Seller Financing", "displayOrder": 7},
        {"label": "Other", "value": "Other", "displayOrder": 8},
    ]},
    {"name": "days_on_market_at_contract", "label": "Days on Market at Contract", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "list_price", "label": "List Price", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "sale_price", "label": "Sale Price", "type": "number", "fieldType": "number", "groupName": "realestate"},
    {"name": "reason_lost", "label": "Reason Lost", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Buyer Withdrew", "value": "Buyer Withdrew", "displayOrder": 0},
        {"label": "Buyer Couldn't Qualify", "value": "Buyer Couldn't Qualify", "displayOrder": 1},
        {"label": "Seller Withdrew", "value": "Seller Withdrew", "displayOrder": 2},
        {"label": "Inspection Killed Deal", "value": "Inspection Killed Deal", "displayOrder": 3},
        {"label": "Appraisal Killed Deal", "value": "Appraisal Killed Deal", "displayOrder": 4},
        {"label": "Financing Fell Through", "value": "Financing Fell Through", "displayOrder": 5},
        {"label": "Title Issue", "value": "Title Issue", "displayOrder": 6},
        {"label": "Better Offer Accepted", "value": "Better Offer Accepted", "displayOrder": 7},
        {"label": "Buyer Found Other Property", "value": "Buyer Found Other Property", "displayOrder": 8},
        {"label": "Listing Expired", "value": "Listing Expired", "displayOrder": 9},
        {"label": "Withdrawn — Off Market", "value": "Withdrawn - Off Market", "displayOrder": 10},
        {"label": "Other", "value": "Other", "displayOrder": 11},
    ]},
    {"name": "reason_lost_notes", "label": "Reason Lost Notes", "type": "string", "fieldType": "textarea", "groupName": "realestate"},
    {"name": "expected_close_date_changes", "label": "Expected Close Date Changes", "type": "number", "fieldType": "number", "groupName": "realestate"},
]

TICKET_PROPERTIES: list[dict[str, Any]] = [
    {"name": "ticket_category", "label": "Ticket Category", "type": "enumeration", "fieldType": "select", "groupName": "realestate", "options": [
        {"label": "Transaction Document", "value": "Transaction Document", "displayOrder": 0},
        {"label": "Inspection Repair", "value": "Inspection Repair", "displayOrder": 1},
        {"label": "Closing Issue", "value": "Closing Issue", "displayOrder": 2},
        {"label": "Post-Close Repair", "value": "Post-Close Repair", "displayOrder": 3},
        {"label": "Home Warranty Claim", "value": "Home Warranty Claim", "displayOrder": 4},
        {"label": "Vendor Coordination", "value": "Vendor Coordination", "displayOrder": 5},
        {"label": "Client Complaint", "value": "Client Complaint", "displayOrder": 6},
        {"label": "Compliance Issue", "value": "Compliance Issue", "displayOrder": 7},
        {"label": "Lead Routing Issue", "value": "Lead Routing Issue", "displayOrder": 8},
        {"label": "Other", "value": "Other", "displayOrder": 9},
    ]},
    {"name": "sla_due_date", "label": "SLA Due Date", "type": "date", "fieldType": "date", "groupName": "realestate"},
    {"name": "resolution_notes", "label": "Resolution Notes", "type": "string", "fieldType": "textarea", "groupName": "realestate"},
    {"name": "client_satisfaction_rating", "label": "Client Satisfaction Rating", "type": "number", "fieldType": "number", "groupName": "realestate"},
]


# ---------------------------------------------------------------------------
# Custom object schemas
# ---------------------------------------------------------------------------

CUSTOM_OBJECTS: dict[str, dict[str, Any]] = {
    "listings": {
        "labels": {"singular": "Listing", "plural": "Listings"},
        "primaryDisplayProperty": "property_address",
        "requiredProperties": ["property_address"],
        "properties": [
            {"name": "mls_number", "label": "MLS Number", "type": "string", "fieldType": "text"},
            {"name": "property_address", "label": "Property Address", "type": "string", "fieldType": "text"},
            {"name": "unit_number", "label": "Unit Number", "type": "string", "fieldType": "text"},
            {"name": "city", "label": "City", "type": "string", "fieldType": "text"},
            {"name": "state", "label": "State", "type": "string", "fieldType": "text"},
            {"name": "zip", "label": "ZIP", "type": "string", "fieldType": "text"},
            {"name": "county", "label": "County", "type": "string", "fieldType": "text"},
            {"name": "subdivision", "label": "Subdivision", "type": "string", "fieldType": "text"},
            {"name": "parcel_id", "label": "Parcel ID", "type": "string", "fieldType": "text"},
            {"name": "latitude", "label": "Latitude", "type": "number", "fieldType": "number"},
            {"name": "longitude", "label": "Longitude", "type": "number", "fieldType": "number"},
            {"name": "google_place_id", "label": "Google Place ID", "type": "string", "fieldType": "text"},
            {"name": "property_type", "label": "Property Type", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Single Family", "value": "Single Family", "displayOrder": 0},
                {"label": "Condo", "value": "Condo", "displayOrder": 1},
                {"label": "Townhome", "value": "Townhome", "displayOrder": 2},
                {"label": "Multi-Family 2-4", "value": "Multi-Family 2-4", "displayOrder": 3},
                {"label": "Multi-Family 5+", "value": "Multi-Family 5+", "displayOrder": 4},
                {"label": "Mobile/Manufactured", "value": "Mobile/Manufactured", "displayOrder": 5},
                {"label": "Land", "value": "Land", "displayOrder": 6},
                {"label": "Commercial", "value": "Commercial", "displayOrder": 7},
                {"label": "New Construction", "value": "New Construction", "displayOrder": 8},
                {"label": "Co-op", "value": "Co-op", "displayOrder": 9},
            ]},
            {"name": "bedrooms", "label": "Bedrooms", "type": "number", "fieldType": "number"},
            {"name": "bathrooms_full", "label": "Bathrooms Full", "type": "number", "fieldType": "number"},
            {"name": "bathrooms_half", "label": "Bathrooms Half", "type": "number", "fieldType": "number"},
            {"name": "square_feet_living", "label": "Square Feet Living", "type": "number", "fieldType": "number"},
            {"name": "square_feet_lot", "label": "Square Feet Lot", "type": "number", "fieldType": "number"},
            {"name": "year_built", "label": "Year Built", "type": "number", "fieldType": "number"},
            {"name": "garage_spaces", "label": "Garage Spaces", "type": "number", "fieldType": "number"},
            {"name": "stories", "label": "Stories", "type": "number", "fieldType": "number"},
            {"name": "pool", "label": "Pool", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "waterfront", "label": "Waterfront", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "hoa_fee", "label": "HOA Fee", "type": "number", "fieldType": "number"},
            {"name": "hoa_frequency", "label": "HOA Frequency", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Monthly", "value": "Monthly", "displayOrder": 0},
                {"label": "Quarterly", "value": "Quarterly", "displayOrder": 1},
                {"label": "Annually", "value": "Annually", "displayOrder": 2},
                {"label": "None", "value": "None", "displayOrder": 3},
            ]},
            {"name": "taxes_annual", "label": "Taxes Annual", "type": "number", "fieldType": "number"},
            {"name": "flood_zone", "label": "Flood Zone", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "listing_status", "label": "Listing Status", "type": "enumeration", "fieldType": "select", "options": [
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
            {"name": "list_price", "label": "List Price", "type": "number", "fieldType": "number"},
            {"name": "original_list_price", "label": "Original List Price", "type": "number", "fieldType": "number"},
            {"name": "list_date", "label": "List Date", "type": "date", "fieldType": "date"},
            {"name": "expiration_date", "label": "Expiration Date", "type": "date", "fieldType": "date"},
            {"name": "withdrawal_date", "label": "Withdrawal Date", "type": "date", "fieldType": "date"},
            {"name": "sold_date", "label": "Sold Date", "type": "date", "fieldType": "date"},
            {"name": "sold_price", "label": "Sold Price", "type": "number", "fieldType": "number"},
            {"name": "days_on_market", "label": "Days on Market", "type": "number", "fieldType": "number"},
            {"name": "price_per_square_foot", "label": "Price per Square Foot", "type": "number", "fieldType": "number"},
            {"name": "listing_commission_offered_buyer_side", "label": "Listing Commission Offered Buyer Side", "type": "number", "fieldType": "number"},
            {"name": "listing_commission_offered_seller_side", "label": "Listing Commission Offered Seller Side", "type": "number", "fieldType": "number"},
            {"name": "professional_photos_url", "label": "Professional Photos URL", "type": "string", "fieldType": "text"},
            {"name": "virtual_tour_url", "label": "Virtual Tour URL", "type": "string", "fieldType": "text"},
            {"name": "mls_remarks_public", "label": "MLS Remarks Public", "type": "string", "fieldType": "textarea"},
            {"name": "mls_remarks_agent", "label": "MLS Remarks Agent", "type": "string", "fieldType": "textarea"},
            {"name": "marketing_started_date", "label": "Marketing Started Date", "type": "date", "fieldType": "date"},
            {"name": "signage_installed_date", "label": "Signage Installed Date", "type": "date", "fieldType": "date"},
            {"name": "total_showings_count", "label": "Total Showings Count", "type": "number", "fieldType": "number"},
            {"name": "total_offers_count", "label": "Total Offers Count", "type": "number", "fieldType": "number"},
            {"name": "last_showing_date", "label": "Last Showing Date", "type": "date", "fieldType": "date"},
            {"name": "total_open_houses_count", "label": "Total Open Houses Count", "type": "number", "fieldType": "number"},
            {"name": "last_price_change_date", "label": "Last Price Change Date", "type": "date", "fieldType": "date"},
            {"name": "price_changes_count", "label": "Price Changes Count", "type": "number", "fieldType": "number"},
            {"name": "is_off_market", "label": "Is Off Market", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "off_market_reason", "label": "Off Market Reason", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Pre-Listing", "value": "Pre-Listing", "displayOrder": 0},
                {"label": "Pocket Listing", "value": "Pocket Listing", "displayOrder": 1},
                {"label": "Investor Hold", "value": "Investor Hold", "displayOrder": 2},
                {"label": "FSBO Watch", "value": "FSBO Watch", "displayOrder": 3},
                {"label": "Foreclosure Watch", "value": "Foreclosure Watch", "displayOrder": 4},
                {"label": "Probate Watch", "value": "Probate Watch", "displayOrder": 5},
                {"label": "Distressed", "value": "Distressed", "displayOrder": 6},
                {"label": "Expired Listing — Working Owner", "value": "Expired Listing - Working Owner", "displayOrder": 7},
            ]},
            {"name": "estimated_arv", "label": "Estimated ARV", "type": "number", "fieldType": "number"},
            {"name": "estimated_rehab_cost", "label": "Estimated Rehab Cost", "type": "number", "fieldType": "number"},
        ],
    },
    "showings": {
        "labels": {"singular": "Showing", "plural": "Showings"},
        "primaryDisplayProperty": "showing_date",
        "requiredProperties": ["showing_date"],
        "properties": [
            {"name": "showing_date", "label": "Showing Date", "type": "datetime", "fieldType": "date"},
            {"name": "showing_status", "label": "Showing Status", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Scheduled", "value": "Scheduled", "displayOrder": 0},
                {"label": "Confirmed", "value": "Confirmed", "displayOrder": 1},
                {"label": "Completed", "value": "Completed", "displayOrder": 2},
                {"label": "No-Show", "value": "No-Show", "displayOrder": 3},
                {"label": "Cancelled", "value": "Cancelled", "displayOrder": 4},
                {"label": "Rescheduled", "value": "Rescheduled", "displayOrder": 5},
            ]},
            {"name": "showing_type", "label": "Showing Type", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Private Showing", "value": "Private Showing", "displayOrder": 0},
                {"label": "Open House Attendance", "value": "Open House Attendance", "displayOrder": 1},
                {"label": "Virtual Showing", "value": "Virtual Showing", "displayOrder": 2},
                {"label": "Second Showing", "value": "Second Showing", "displayOrder": 3},
                {"label": "Final Walkthrough", "value": "Final Walkthrough", "displayOrder": 4},
                {"label": "Inspection Walkthrough", "value": "Inspection Walkthrough", "displayOrder": 5},
            ]},
            {"name": "duration_minutes", "label": "Duration Minutes", "type": "number", "fieldType": "number"},
            {"name": "feedback_received", "label": "Feedback Received", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "feedback_rating", "label": "Feedback Rating", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Loved It", "value": "Loved It", "displayOrder": 0},
                {"label": "Liked It", "value": "Liked It", "displayOrder": 1},
                {"label": "Neutral", "value": "Neutral", "displayOrder": 2},
                {"label": "Didn't Like", "value": "Didn't Like", "displayOrder": 3},
                {"label": "Hated It", "value": "Hated It", "displayOrder": 4},
            ]},
            {"name": "feedback_likes", "label": "Feedback Likes", "type": "string", "fieldType": "textarea"},
            {"name": "feedback_concerns", "label": "Feedback Concerns", "type": "string", "fieldType": "textarea"},
            {"name": "objection_category", "label": "Objection Category", "type": "enumeration", "fieldType": "checkbox", "options": [
                {"label": "Price Too High", "value": "Price Too High", "displayOrder": 0},
                {"label": "Condition Issues", "value": "Condition Issues", "displayOrder": 1},
                {"label": "Layout", "value": "Layout", "displayOrder": 2},
                {"label": "Location", "value": "Location", "displayOrder": 3},
                {"label": "Schools", "value": "Schools", "displayOrder": 4},
                {"label": "Traffic / Noise", "value": "Traffic / Noise", "displayOrder": 5},
                {"label": "Yard / Lot", "value": "Yard / Lot", "displayOrder": 6},
                {"label": "HOA", "value": "HOA", "displayOrder": 7},
                {"label": "Specific Repair Needed", "value": "Specific Repair Needed", "displayOrder": 8},
                {"label": "Other", "value": "Other", "displayOrder": 9},
            ]},
            {"name": "would_consider_at_lower_price", "label": "Would Consider at Lower Price", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "target_price", "label": "Target Price", "type": "number", "fieldType": "number"},
            {"name": "resulted_in_offer", "label": "Resulted in Offer", "type": "bool", "fieldType": "booleancheckbox"},
        ],
    },
    "offers": {
        "labels": {"singular": "Offer", "plural": "Offers"},
        "primaryDisplayProperty": "offer_amount",
        "requiredProperties": ["offer_amount"],
        "properties": [
            {"name": "offer_amount", "label": "Offer Amount", "type": "number", "fieldType": "number"},
            {"name": "offer_date", "label": "Offer Date", "type": "date", "fieldType": "date"},
            {"name": "offer_status", "label": "Offer Status", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Submitted", "value": "Submitted", "displayOrder": 0},
                {"label": "Countered", "value": "Countered", "displayOrder": 1},
                {"label": "Counter-Submitted", "value": "Counter-Submitted", "displayOrder": 2},
                {"label": "Accepted", "value": "Accepted", "displayOrder": 3},
                {"label": "Rejected", "value": "Rejected", "displayOrder": 4},
                {"label": "Withdrawn", "value": "Withdrawn", "displayOrder": 5},
                {"label": "Expired", "value": "Expired", "displayOrder": 6},
            ]},
            {"name": "offer_type", "label": "Offer Type", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Initial", "value": "Initial", "displayOrder": 0},
                {"label": "Counter", "value": "Counter", "displayOrder": 1},
                {"label": "Best-and-Final", "value": "Best-and-Final", "displayOrder": 2},
                {"label": "Backup", "value": "Backup", "displayOrder": 3},
            ]},
            {"name": "expiration_date", "label": "Expiration Date", "type": "datetime", "fieldType": "date"},
            {"name": "down_payment_amount", "label": "Down Payment Amount", "type": "number", "fieldType": "number"},
            {"name": "down_payment_percent", "label": "Down Payment Percent", "type": "number", "fieldType": "number"},
            {"name": "earnest_money_amount", "label": "Earnest Money Amount", "type": "number", "fieldType": "number"},
            {"name": "closing_date_proposed", "label": "Closing Date Proposed", "type": "date", "fieldType": "date"},
            {"name": "financing_type", "label": "Financing Type", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Cash", "value": "Cash", "displayOrder": 0},
                {"label": "Conventional", "value": "Conventional", "displayOrder": 1},
                {"label": "FHA", "value": "FHA", "displayOrder": 2},
                {"label": "VA", "value": "VA", "displayOrder": 3},
                {"label": "USDA", "value": "USDA", "displayOrder": 4},
                {"label": "Jumbo", "value": "Jumbo", "displayOrder": 5},
                {"label": "Hard Money", "value": "Hard Money", "displayOrder": 6},
                {"label": "Seller Financing", "value": "Seller Financing", "displayOrder": 7},
                {"label": "Other", "value": "Other", "displayOrder": 8},
            ]},
            {"name": "pre_approval_attached", "label": "Pre-Approval Attached", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "proof_of_funds_attached", "label": "Proof of Funds Attached", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "contingency_inspection", "label": "Contingency Inspection", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "contingency_inspection_days", "label": "Contingency Inspection Days", "type": "number", "fieldType": "number"},
            {"name": "contingency_appraisal", "label": "Contingency Appraisal", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "contingency_appraisal_days", "label": "Contingency Appraisal Days", "type": "number", "fieldType": "number"},
            {"name": "contingency_financing", "label": "Contingency Financing", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "contingency_financing_days", "label": "Contingency Financing Days", "type": "number", "fieldType": "number"},
            {"name": "contingency_sale_of_home", "label": "Contingency Sale of Home", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "contingency_other", "label": "Contingency Other", "type": "string", "fieldType": "textarea"},
            {"name": "seller_concessions_requested", "label": "Seller Concessions Requested", "type": "number", "fieldType": "number"},
            {"name": "appliances_included", "label": "Appliances Included", "type": "enumeration", "fieldType": "checkbox", "options": [
                {"label": "Refrigerator", "value": "Refrigerator", "displayOrder": 0},
                {"label": "Washer", "value": "Washer", "displayOrder": 1},
                {"label": "Dryer", "value": "Dryer", "displayOrder": 2},
                {"label": "Hot Tub", "value": "Hot Tub", "displayOrder": 3},
                {"label": "Pool Equipment", "value": "Pool Equipment", "displayOrder": 4},
                {"label": "Riding Mower", "value": "Riding Mower", "displayOrder": 5},
                {"label": "Other", "value": "Other", "displayOrder": 6},
            ]},
            {"name": "repairs_requested_at_offer", "label": "Repairs Requested at Offer", "type": "string", "fieldType": "textarea"},
            {"name": "home_warranty_requested", "label": "Home Warranty Requested", "type": "bool", "fieldType": "booleancheckbox"},
            {"name": "closing_costs_credit", "label": "Closing Costs Credit", "type": "number", "fieldType": "number"},
            {"name": "competing_offers_at_time", "label": "Competing Offers at Time", "type": "number", "fieldType": "number"},
            {"name": "lost_reason", "label": "Lost Reason", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Price Too Low", "value": "Price Too Low", "displayOrder": 0},
                {"label": "Bad Terms", "value": "Bad Terms", "displayOrder": 1},
                {"label": "Contingencies Too Heavy", "value": "Contingencies Too Heavy", "displayOrder": 2},
                {"label": "Closing Date Mismatch", "value": "Closing Date Mismatch", "displayOrder": 3},
                {"label": "Buyer Not Pre-Approved", "value": "Buyer Not Pre-Approved", "displayOrder": 4},
                {"label": "Other Offer Accepted", "value": "Other Offer Accepted", "displayOrder": 5},
                {"label": "Withdrawn by Buyer", "value": "Withdrawn by Buyer", "displayOrder": 6},
                {"label": "Other", "value": "Other", "displayOrder": 7},
            ]},
        ],
    },
    "open_houses": {
        "labels": {"singular": "Open House", "plural": "Open Houses"},
        "primaryDisplayProperty": "event_date",
        "requiredProperties": ["event_date"],
        "properties": [
            {"name": "event_date", "label": "Event Date", "type": "datetime", "fieldType": "date"},
            {"name": "duration_minutes", "label": "Duration Minutes", "type": "number", "fieldType": "number"},
            {"name": "event_type", "label": "Event Type", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Public Open House", "value": "Public Open House", "displayOrder": 0},
                {"label": "Broker's Open", "value": "Broker's Open", "displayOrder": 1},
                {"label": "Twilight Tour", "value": "Twilight Tour", "displayOrder": 2},
                {"label": "Caravan", "value": "Caravan", "displayOrder": 3},
            ]},
            {"name": "event_status", "label": "Event Status", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Scheduled", "value": "Scheduled", "displayOrder": 0},
                {"label": "Live", "value": "Live", "displayOrder": 1},
                {"label": "Completed", "value": "Completed", "displayOrder": 2},
                {"label": "Cancelled", "value": "Cancelled", "displayOrder": 3},
            ]},
            {"name": "marketing_channels_used", "label": "Marketing Channels Used", "type": "enumeration", "fieldType": "checkbox", "options": [
                {"label": "MLS", "value": "MLS", "displayOrder": 0},
                {"label": "Zillow", "value": "Zillow", "displayOrder": 1},
                {"label": "Realtor.com", "value": "Realtor.com", "displayOrder": 2},
                {"label": "Facebook Ad", "value": "Facebook Ad", "displayOrder": 3},
                {"label": "Instagram Post", "value": "Instagram Post", "displayOrder": 4},
                {"label": "Yard Signs", "value": "Yard Signs", "displayOrder": 5},
                {"label": "Direct Mail", "value": "Direct Mail", "displayOrder": 6},
                {"label": "Email Blast", "value": "Email Blast", "displayOrder": 7},
                {"label": "Door Knocking", "value": "Door Knocking", "displayOrder": 8},
            ]},
            {"name": "marketing_spend", "label": "Marketing Spend", "type": "number", "fieldType": "number"},
            {"name": "attendee_count", "label": "Attendee Count", "type": "number", "fieldType": "number"},
            {"name": "sign_ins_collected", "label": "Sign-Ins Collected", "type": "number", "fieldType": "number"},
            {"name": "qualified_leads_generated", "label": "Qualified Leads Generated", "type": "number", "fieldType": "number"},
            {"name": "offers_received_within_72hrs", "label": "Offers Received Within 72hrs", "type": "number", "fieldType": "number"},
        ],
    },
    "commissions": {
        "labels": {"singular": "Commission", "plural": "Commissions"},
        "primaryDisplayProperty": "commission_gross",
        "requiredProperties": ["commission_gross"],
        "properties": [
            {"name": "commission_gross", "label": "Commission Gross", "type": "number", "fieldType": "number"},
            {"name": "commission_split_basis", "label": "Commission Split Basis", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Gross", "value": "Gross", "displayOrder": 0},
                {"label": "Net After Brokerage Cut", "value": "Net After Brokerage Cut", "displayOrder": 1},
            ]},
            {"name": "referral_fee_amount", "label": "Referral Fee Amount", "type": "number", "fieldType": "number"},
            {"name": "brokerage_split_percent", "label": "Brokerage Split Percent", "type": "number", "fieldType": "number"},
            {"name": "brokerage_amount", "label": "Brokerage Amount", "type": "number", "fieldType": "number"},
            {"name": "transaction_fee", "label": "Transaction Fee", "type": "number", "fieldType": "number"},
            {"name": "e_o_insurance_fee", "label": "E&O Insurance Fee", "type": "number", "fieldType": "number"},
            {"name": "payment_status", "label": "Payment Status", "type": "enumeration", "fieldType": "select", "options": [
                {"label": "Pending Close", "value": "Pending Close", "displayOrder": 0},
                {"label": "Awaiting CDA", "value": "Awaiting CDA", "displayOrder": 1},
                {"label": "Pending Disbursement", "value": "Pending Disbursement", "displayOrder": 2},
                {"label": "Paid", "value": "Paid", "displayOrder": 3},
                {"label": "Disputed", "value": "Disputed", "displayOrder": 4},
                {"label": "Refunded", "value": "Refunded", "displayOrder": 5},
            ]},
            {"name": "payment_date", "label": "Payment Date", "type": "date", "fieldType": "date"},
            {"name": "disbursement_authorization_signed_date", "label": "Disbursement Authorization Signed Date", "type": "date", "fieldType": "date"},
            {"name": "closed_date", "label": "Closed Date", "type": "date", "fieldType": "date"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Pipeline definitions
# ---------------------------------------------------------------------------

DEAL_PIPELINES: list[dict[str, Any]] = [
    {
        "label": "Buyer Pipeline",
        "displayOrder": 0,
        "stages": [
            {"label": "New Buyer Lead", "displayOrder": 0, "metadata": {"probability": 0.05, "isClosed": "false"}},
            {"label": "Consultation Scheduled", "displayOrder": 1, "metadata": {"probability": 0.15, "isClosed": "false"}},
            {"label": "Consultation Completed", "displayOrder": 2, "metadata": {"probability": 0.25, "isClosed": "false"}},
            {"label": "Pre-Approved / Cash Verified", "displayOrder": 3, "metadata": {"probability": 0.40, "isClosed": "false"}},
            {"label": "Active Search (Touring)", "displayOrder": 4, "metadata": {"probability": 0.50, "isClosed": "false"}},
            {"label": "Offer Submitted", "displayOrder": 5, "metadata": {"probability": 0.65, "isClosed": "false"}},
            {"label": "Under Contract", "displayOrder": 6, "metadata": {"probability": 0.80, "isClosed": "false"}},
            {"label": "Inspection / Due Diligence", "displayOrder": 7, "metadata": {"probability": 0.80, "isClosed": "false"}},
            {"label": "Appraisal", "displayOrder": 8, "metadata": {"probability": 0.85, "isClosed": "false"}},
            {"label": "Loan Clear-to-Close", "displayOrder": 9, "metadata": {"probability": 0.95, "isClosed": "false"}},
            {"label": "Closing Scheduled", "displayOrder": 10, "metadata": {"probability": 0.98, "isClosed": "false"}},
            {"label": "Closed Won", "displayOrder": 11, "metadata": {"probability": 1.00, "isClosed": "true", "isWon": "true"}},
            {"label": "Closed Lost", "displayOrder": 12, "metadata": {"probability": 0.00, "isClosed": "true", "isWon": "false"}},
        ],
    },
    {
        "label": "Seller Pipeline",
        "displayOrder": 1,
        "stages": [
            {"label": "New Seller Lead", "displayOrder": 0, "metadata": {"probability": 0.05, "isClosed": "false"}},
            {"label": "Listing Appointment Scheduled", "displayOrder": 1, "metadata": {"probability": 0.15, "isClosed": "false"}},
            {"label": "Listing Appointment Completed", "displayOrder": 2, "metadata": {"probability": 0.30, "isClosed": "false"}},
            {"label": "Pre-Listing Prep", "displayOrder": 3, "metadata": {"probability": 0.45, "isClosed": "false"}},
            {"label": "Listing Live", "displayOrder": 4, "metadata": {"probability": 0.55, "isClosed": "false"}},
            {"label": "Under Contract", "displayOrder": 5, "metadata": {"probability": 0.75, "isClosed": "false"}},
            {"label": "Inspection Negotiation", "displayOrder": 6, "metadata": {"probability": 0.80, "isClosed": "false"}},
            {"label": "Appraisal", "displayOrder": 7, "metadata": {"probability": 0.85, "isClosed": "false"}},
            {"label": "Closing Scheduled", "displayOrder": 8, "metadata": {"probability": 0.95, "isClosed": "false"}},
            {"label": "Closed Won", "displayOrder": 9, "metadata": {"probability": 1.00, "isClosed": "true", "isWon": "true"}},
            {"label": "Closed Lost", "displayOrder": 10, "metadata": {"probability": 0.00, "isClosed": "true", "isWon": "false"}},
        ],
    },
    {
        "label": "Lease Pipeline",
        "displayOrder": 2,
        "stages": [
            {"label": "New Tenant Lead", "displayOrder": 0, "metadata": {"probability": 0.10, "isClosed": "false"}},
            {"label": "Application Received", "displayOrder": 1, "metadata": {"probability": 0.40, "isClosed": "false"}},
            {"label": "Application Approved", "displayOrder": 2, "metadata": {"probability": 0.70, "isClosed": "false"}},
            {"label": "Lease Signed", "displayOrder": 3, "metadata": {"probability": 0.90, "isClosed": "false"}},
            {"label": "Move-In Scheduled", "displayOrder": 4, "metadata": {"probability": 0.95, "isClosed": "false"}},
            {"label": "Active Lease", "displayOrder": 5, "metadata": {"probability": 1.00, "isClosed": "false"}},
            {"label": "Renewed", "displayOrder": 6, "metadata": {"probability": 1.00, "isClosed": "true", "isWon": "true"}},
            {"label": "Moved Out", "displayOrder": 7, "metadata": {"probability": 0.00, "isClosed": "true", "isWon": "false"}},
        ],
    },
    {
        "label": "Investor / Off-Market Pipeline",
        "displayOrder": 3,
        "stages": [
            {"label": "Investor Lead", "displayOrder": 0, "metadata": {"probability": 0.05, "isClosed": "false"}},
            {"label": "Property Identified", "displayOrder": 1, "metadata": {"probability": 0.20, "isClosed": "false"}},
            {"label": "LOI Submitted", "displayOrder": 2, "metadata": {"probability": 0.40, "isClosed": "false"}},
            {"label": "Under Contract", "displayOrder": 3, "metadata": {"probability": 0.70, "isClosed": "false"}},
            {"label": "Due Diligence", "displayOrder": 4, "metadata": {"probability": 0.80, "isClosed": "false"}},
            {"label": "Closing", "displayOrder": 5, "metadata": {"probability": 0.95, "isClosed": "false"}},
            {"label": "Closed", "displayOrder": 6, "metadata": {"probability": 1.00, "isClosed": "true", "isWon": "true"}},
        ],
    },
]

TICKET_PIPELINES: list[dict[str, Any]] = [
    {
        "label": "Transaction Coordination",
        "displayOrder": 0,
        "stages": [
            {"label": "New", "displayOrder": 0, "metadata": {"isClosed": "false"}},
            {"label": "Awaiting Documents", "displayOrder": 1, "metadata": {"isClosed": "false"}},
            {"label": "Sent for Signature", "displayOrder": 2, "metadata": {"isClosed": "false"}},
            {"label": "Signed", "displayOrder": 3, "metadata": {"isClosed": "false"}},
            {"label": "Filed With Brokerage", "displayOrder": 4, "metadata": {"isClosed": "false"}},
            {"label": "Closed", "displayOrder": 5, "metadata": {"isClosed": "true"}},
        ],
    },
    {
        "label": "Client Service",
        "displayOrder": 1,
        "stages": [
            {"label": "New", "displayOrder": 0, "metadata": {"isClosed": "false"}},
            {"label": "Triaged", "displayOrder": 1, "metadata": {"isClosed": "false"}},
            {"label": "In Progress", "displayOrder": 2, "metadata": {"isClosed": "false"}},
            {"label": "Awaiting Vendor", "displayOrder": 3, "metadata": {"isClosed": "false"}},
            {"label": "Awaiting Client", "displayOrder": 4, "metadata": {"isClosed": "false"}},
            {"label": "Resolved", "displayOrder": 5, "metadata": {"isClosed": "false"}},
            {"label": "Closed", "displayOrder": 6, "metadata": {"isClosed": "true"}},
        ],
    },
]


# ---------------------------------------------------------------------------
# Association labels
# ---------------------------------------------------------------------------

ASSOCIATION_LABELS: list[tuple[str, str, str, str]] = [
    # Contact -> Contact
    ("contacts", "contacts", "Spouse / Partner", "spouse_partner"),
    ("contacts", "contacts", "Co-Buyer", "co_buyer"),
    ("contacts", "contacts", "Co-Seller", "co_seller"),
    ("contacts", "contacts", "Referred By", "referred_by"),
    ("contacts", "contacts", "Referred", "referred"),
    ("contacts", "contacts", "Family Member", "family_member"),
    ("contacts", "contacts", "Business Partner", "business_partner"),
    ("contacts", "contacts", "Attorney For", "attorney_for"),
    ("contacts", "contacts", "Lender For", "lender_for"),
    ("contacts", "contacts", "Inspector For", "inspector_for"),
    # Contact -> Deal
    ("contacts", "deals", "Buyer", "buyer"),
    ("contacts", "deals", "Co-Buyer", "co_buyer"),
    ("contacts", "deals", "Seller", "seller"),
    ("contacts", "deals", "Co-Seller", "co_seller"),
    ("contacts", "deals", "Buyer's Agent", "buyer_agent"),
    ("contacts", "deals", "Listing Agent", "listing_agent"),
    ("contacts", "deals", "Co-Listing Agent", "co_listing_agent"),
    ("contacts", "deals", "Cooperating Agent", "cooperating_agent"),
    ("contacts", "deals", "Buyer's Lender — Loan Officer", "buyer_lender_loan_officer"),
    ("contacts", "deals", "Buyer's Attorney", "buyer_attorney"),
    ("contacts", "deals", "Seller's Attorney", "seller_attorney"),
    ("contacts", "deals", "Title Officer", "title_officer"),
    ("contacts", "deals", "Inspector", "inspector"),
    ("contacts", "deals", "Appraiser", "appraiser"),
    ("contacts", "deals", "Photographer", "photographer"),
    ("contacts", "deals", "Stager", "stager"),
    ("contacts", "deals", "Other Vendor", "other_vendor"),
    # Contact -> Listing
    ("contacts", "listings", "Seller / Owner", "seller_owner"),
    ("contacts", "listings", "Co-Owner", "co_owner"),
    ("contacts", "listings", "Listing Agent", "listing_agent"),
    ("contacts", "listings", "Co-Listing Agent", "co_listing_agent"),
    ("contacts", "listings", "Buyer Interested", "buyer_interested"),
    ("contacts", "listings", "Buyer Showed Property", "buyer_showed_property"),
    ("contacts", "listings", "Buyer Made Offer", "buyer_made_offer"),
    ("contacts", "listings", "Buyer Closed", "buyer_closed"),
    ("contacts", "listings", "Past Owner", "past_owner"),
    ("contacts", "listings", "Tenant", "tenant"),
    # Contact -> Ticket
    ("contacts", "tickets", "Reporter", "reporter"),
    ("contacts", "tickets", "Subject Of", "subject_of"),
    ("contacts", "tickets", "Vendor Assigned", "vendor_assigned"),
    ("contacts", "tickets", "Resolver", "resolver"),
    # Company -> Company
    ("companies", "companies", "Subsidiary Of", "subsidiary_of"),
    ("companies", "companies", "Partnered With", "partnered_with"),
    ("companies", "companies", "Competitor Of", "competitor_of"),
    ("companies", "companies", "Owns", "owns"),
    # Company -> Deal
    ("companies", "deals", "Buyer's Brokerage", "buyer_brokerage"),
    ("companies", "deals", "Listing Brokerage", "listing_brokerage"),
    ("companies", "deals", "Buyer's Lender", "buyer_lender"),
    ("companies", "deals", "Title Company", "title_company"),
    ("companies", "deals", "Escrow Company", "escrow_company"),
    ("companies", "deals", "Buyer's Attorney's Firm", "buyer_attorney_firm"),
    ("companies", "deals", "Seller's Attorney's Firm", "seller_attorney_firm"),
    ("companies", "deals", "Inspection Company", "inspection_company"),
    ("companies", "deals", "Appraisal Firm", "appraisal_firm"),
    ("companies", "deals", "Home Warranty Provider", "home_warranty_provider"),
    # Company -> Listing
    ("companies", "listings", "Listing Brokerage", "listing_brokerage"),
    ("companies", "listings", "HOA", "hoa"),
    ("companies", "listings", "Builder", "builder"),
    ("companies", "listings", "Property Management", "property_management"),
    ("companies", "listings", "Past Listing Brokerage", "past_listing_brokerage"),
    # Deal -> Listing
    ("deals", "listings", "Subject Property", "subject_property"),
    ("deals", "listings", "Backup Property", "backup_property"),
    ("deals", "listings", "Investor Acquisition Of", "investor_acquisition_of"),
    # Deal -> Commission
    ("deals", "commissions", "Commission Record", "commission_record"),
    # Deal -> Ticket
    ("deals", "tickets", "Transaction Coordination", "transaction_coordination"),
    ("deals", "tickets", "Service Issue", "service_issue"),
    # Listing -> Showing
    ("listings", "showings", "Showing", "showing"),
    # Listing -> Offer
    ("listings", "offers", "Offer", "offer"),
    # Listing -> Open House
    ("listings", "open_houses", "Open House", "open_house"),
    # Listing -> Ticket
    ("listings", "tickets", "Property Issue", "property_issue"),
    # Showing -> Offer
    ("showings", "offers", "Resulted In Offer", "resulted_in_offer"),
    # Offer -> Offer
    ("offers", "offers", "Counter Of", "counter_of"),
    ("offers", "offers", "Replaced By", "replaced_by"),
    ("offers", "offers", "Beat", "beat"),
    # Commission -> Contact
    ("commissions", "contacts", "Lead Agent Payee", "lead_agent_payee"),
    ("commissions", "contacts", "Co-Agent Payee", "co_agent_payee"),
    ("commissions", "contacts", "Referral Payee", "referral_payee"),
    ("commissions", "contacts", "ISA Bonus Payee", "isa_bonus_payee"),
    ("commissions", "contacts", "Override Payee", "override_payee"),
]


# ---------------------------------------------------------------------------
# Sample records
# ---------------------------------------------------------------------------

SAMPLE_CONTACTS: list[dict[str, Any]] = [
    {"email": "john.smith@example.com", "firstname": "John", "lastname": "Smith", "phone": "555-0101", "contact_role": "Buyer", "buyer_qualification_status": "Pre-Approved", "price_range_min": 400000, "price_range_max": 600000, "preferred_areas": "Downtown, Midtown", "bedrooms_min": 3, "bathrooms_min": 2, "property_types_of_interest": "Single Family;Townhome", "timeline_to_buy": "30-90 days", "source_detail": "Zillow Tech Connect"},
    {"email": "jane.doe@example.com", "firstname": "Jane", "lastname": "Doe", "phone": "555-0102", "contact_role": "Seller", "seller_motivation": "Relocating", "current_home_owned": "true", "current_home_address": "123 Main St, Springfield", "current_home_estimated_value": 450000, "source_detail": "Past Client Referral"},
    {"email": "mike.johnson@example.com", "firstname": "Mike", "lastname": "Johnson", "phone": "555-0103", "contact_role": "Investor;Past Client", "source_detail": "Sphere Referral"},
    {"email": "sarah.williams@example.com", "firstname": "Sarah", "lastname": "Williams", "phone": "555-0104", "contact_role": "Buyer", "buyer_qualification_status": "Cash Buyer", "price_range_min": 800000, "price_range_max": 1200000, "property_types_of_interest": "Single Family;New Construction", "timeline_to_buy": "0-30 days", "source_detail": "Online Form"},
    {"email": "david.brown@example.com", "firstname": "David", "lastname": "Brown", "phone": "555-0105", "contact_role": "Seller;Past Client", "seller_motivation": "Downsizing", "current_home_owned": "true", "current_home_address": "456 Oak Ave, Springfield", "source_detail": "Walk-In"},
    {"email": "emily.davis@example.com", "firstname": "Emily", "lastname": "Davis", "phone": "555-0106", "contact_role": "Buyer", "buyer_qualification_status": "Pre-Qualified", "price_range_min": 300000, "price_range_max": 500000, "bedrooms_min": 2, "bathrooms_min": 1, "property_types_of_interest": "Condo;Townhome", "timeline_to_buy": "3-6 months", "source_detail": "Open House Sign-In"},
    {"email": "robert.miller@example.com", "firstname": "Robert", "lastname": "Miller", "phone": "555-0107", "contact_role": "Referral Partner;Sphere of Influence", "source_detail": "Vendor Referral"},
    {"email": "lisa.wilson@example.com", "firstname": "Lisa", "lastname": "Wilson", "phone": "555-0108", "contact_role": "Internal Agent", "source_detail": "Cold Call"},
    {"email": "james.taylor@example.com", "firstname": "James", "lastname": "Taylor", "phone": "555-0109", "contact_role": "Lender Loan Officer", "company_type": "Lender — Mortgage Broker", "source_detail": "Vendor Referral"},
    {"email": "patricia.anderson@example.com", "firstname": "Patricia", "lastname": "Anderson", "phone": "555-0110", "contact_role": "Attorney", "source_detail": "Vendor Referral"},
    {"email": "chris.thomas@example.com", "firstname": "Chris", "lastname": "Thomas", "phone": "555-0111", "contact_role": "Tenant", "source_detail": "Online Form"},
    {"email": "amanda.jackson@example.com", "firstname": "Amanda", "lastname": "Jackson", "phone": "555-0112", "contact_role": "Buyer;Seller", "buyer_qualification_status": "Pre-Approved", "seller_motivation": "Upgrading", "price_range_min": 500000, "price_range_max": 750000, "timeline_to_buy": "30-90 days", "source_detail": "Past Client Referral"},
    {"email": "kevin.white@example.com", "firstname": "Kevin", "lastname": "White", "phone": "555-0113", "contact_role": "Inspector", "source_detail": "Vendor Referral"},
    {"email": "nancy.harris@example.com", "firstname": "Nancy", "lastname": "Harris", "phone": "555-0114", "contact_role": "Stager", "source_detail": "Vendor Referral"},
    {"email": "brian.clark@example.com", "firstname": "Brian", "lastname": "Clark", "phone": "555-0115", "contact_role": "Photographer", "source_detail": "Vendor Referral"},
]

SAMPLE_COMPANIES: list[dict[str, Any]] = [
    {"name": "Springfield National Bank", "domain": "snb.example.com", "company_type": "Lender — Bank", "preferred_partner": "true", "partnership_tier": "Tier 1", "phone": "555-1001", "source_detail": "Vendor Referral"},
    {"name": "Metro Mortgage Brokers", "domain": "mmb.example.com", "company_type": "Lender — Mortgage Broker", "preferred_partner": "true", "partnership_tier": "Tier 1", "phone": "555-1002"},
    {"name": "First Title & Escrow", "domain": "ftescrow.example.com", "company_type": "Title Company", "preferred_partner": "true", "partnership_tier": "Tier 1", "phone": "555-1003"},
    {"name": "HomeInspect Pro", "domain": "hip.example.com", "company_type": "Inspection Company", "preferred_partner": "true", "partnership_tier": "Tier 2", "phone": "555-1004", "insurance_expiry_date": "2026-12-31"},
    {"name": "Stellar Staging Co", "domain": "stellarstaging.example.com", "company_type": "Staging Company", "preferred_partner": "true", "partnership_tier": "Tier 1", "phone": "555-1005"},
    {"name": "Green Acres HOA", "domain": "greenacreshoa.example.com", "company_type": "HOA / Property Manager", "hoa_management_company": "true", "hoa_dues_amount": 250, "hoa_dues_frequency": "Monthly", "phone": "555-1006"},
    {"name": "BuildRight Developers", "domain": "buildright.example.com", "company_type": "Builder / Developer", "phone": "555-1007"},
    {"name": "Acme Insurance", "domain": "acmeins.example.com", "company_type": "Insurance", "phone": "555-1008"},
    {"name": "Cooperating Brokerage LLC", "domain": "coop.example.com", "company_type": "Brokerage (Cooperating)", "co_brokerage_split_default": 0.025, "phone": "555-1009"},
    {"name": "FastFix Contractors", "domain": "fastfix.example.com", "company_type": "General Contractor", "preferred_partner": "true", "partnership_tier": "Backup", "phone": "555-1010", "license_number": "GC-12345", "license_state": "IL"},
    {"name": "Oakwood Law Firm", "domain": "oakwoodlaw.example.com", "company_type": "Law Firm", "preferred_partner": "true", "partnership_tier": "Tier 2", "phone": "555-1011"},
    {"name": "Premier Appraisal Group", "domain": "premierappraise.example.com", "company_type": "Appraisal Firm", "phone": "555-1012"},
    {"name": "Snap Photos Media", "domain": "snapphotos.example.com", "company_type": "Photography / Media", "phone": "555-1013"},
    {"name": "Investor Capital LLC", "domain": "investorcap.example.com", "company_type": "Investor — Institutional", "investor_focus": "Buy-and-Hold;Multifamily", "phone": "555-1014"},
    {"name": "ClearView Home Warranty", "domain": "clearviewhw.example.com", "company_type": "Home Warranty", "phone": "555-1015"},
]

SAMPLE_LISTINGS: list[dict[str, Any]] = [
    {"mls_number": "MLS001", "property_address": "123 Main St", "city": "Springfield", "state": "IL", "zip": "62701", "property_type": "Single Family", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 2100, "square_feet_lot": 6500, "year_built": 2005, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 4200, "flood_zone": "false", "listing_status": "Active", "list_price": 450000, "original_list_price": 460000, "list_date": "2026-04-01", "expiration_date": "2026-10-01", "days_on_market": 38, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS002", "property_address": "456 Oak Ave", "city": "Springfield", "state": "IL", "zip": "62702", "property_type": "Condo", "bedrooms": 2, "bathrooms_full": 2, "square_feet_living": 1200, "square_feet_lot": 0, "year_built": 2015, "garage_spaces": 1, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 300, "hoa_frequency": "Monthly", "taxes_annual": 2800, "flood_zone": "false", "listing_status": "Active", "list_price": 320000, "original_list_price": 320000, "list_date": "2026-03-15", "expiration_date": "2026-09-15", "days_on_market": 55, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS003", "property_address": "789 Pine Rd", "city": "Springfield", "state": "IL", "zip": "62703", "property_type": "Townhome", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 1800, "square_feet_lot": 3000, "year_built": 2010, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 150, "hoa_frequency": "Monthly", "taxes_annual": 3500, "flood_zone": "false", "listing_status": "Pending", "list_price": 380000, "original_list_price": 390000, "list_date": "2026-02-20", "expiration_date": "2026-08-20", "days_on_market": 78, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS004", "property_address": "321 Elm Blvd", "city": "Springfield", "state": "IL", "zip": "62704", "property_type": "Single Family", "bedrooms": 4, "bathrooms_full": 3, "bathrooms_half": 0, "square_feet_living": 2800, "square_feet_lot": 8500, "year_built": 1998, "garage_spaces": 2, "stories": 2, "pool": "true", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 5600, "flood_zone": "false", "listing_status": "Active", "list_price": 550000, "original_list_price": 550000, "list_date": "2026-04-10", "expiration_date": "2026-10-10", "days_on_market": 29, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS005", "property_address": "654 Maple Dr", "city": "Springfield", "state": "IL", "zip": "62705", "property_type": "Multi-Family 2-4", "bedrooms": 4, "bathrooms_full": 2, "square_feet_living": 2400, "square_feet_lot": 5000, "year_built": 1985, "garage_spaces": 1, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 4800, "flood_zone": "false", "listing_status": "Active", "list_price": 420000, "original_list_price": 430000, "list_date": "2026-03-25", "expiration_date": "2026-09-25", "days_on_market": 45, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS006", "property_address": "987 Cedar Ln", "city": "Springfield", "state": "IL", "zip": "62706", "property_type": "Land", "bedrooms": 0, "bathrooms_full": 0, "square_feet_living": 0, "square_feet_lot": 21780, "year_built": 0, "garage_spaces": 0, "stories": 0, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 800, "flood_zone": "false", "listing_status": "Active", "list_price": 150000, "original_list_price": 150000, "list_date": "2026-04-20", "expiration_date": "2026-10-20", "days_on_market": 19, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS007", "property_address": "147 Birch Way", "city": "Springfield", "state": "IL", "zip": "62707", "property_type": "Single Family", "bedrooms": 5, "bathrooms_full": 3, "bathrooms_half": 1, "square_feet_living": 3500, "square_feet_lot": 12000, "year_built": 2018, "garage_spaces": 3, "stories": 2, "pool": "true", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 7200, "flood_zone": "false", "listing_status": "Sold", "list_price": 750000, "original_list_price": 750000, "list_date": "2025-08-01", "expiration_date": "2026-02-01", "sold_date": "2025-11-15", "sold_price": 735000, "days_on_market": 106, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS008", "property_address": "258 Willow Ct", "city": "Springfield", "state": "IL", "zip": "62708", "property_type": "Condo", "bedrooms": 1, "bathrooms_full": 1, "square_feet_living": 800, "square_feet_lot": 0, "year_built": 2020, "garage_spaces": 1, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 400, "hoa_frequency": "Monthly", "taxes_annual": 2200, "flood_zone": "false", "listing_status": "Active", "list_price": 210000, "original_list_price": 210000, "list_date": "2026-04-05", "expiration_date": "2026-10-05", "days_on_market": 34, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS009", "property_address": "369 Spruce St", "city": "Springfield", "state": "IL", "zip": "62709", "property_type": "Townhome", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 1900, "square_feet_lot": 3500, "year_built": 2012, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 200, "hoa_frequency": "Monthly", "taxes_annual": 3800, "flood_zone": "false", "listing_status": "Coming Soon", "list_price": 410000, "original_list_price": 410000, "list_date": "2026-05-15", "expiration_date": "2026-11-15", "days_on_market": 0, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS010", "property_address": "741 Ash Ave", "city": "Springfield", "state": "IL", "zip": "62710", "property_type": "Single Family", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 0, "square_feet_living": 1600, "square_feet_lot": 7000, "year_built": 1975, "garage_spaces": 1, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 3100, "flood_zone": "false", "listing_status": "Active", "list_price": 295000, "original_list_price": 300000, "list_date": "2026-03-01", "expiration_date": "2026-09-01", "days_on_market": 69, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS011", "property_address": "852 Hickory Rd", "city": "Springfield", "state": "IL", "zip": "62711", "property_type": "Single Family", "bedrooms": 4, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 2400, "square_feet_lot": 9000, "year_built": 2008, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 50, "hoa_frequency": "Monthly", "taxes_annual": 4600, "flood_zone": "false", "listing_status": "Active Under Contract / Backup", "list_price": 485000, "original_list_price": 495000, "list_date": "2026-02-15", "expiration_date": "2026-08-15", "days_on_market": 83, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"mls_number": "MLS012", "property_address": "963 Poplar Blvd", "city": "Springfield", "state": "IL", "zip": "62712", "property_type": "Commercial", "bedrooms": 0, "bathrooms_full": 2, "square_feet_living": 5000, "square_feet_lot": 15000, "year_built": 1995, "garage_spaces": 10, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 12000, "flood_zone": "false", "listing_status": "Active", "list_price": 1200000, "original_list_price": 1250000, "list_date": "2026-01-10", "expiration_date": "2026-07-10", "days_on_market": 119, "listing_commission_offered_buyer_side": 0.03, "listing_commission_offered_seller_side": 0.03},
]

SAMPLE_DEALS: list[dict[str, Any]] = [
    {"dealname": "Smith Family - 123 Main St", "amount": 445000, "commission_total": 11125, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "123 Main St", "mls_number": "MLS001", "financing_type": "Conventional", "pipeline": "Buyer Pipeline", "dealstage": "Under Contract"},
    {"dealname": "Doe Family - 456 Oak Ave", "amount": 310000, "commission_total": 7750, "commission_percent": 0.025, "buyer_side_or_seller_side": "Seller Side", "property_address": "456 Oak Ave", "mls_number": "MLS002", "financing_type": "Cash", "pipeline": "Seller Pipeline", "dealstage": "Listing Live"},
    {"dealname": "Johnson Investor - 654 Maple Dr", "amount": 405000, "commission_total": 10125, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "654 Maple Dr", "mls_number": "MLS005", "financing_type": "Hard Money", "pipeline": "Investor / Off-Market Pipeline", "dealstage": "Under Contract"},
    {"dealname": "Williams Family - 321 Elm Blvd", "amount": 540000, "commission_total": 13500, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "321 Elm Blvd", "mls_number": "MLS004", "financing_type": "Conventional", "pipeline": "Buyer Pipeline", "dealstage": "Active Search (Touring)"},
    {"dealname": "Brown Family - 741 Ash Ave", "amount": 290000, "commission_total": 7250, "commission_percent": 0.025, "buyer_side_or_seller_side": "Seller Side", "property_address": "741 Ash Ave", "mls_number": "MLS010", "financing_type": "Cash", "pipeline": "Seller Pipeline", "dealstage": "Pre-Listing Prep"},
    {"dealname": "Thomas Rental - 258 Willow Ct", "amount": 200000, "commission_total": 4000, "commission_percent": 0.02, "buyer_side_or_seller_side": "Lease Side", "property_address": "258 Willow Ct", "mls_number": "MLS008", "financing_type": "Cash", "pipeline": "Lease Pipeline", "dealstage": "Lease Signed"},
    {"dealname": "Anderson Family - 852 Hickory Rd", "amount": 480000, "commission_total": 12000, "commission_percent": 0.025, "buyer_side_or_seller_side": "Both Sides (Double End)", "property_address": "852 Hickory Rd", "mls_number": "MLS011", "financing_type": "VA", "pipeline": "Buyer Pipeline", "dealstage": "Under Contract"},
    {"dealname": "Davis Family - 789 Pine Rd", "amount": 375000, "commission_total": 9375, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "789 Pine Rd", "mls_number": "MLS003", "financing_type": "FHA", "pipeline": "Buyer Pipeline", "dealstage": "Closed Won", "closedate": "2026-05-01"},
    {"dealname": "Miller Referral - 147 Birch Way", "amount": 735000, "commission_total": 18375, "commission_percent": 0.025, "buyer_side_or_seller_side": "Seller Side", "property_address": "147 Birch Way", "mls_number": "MLS007", "financing_type": "Conventional", "pipeline": "Seller Pipeline", "dealstage": "Closed Won", "closedate": "2025-11-15"},
    {"dealname": "Jackson Upgrade - 369 Spruce St", "amount": 405000, "commission_total": 10125, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "369 Spruce St", "mls_number": "MLS009", "financing_type": "Conventional", "pipeline": "Buyer Pipeline", "dealstage": "Offer Submitted"},
]

SAMPLE_TICKETS: list[dict[str, Any]] = [
    {"subject": "Inspection Report Missing", "content": "Still waiting for inspection report on 123 Main St", "ticket_category": "Transaction Document", "hs_pipeline": "Transaction Coordination", "hs_pipeline_stage": "Awaiting Documents"},
    {"subject": "Repair Request - Roof", "content": "Buyer requests roof repair credit of $3,500", "ticket_category": "Inspection Repair", "hs_pipeline": "Transaction Coordination", "hs_pipeline_stage": "In Progress"},
    {"subject": "Closing Delay - Lender Issue", "content": "Lender needs additional 5 days for final approval", "ticket_category": "Closing Issue", "hs_pipeline": "Client Service", "hs_pipeline_stage": "In Progress"},
    {"subject": "Post-Close HVAC Repair", "content": "HVAC unit failed 2 weeks after closing", "ticket_category": "Post-Close Repair", "hs_pipeline": "Client Service", "hs_pipeline_stage": "Awaiting Vendor"},
    {"subject": "Home Warranty Claim - Dishwasher", "content": "Dishwasher leaking, filed warranty claim", "ticket_category": "Home Warranty Claim", "hs_pipeline": "Client Service", "hs_pipeline_stage": "Triaged"},
    {"subject": "Vendor Coordination - Painter", "content": "Schedule pre-listing painting for 741 Ash Ave", "ticket_category": "Vendor Coordination", "hs_pipeline": "Transaction Coordination", "hs_pipeline_stage": "New"},
    {"subject": "Client Complaint - Communication", "content": "Seller feels they were not updated during showings", "ticket_category": "Client Complaint", "hs_pipeline": "Client Service", "hs_pipeline_stage": "Triaged"},
    {"subject": "Compliance Review - Disclosure", "content": "Missing lead paint disclosure in file", "ticket_category": "Compliance Issue", "hs_pipeline": "Transaction Coordination", "hs_pipeline_stage": "Awaiting Documents"},
    {"subject": "Lead Routing Error", "content": "Lead from Zillow was not assigned to agent for 4 hours", "ticket_category": "Lead Routing Issue", "hs_pipeline": "Client Service", "hs_pipeline_stage": "Resolved"},
    {"subject": "Title Commitment Issue", "content": "Cloud on title from prior lien needs clearance", "ticket_category": "Closing Issue", "hs_pipeline": "Transaction Coordination", "hs_pipeline_stage": "In Progress"},
]

SAMPLE_SHOWINGS: list[dict[str, Any]] = [
    {"showing_date": "2026-04-15T14:00:00Z", "showing_status": "Completed", "showing_type": "Private Showing", "duration_minutes": 30, "feedback_received": "true", "feedback_rating": "Liked It", "feedback_likes": "Great layout, nice backyard", "feedback_concerns": "Kitchen needs updating", "objection_category": "Condition Issues", "would_consider_at_lower_price": "true", "target_price": 430000, "resulted_in_offer": "true"},
    {"showing_date": "2026-04-18T10:00:00Z", "showing_status": "Completed", "showing_type": "Private Showing", "duration_minutes": 45, "feedback_received": "true", "feedback_rating": "Loved It", "feedback_likes": "Perfect condition, great schools", "would_consider_at_lower_price": "false", "resulted_in_offer": "true"},
    {"showing_date": "2026-04-20T16:00:00Z", "showing_status": "No-Show", "showing_type": "Private Showing", "duration_minutes": 0, "feedback_received": "false", "resulted_in_offer": "false"},
    {"showing_date": "2026-04-22T11:00:00Z", "showing_status": "Completed", "showing_type": "Open House Attendance", "duration_minutes": 20, "feedback_received": "true", "feedback_rating": "Neutral", "feedback_concerns": "Too small for family", "objection_category": "Layout", "would_consider_at_lower_price": "false", "resulted_in_offer": "false"},
    {"showing_date": "2026-04-25T13:30:00Z", "showing_status": "Scheduled", "showing_type": "Private Showing", "duration_minutes": 30, "feedback_received": "false", "resulted_in_offer": "false"},
    {"showing_date": "2026-04-28T15:00:00Z", "showing_status": "Completed", "showing_type": "Second Showing", "duration_minutes": 40, "feedback_received": "true", "feedback_rating": "Loved It", "feedback_likes": "Confirmed this is the one", "would_consider_at_lower_price": "false", "resulted_in_offer": "true"},
    {"showing_date": "2026-05-01T09:00:00Z", "showing_status": "Completed", "showing_type": "Final Walkthrough", "duration_minutes": 60, "feedback_received": "true", "feedback_rating": "Liked It", "feedback_likes": "House in good condition", "resulted_in_offer": "false"},
    {"showing_date": "2026-04-10T14:00:00Z", "showing_status": "Completed", "showing_type": "Private Showing", "duration_minutes": 25, "feedback_received": "true", "feedback_rating": "Didn't Like", "feedback_concerns": "Too much traffic noise", "objection_category": "Traffic / Noise", "would_consider_at_lower_price": "false", "resulted_in_offer": "false"},
    {"showing_date": "2026-04-12T11:00:00Z", "showing_status": "Completed", "showing_type": "Virtual Showing", "duration_minutes": 20, "feedback_received": "true", "feedback_rating": "Liked It", "feedback_likes": "Interested in in-person tour", "resulted_in_offer": "false"},
    {"showing_date": "2026-05-03T10:00:00Z", "showing_status": "Scheduled", "showing_type": "Private Showing", "duration_minutes": 30, "feedback_received": "false", "resulted_in_offer": "false"},
]

SAMPLE_OFFERS: list[dict[str, Any]] = [
    {"offer_amount": 440000, "offer_date": "2026-04-20", "offer_status": "Rejected", "offer_type": "Initial", "expiration_date": "2026-04-22T17:00:00Z", "down_payment_amount": 88000, "down_payment_percent": 0.20, "earnest_money_amount": 5000, "closing_date_proposed": "2026-06-15", "financing_type": "Conventional", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 3000, "home_warranty_requested": "true", "closing_costs_credit": 0, "competing_offers_at_time": 3, "lost_reason": "Other Offer Accepted"},
    {"offer_amount": 445000, "offer_date": "2026-04-21", "offer_status": "Accepted", "offer_type": "Initial", "expiration_date": "2026-04-23T17:00:00Z", "down_payment_amount": 89000, "down_payment_percent": 0.20, "earnest_money_amount": 5000, "closing_date_proposed": "2026-06-20", "financing_type": "Conventional", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 2000, "home_warranty_requested": "true", "closing_costs_credit": 0, "competing_offers_at_time": 3},
    {"offer_amount": 310000, "offer_date": "2026-04-05", "offer_status": "Accepted", "offer_type": "Initial", "expiration_date": "2026-04-07T17:00:00Z", "down_payment_amount": 62000, "down_payment_percent": 0.20, "earnest_money_amount": 3000, "closing_date_proposed": "2026-05-30", "financing_type": "Cash", "pre_approval_attached": "false", "proof_of_funds_attached": "true", "contingency_inspection": "true", "contingency_inspection_days": 7, "contingency_appraisal": "false", "contingency_financing": "false", "contingency_sale_of_home": "false", "seller_concessions_requested": 0, "home_warranty_requested": "false", "closing_costs_credit": 0, "competing_offers_at_time": 1},
    {"offer_amount": 400000, "offer_date": "2026-04-10", "offer_status": "Accepted", "offer_type": "Initial", "expiration_date": "2026-04-12T17:00:00Z", "down_payment_amount": 100000, "down_payment_percent": 0.25, "earnest_money_amount": 5000, "closing_date_proposed": "2026-06-01", "financing_type": "Hard Money", "pre_approval_attached": "false", "proof_of_funds_attached": "true", "contingency_inspection": "true", "contingency_inspection_days": 5, "contingency_appraisal": "false", "contingency_financing": "false", "contingency_sale_of_home": "false", "seller_concessions_requested": 0, "home_warranty_requested": "false", "closing_costs_credit": 0, "competing_offers_at_time": 2},
    {"offer_amount": 525000, "offer_date": "2026-04-25", "offer_status": "Submitted", "offer_type": "Initial", "expiration_date": "2026-04-27T17:00:00Z", "down_payment_amount": 105000, "down_payment_percent": 0.20, "earnest_money_amount": 5000, "closing_date_proposed": "2026-06-30", "financing_type": "Conventional", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 5000, "home_warranty_requested": "true", "closing_costs_credit": 3000, "competing_offers_at_time": 4},
    {"offer_amount": 280000, "offer_date": "2026-04-01", "offer_status": "Countered", "offer_type": "Initial", "expiration_date": "2026-04-03T17:00:00Z", "down_payment_amount": 56000, "down_payment_percent": 0.20, "earnest_money_amount": 2500, "closing_date_proposed": "2026-05-31", "financing_type": "FHA", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "true", "seller_concessions_requested": 5000, "home_warranty_requested": "true", "closing_costs_credit": 2000, "competing_offers_at_time": 2},
    {"offer_amount": 375000, "offer_date": "2026-03-10", "offer_status": "Accepted", "offer_type": "Initial", "expiration_date": "2026-03-12T17:00:00Z", "down_payment_amount": 75000, "down_payment_percent": 0.20, "earnest_money_amount": 4000, "closing_date_proposed": "2026-04-30", "financing_type": "FHA", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 1000, "home_warranty_requested": "true", "closing_costs_credit": 0, "competing_offers_at_time": 2},
    {"offer_amount": 735000, "offer_date": "2025-10-20", "offer_status": "Accepted", "offer_type": "Initial", "expiration_date": "2025-10-22T17:00:00Z", "down_payment_amount": 147000, "down_payment_percent": 0.20, "earnest_money_amount": 7000, "closing_date_proposed": "2025-12-15", "financing_type": "Conventional", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 2000, "home_warranty_requested": "true", "closing_costs_credit": 0, "competing_offers_at_time": 1},
    {"offer_amount": 395000, "offer_date": "2026-05-01", "offer_status": "Submitted", "offer_type": "Initial", "expiration_date": "2026-05-03T17:00:00Z", "down_payment_amount": 79000, "down_payment_percent": 0.20, "earnest_money_amount": 4000, "closing_date_proposed": "2026-06-30", "financing_type": "Conventional", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 0, "home_warranty_requested": "true", "closing_costs_credit": 0, "competing_offers_at_time": 1},
    {"offer_amount": 450000, "offer_date": "2026-04-15", "offer_status": "Rejected", "offer_type": "Initial", "expiration_date": "2026-04-17T17:00:00Z", "down_payment_amount": 90000, "down_payment_percent": 0.20, "earnest_money_amount": 5000, "closing_date_proposed": "2026-06-15", "financing_type": "Conventional", "pre_approval_attached": "true", "proof_of_funds_attached": "false", "contingency_inspection": "true", "contingency_inspection_days": 10, "contingency_appraisal": "true", "contingency_appraisal_days": 10, "contingency_financing": "true", "contingency_financing_days": 21, "contingency_sale_of_home": "false", "seller_concessions_requested": 3000, "home_warranty_requested": "true", "closing_costs_credit": 0, "competing_offers_at_time": 3, "lost_reason": "Other Offer Accepted"},
]

SAMPLE_OPEN_HOUSES: list[dict[str, Any]] = [
    {"event_date": "2026-04-05T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Zillow;Yard Signs", "marketing_spend": 150, "attendee_count": 25, "sign_ins_collected": 18, "qualified_leads_generated": 5, "offers_received_within_72hrs": 2},
    {"event_date": "2026-04-12T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Facebook Ad;Email Blast", "marketing_spend": 300, "attendee_count": 32, "sign_ins_collected": 24, "qualified_leads_generated": 8, "offers_received_within_72hrs": 3},
    {"event_date": "2026-04-19T11:00:00Z", "duration_minutes": 120, "event_type": "Broker's Open", "event_status": "Completed", "marketing_channels_used": "MLS;Email Blast", "marketing_spend": 50, "attendee_count": 12, "sign_ins_collected": 10, "qualified_leads_generated": 2, "offers_received_within_72hrs": 0},
    {"event_date": "2026-04-26T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Scheduled", "marketing_channels_used": "MLS;Zillow;Realtor.com;Yard Signs", "marketing_spend": 200, "attendee_count": 0, "sign_ins_collected": 0, "qualified_leads_generated": 0, "offers_received_within_72hrs": 0},
    {"event_date": "2026-03-20T10:00:00Z", "duration_minutes": 240, "event_type": "Twilight Tour", "event_status": "Completed", "marketing_channels_used": "MLS;Instagram Post;Direct Mail", "marketing_spend": 400, "attendee_count": 15, "sign_ins_collected": 12, "qualified_leads_generated": 3, "offers_received_within_72hrs": 1},
    {"event_date": "2026-05-01T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Scheduled", "marketing_channels_used": "MLS;Zillow;Yard Signs;Facebook Ad", "marketing_spend": 250, "attendee_count": 0, "sign_ins_collected": 0, "qualified_leads_generated": 0, "offers_received_within_72hrs": 0},
    {"event_date": "2026-04-08T11:00:00Z", "duration_minutes": 120, "event_type": "Caravan", "event_status": "Completed", "marketing_channels_used": "MLS;Email Blast", "marketing_spend": 75, "attendee_count": 8, "sign_ins_collected": 8, "qualified_leads_generated": 1, "offers_received_within_72hrs": 0},
    {"event_date": "2026-04-15T14:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Yard Signs;Door Knocking", "marketing_spend": 100, "attendee_count": 20, "sign_ins_collected": 15, "qualified_leads_generated": 4, "offers_received_within_72hrs": 1},
    {"event_date": "2026-03-25T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Zillow;Realtor.com", "marketing_spend": 175, "attendee_count": 28, "sign_ins_collected": 22, "qualified_leads_generated": 6, "offers_received_within_72hrs": 2},
    {"event_date": "2026-05-10T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Scheduled", "marketing_channels_used": "MLS;Yard Signs", "marketing_spend": 125, "attendee_count": 0, "sign_ins_collected": 0, "qualified_leads_generated": 0, "offers_received_within_72hrs": 0},
]

SAMPLE_COMMISSIONS: list[dict[str, Any]] = [
    {"commission_gross": 11125, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 2225, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-20"},
    {"commission_gross": 7750, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 1550, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Awaiting CDA", "closed_date": "2026-05-30"},
    {"commission_gross": 10125, "commission_split_basis": "Gross", "referral_fee_amount": 1000, "brokerage_split_percent": 0.20, "brokerage_amount": 2025, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Disbursement", "closed_date": "2026-06-01"},
    {"commission_gross": 13500, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 2700, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-30"},
    {"commission_gross": 7250, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 1450, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Awaiting CDA", "closed_date": "2026-05-31"},
    {"commission_gross": 4000, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 800, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Paid", "payment_date": "2026-05-01", "closed_date": "2026-05-01"},
    {"commission_gross": 24000, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 4800, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-20"},
    {"commission_gross": 9375, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 1875, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Paid", "payment_date": "2026-05-01", "closed_date": "2026-05-01"},
    {"commission_gross": 18375, "commission_split_basis": "Gross", "referral_fee_amount": 1500, "brokerage_split_percent": 0.20, "brokerage_amount": 3675, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Paid", "payment_date": "2025-11-15", "closed_date": "2025-11-15"},
    {"commission_gross": 10125, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 2025, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-30"},
]


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

class Builder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.created: dict[str, list[str]] = {"contacts": [], "companies": [], "deals": [], "tickets": [], "listings": [], "showings": [], "offers": [], "open_houses": [], "commissions": []}
        self.errors: list[dict[str, Any]] = []

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body or {})
        return resp.body

    async def _get(self, path: str) -> dict[str, Any]:
        resp = await self.client.get(path, portal_id=self.portal_id)
        return resp.body

    async def _patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.patch(path, portal_id=self.portal_id, body=body)
        return resp.body

    async def create_property_group(self, object_type: str, name: str, label: str) -> None:
        try:
            await self.client.post(
                f"/crm/v3/properties/{object_type}/groups",
                portal_id=self.portal_id,
                body={"name": name, "label": label, "displayOrder": 10},
            )
            print(f"  Created property group {name} on {object_type}")
        except Exception as exc:
            if "already exists" in str(exc).lower() or "conflict" in str(exc).lower():
                print(f"  Property group {name} already exists on {object_type}")
            else:
                print(f"  Error creating property group {name} on {object_type}: {exc}")

    async def create_custom_property(self, object_type: str, prop: dict[str, Any]) -> None:
        name = prop["name"]
        try:
            body = {
                "name": name,
                "label": prop["label"],
                "type": prop["type"],
                "fieldType": prop["fieldType"],
                "groupName": prop.get("groupName", "contactinformation"),
            }
            if "options" in prop:
                body["options"] = prop["options"]
            await self.client.post(
                f"/crm/v3/properties/{object_type}",
                portal_id=self.portal_id,
                body=body,
            )
            print(f"  Created property {name} on {object_type}")
        except Exception as exc:
            msg = str(exc)
            if "already exists" in msg.lower() or "conflict" in msg.lower():
                print(f"  Property {name} already exists on {object_type}")
            else:
                print(f"  ERROR creating property {name} on {object_type}: {exc}")
                self.errors.append({"action": "property", "object_type": object_type, "name": name, "error": msg})

    async def create_custom_object(self, schema: dict[str, Any]) -> str | None:
        name = schema["labels"]["plural"].lower().replace(" ", "_")
        try:
            # First check if it exists
            existing = await self._get(f"/crm/v3/schemas/{name}")
            if "objectTypeId" in existing:
                print(f"  Custom object {name} already exists")
                return name
        except Exception:
            pass
        try:
            body = {
                "labels": schema["labels"],
                "primaryDisplayProperty": schema["primaryDisplayProperty"],
                "requiredProperties": schema["requiredProperties"],
                "properties": schema["properties"],
                "name": name,
            }
            resp = await self.client.post("/crm/v3/schemas", portal_id=self.portal_id, body=body)
            print(f"  Created custom object {name}")
            return name
        except Exception as exc:
            print(f"  ERROR creating custom object {name}: {exc}")
            self.errors.append({"action": "custom_object", "name": name, "error": str(exc)})
            return None

    async def create_pipeline(self, object_type: str, pipeline: dict[str, Any]) -> None:
        label = pipeline["label"]
        try:
            existing = await self._get(f"/crm/v3/pipelines/{object_type}")
            for p in existing.get("results", []):
                if p.get("label") == label:
                    print(f"  Pipeline '{label}' already exists for {object_type}")
                    return
        except Exception:
            pass
        try:
            await self.client.post(
                f"/crm/v3/pipelines/{object_type}",
                portal_id=self.portal_id,
                body={
                    "label": label,
                    "displayOrder": pipeline["displayOrder"],
                    "stages": pipeline["stages"],
                },
            )
            print(f"  Created pipeline '{label}' for {object_type}")
        except Exception as exc:
            print(f"  ERROR creating pipeline '{label}' for {object_type}: {exc}")
            self.errors.append({"action": "pipeline", "object_type": object_type, "label": label, "error": str(exc)})

    async def create_association_label(self, from_type: str, to_type: str, label: str, name: str) -> None:
        try:
            await self.client.post(
                f"/crm/v4/associations/{from_type}/{to_type}/labels",
                portal_id=self.portal_id,
                body={"name": name, "label": label},
            )
            print(f"  Created association label '{label}' ({name}) from {from_type} to {to_type}")
        except Exception as exc:
            msg = str(exc)
            if "already exists" in msg.lower() or "conflict" in msg.lower():
                print(f"  Association label '{label}' already exists from {from_type} to {to_type}")
            else:
                print(f"  ERROR creating association label '{label}' from {from_type} to {to_type}: {exc}")
                self.errors.append({"action": "association", "from": from_type, "to": to_type, "label": label, "error": msg})

    async def create_record(self, object_type: str, properties: dict[str, Any]) -> str | None:
        try:
            resp = await self.client.post(
                f"/crm/v3/objects/{object_type}",
                portal_id=self.portal_id,
                body={"properties": properties},
            )
            obj_id = resp.body.get("id")
            if obj_id:
                self.created[object_type].append(obj_id)
            return obj_id
        except Exception as exc:
            print(f"  ERROR creating {object_type} record: {exc}")
            self.errors.append({"action": "record", "object_type": object_type, "error": str(exc)})
            return None

    async def batch_create_records(self, object_type: str, records: list[dict[str, Any]]) -> list[str]:
        created_ids: list[str] = []
        for record in records:
            obj_id = await self.create_record(object_type, record)
            if obj_id:
                created_ids.append(obj_id)
                print(f"  Created {object_type} {obj_id}")
            await asyncio.sleep(0.1)  # rate limit
        return created_ids


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"No portal config found for {PORTAL_ID}")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = Builder(client, PORTAL_ID)

    try:
        # 1. Create property groups
        print("\n=== Creating property groups ===")
        for object_type in ["contacts", "companies", "deals", "tickets"]:
            await builder.create_property_group(object_type, "realestate", "Real Estate")

        # 2. Create custom properties on standard objects
        print("\n=== Creating custom properties on Contacts ===")
        for prop in CONTACT_PROPERTIES:
            await builder.create_custom_property("contacts", prop)

        print("\n=== Creating custom properties on Companies ===")
        for prop in COMPANY_PROPERTIES:
            await builder.create_custom_property("companies", prop)

        print("\n=== Creating custom properties on Deals ===")
        for prop in DEAL_PROPERTIES:
            await builder.create_custom_property("deals", prop)

        print("\n=== Creating custom properties on Tickets ===")
        for prop in TICKET_PROPERTIES:
            await builder.create_custom_property("tickets", prop)

        # 3. Create custom objects
        print("\n=== Creating custom objects ===")
        custom_object_names: list[str] = []
        for key, schema in CUSTOM_OBJECTS.items():
            name = await builder.create_custom_object(schema)
            if name:
                custom_object_names.append(name)

        # 4. Create pipelines
        print("\n=== Creating Deal pipelines ===")
        for pipeline in DEAL_PIPELINES:
            await builder.create_pipeline("deals", pipeline)

        print("\n=== Creating Ticket pipelines ===")
        for pipeline in TICKET_PIPELINES:
            await builder.create_pipeline("tickets", pipeline)

        # 5. Create association labels
        print("\n=== Creating association labels ===")
        for from_type, to_type, label, name in ASSOCIATION_LABELS:
            await builder.create_association_label(from_type, to_type, label, name)

        # 6. Create sample records
        print("\n=== Creating sample Contacts ===")
        await builder.batch_create_records("contacts", SAMPLE_CONTACTS)

        print("\n=== Creating sample Companies ===")
        await builder.batch_create_records("companies", SAMPLE_COMPANIES)

        print("\n=== Creating sample Listings ===")
        await builder.batch_create_records("listings", SAMPLE_LISTINGS)

        print("\n=== Creating sample Deals ===")
        await builder.batch_create_records("deals", SAMPLE_DEALS)

        print("\n=== Creating sample Tickets ===")
        await builder.batch_create_records("tickets", SAMPLE_TICKETS)

        print("\n=== Creating sample Showings ===")
        await builder.batch_create_records("showings", SAMPLE_SHOWINGS)

        print("\n=== Creating sample Offers ===")
        await builder.batch_create_records("offers", SAMPLE_OFFERS)

        print("\n=== Creating sample Open Houses ===")
        await builder.batch_create_records("open_houses", SAMPLE_OPEN_HOUSES)

        print("\n=== Creating sample Commissions ===")
        await builder.batch_create_records("commissions", SAMPLE_COMMISSIONS)

        print("\n=== Summary ===")
        for obj_type, ids in builder.created.items():
            print(f"  {obj_type}: {len(ids)} created")
        if builder.errors:
            print(f"\n  {len(builder.errors)} errors encountered")
            for err in builder.errors[:10]:
                print(f"    {err}")
        else:
            print("\n  No errors!")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
