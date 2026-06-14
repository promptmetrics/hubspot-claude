#!/usr/bin/env python3
"""
Fix script for Real Estate CRM build in HubSpot portal 148408595.
Addresses: boolean options, custom object IDs, pipeline stage IDs, hs_name, value normalization.
Run with: PYTHONPATH=src .venv/bin/python scripts/build_realestate_crm_fix.py
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
# 1. Boolean properties that failed (need explicit true/false options)
# ---------------------------------------------------------------------------

BOOLEAN_PROPERTIES_TO_FIX: list[tuple[str, dict[str, Any]]] = [
    ("contacts", {
        "name": "current_home_owned",
        "label": "Current Home Owned",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "groupName": "realestate",
        "options": [
            {"label": "Yes", "value": "true"},
            {"label": "No", "value": "false"},
        ],
    }),
    ("companies", {
        "name": "preferred_partner",
        "label": "Preferred Partner",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "groupName": "realestate",
        "options": [
            {"label": "Yes", "value": "true"},
            {"label": "No", "value": "false"},
        ],
    }),
    ("companies", {
        "name": "hoa_management_company",
        "label": "HOA Management Company",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "groupName": "realestate",
        "options": [
            {"label": "Yes", "value": "true"},
            {"label": "No", "value": "false"},
        ],
    }),
]

# ---------------------------------------------------------------------------
# 2. Custom objects that failed (boolean fields inside them need options)
# ---------------------------------------------------------------------------

CUSTOM_OBJECTS_TO_CREATE: dict[str, dict[str, Any]] = {
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
            {"name": "feedback_received", "label": "Feedback Received", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
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
            {"name": "would_consider_at_lower_price", "label": "Would Consider at Lower Price", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
            {"name": "target_price", "label": "Target Price", "type": "number", "fieldType": "number"},
            {"name": "resulted_in_offer", "label": "Resulted in Offer", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
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
            {"name": "pre_approval_attached", "label": "Pre-Approval Attached", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
            {"name": "proof_of_funds_attached", "label": "Proof of Funds Attached", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
            {"name": "contingency_inspection", "label": "Contingency Inspection", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
            {"name": "contingency_inspection_days", "label": "Contingency Inspection Days", "type": "number", "fieldType": "number"},
            {"name": "contingency_appraisal", "label": "Contingency Appraisal", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
            {"name": "contingency_appraisal_days", "label": "Contingency Appraisal Days", "type": "number", "fieldType": "number"},
            {"name": "contingency_financing", "label": "Contingency Financing", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
            {"name": "contingency_financing_days", "label": "Contingency Financing Days", "type": "number", "fieldType": "number"},
            {"name": "contingency_sale_of_home", "label": "Contingency Sale of Home", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
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
            {"name": "home_warranty_requested", "label": "Home Warranty Requested", "type": "bool", "fieldType": "booleancheckbox", "options": [
                {"label": "Yes", "value": "true"},
                {"label": "No", "value": "false"},
            ]},
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
}

# ---------------------------------------------------------------------------
# 3. Sample data fixes
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
    {"email": "james.taylor@example.com", "firstname": "James", "lastname": "Taylor", "phone": "555-0109", "contact_role": "Lender Loan Officer", "source_detail": "Vendor Referral"},
    {"email": "patricia.anderson@example.com", "firstname": "Patricia", "lastname": "Anderson", "phone": "555-0110", "contact_role": "Attorney", "source_detail": "Vendor Referral"},
    {"email": "chris.thomas@example.com", "firstname": "Chris", "lastname": "Thomas", "phone": "555-0111", "contact_role": "Tenant", "source_detail": "Online Form"},
    {"email": "amanda.jackson@example.com", "firstname": "Amanda", "lastname": "Jackson", "phone": "555-0112", "contact_role": "Buyer;Seller", "buyer_qualification_status": "Pre-Approved", "seller_motivation": "Upgrading", "price_range_min": 500000, "price_range_max": 750000, "timeline_to_buy": "30-90 days", "source_detail": "Past Client Referral"},
    {"email": "kevin.white@example.com", "firstname": "Kevin", "lastname": "White", "phone": "555-0113", "contact_role": "Inspector", "source_detail": "Vendor Referral"},
    {"email": "nancy.harris@example.com", "firstname": "Nancy", "lastname": "Harris", "phone": "555-0114", "contact_role": "Stager", "source_detail": "Vendor Referral"},
    {"email": "brian.clark@example.com", "firstname": "Brian", "lastname": "Clark", "phone": "555-0115", "contact_role": "Photographer", "source_detail": "Vendor Referral"},
]

# FIXED: removed company_type and preferred_partner and source_detail from companies (cross-object)
# FIXED: normalized em-dashes to hyphens to match option values
SAMPLE_COMPANIES: list[dict[str, Any]] = [
    {"name": "Springfield National Bank", "domain": "snb.example.com", "company_type": "Lender - Bank", "preferred_partner": "true", "partnership_tier": "Tier 1", "phone": "555-1001"},
    {"name": "Metro Mortgage Brokers", "domain": "mmb.example.com", "company_type": "Lender - Mortgage Broker", "preferred_partner": "true", "partnership_tier": "Tier 1", "phone": "555-1002"},
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
    {"name": "Investor Capital LLC", "domain": "investorcap.example.com", "company_type": "Investor - Institutional", "investor_focus": "Buy-and-Hold;Multifamily", "phone": "555-1014"},
    {"name": "ClearView Home Warranty", "domain": "clearviewhw.example.com", "company_type": "Home Warranty", "phone": "555-1015"},
]

# FIXED: added hs_name (required for custom objects)
SAMPLE_LISTINGS: list[dict[str, Any]] = [
    {"hs_name": "123 Main St", "mls_number": "MLS001", "property_address": "123 Main St", "city": "Springfield", "state": "IL", "zip": "62701", "property_type": "Single Family", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 2100, "square_feet_lot": 6500, "year_built": 2005, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 4200, "flood_zone": "false", "listing_status": "Active", "list_price": 450000, "original_list_price": 460000, "list_date": "2026-04-01", "expiration_date": "2026-10-01", "days_on_market": 38, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "456 Oak Ave", "mls_number": "MLS002", "property_address": "456 Oak Ave", "city": "Springfield", "state": "IL", "zip": "62702", "property_type": "Condo", "bedrooms": 2, "bathrooms_full": 2, "square_feet_living": 1200, "square_feet_lot": 0, "year_built": 2015, "garage_spaces": 1, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 300, "hoa_frequency": "Monthly", "taxes_annual": 2800, "flood_zone": "false", "listing_status": "Active", "list_price": 320000, "original_list_price": 320000, "list_date": "2026-03-15", "expiration_date": "2026-09-15", "days_on_market": 55, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "789 Pine Rd", "mls_number": "MLS003", "property_address": "789 Pine Rd", "city": "Springfield", "state": "IL", "zip": "62703", "property_type": "Townhome", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 1800, "square_feet_lot": 3000, "year_built": 2010, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 150, "hoa_frequency": "Monthly", "taxes_annual": 3500, "flood_zone": "false", "listing_status": "Pending", "list_price": 380000, "original_list_price": 390000, "list_date": "2026-02-20", "expiration_date": "2026-08-20", "days_on_market": 78, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "321 Elm Blvd", "mls_number": "MLS004", "property_address": "321 Elm Blvd", "city": "Springfield", "state": "IL", "zip": "62704", "property_type": "Single Family", "bedrooms": 4, "bathrooms_full": 3, "bathrooms_half": 0, "square_feet_living": 2800, "square_feet_lot": 8500, "year_built": 1998, "garage_spaces": 2, "stories": 2, "pool": "true", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 5600, "flood_zone": "false", "listing_status": "Active", "list_price": 550000, "original_list_price": 550000, "list_date": "2026-04-10", "expiration_date": "2026-10-10", "days_on_market": 29, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "654 Maple Dr", "mls_number": "MLS005", "property_address": "654 Maple Dr", "city": "Springfield", "state": "IL", "zip": "62705", "property_type": "Multi-Family 2-4", "bedrooms": 4, "bathrooms_full": 2, "square_feet_living": 2400, "square_feet_lot": 5000, "year_built": 1985, "garage_spaces": 1, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 4800, "flood_zone": "false", "listing_status": "Active", "list_price": 420000, "original_list_price": 430000, "list_date": "2026-03-25", "expiration_date": "2026-09-25", "days_on_market": 45, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "987 Cedar Ln", "mls_number": "MLS006", "property_address": "987 Cedar Ln", "city": "Springfield", "state": "IL", "zip": "62706", "property_type": "Land", "bedrooms": 0, "bathrooms_full": 0, "square_feet_living": 0, "square_feet_lot": 21780, "year_built": 0, "garage_spaces": 0, "stories": 0, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 800, "flood_zone": "false", "listing_status": "Active", "list_price": 150000, "original_list_price": 150000, "list_date": "2026-04-20", "expiration_date": "2026-10-20", "days_on_market": 19, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "147 Birch Way", "mls_number": "MLS007", "property_address": "147 Birch Way", "city": "Springfield", "state": "IL", "zip": "62707", "property_type": "Single Family", "bedrooms": 5, "bathrooms_full": 3, "bathrooms_half": 1, "square_feet_living": 3500, "square_feet_lot": 12000, "year_built": 2018, "garage_spaces": 3, "stories": 2, "pool": "true", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 7200, "flood_zone": "false", "listing_status": "Sold", "list_price": 750000, "original_list_price": 750000, "list_date": "2025-08-01", "expiration_date": "2026-02-01", "sold_date": "2025-11-15", "sold_price": 735000, "days_on_market": 106, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "258 Willow Ct", "mls_number": "MLS008", "property_address": "258 Willow Ct", "city": "Springfield", "state": "IL", "zip": "62708", "property_type": "Condo", "bedrooms": 1, "bathrooms_full": 1, "square_feet_living": 800, "square_feet_lot": 0, "year_built": 2020, "garage_spaces": 1, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 400, "hoa_frequency": "Monthly", "taxes_annual": 2200, "flood_zone": "false", "listing_status": "Active", "list_price": 210000, "original_list_price": 210000, "list_date": "2026-04-05", "expiration_date": "2026-10-05", "days_on_market": 34, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "369 Spruce St", "mls_number": "MLS009", "property_address": "369 Spruce St", "city": "Springfield", "state": "IL", "zip": "62709", "property_type": "Townhome", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 1900, "square_feet_lot": 3500, "year_built": 2012, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 200, "hoa_frequency": "Monthly", "taxes_annual": 3800, "flood_zone": "false", "listing_status": "Coming Soon", "list_price": 410000, "original_list_price": 410000, "list_date": "2026-05-15", "expiration_date": "2026-11-15", "days_on_market": 0, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "741 Ash Ave", "mls_number": "MLS010", "property_address": "741 Ash Ave", "city": "Springfield", "state": "IL", "zip": "62710", "property_type": "Single Family", "bedrooms": 3, "bathrooms_full": 2, "bathrooms_half": 0, "square_feet_living": 1600, "square_feet_lot": 7000, "year_built": 1975, "garage_spaces": 1, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 3100, "flood_zone": "false", "listing_status": "Active", "list_price": 295000, "original_list_price": 300000, "list_date": "2026-03-01", "expiration_date": "2026-09-01", "days_on_market": 69, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "852 Hickory Rd", "mls_number": "MLS011", "property_address": "852 Hickory Rd", "city": "Springfield", "state": "IL", "zip": "62711", "property_type": "Single Family", "bedrooms": 4, "bathrooms_full": 2, "bathrooms_half": 1, "square_feet_living": 2400, "square_feet_lot": 9000, "year_built": 2008, "garage_spaces": 2, "stories": 2, "pool": "false", "waterfront": "false", "hoa_fee": 50, "hoa_frequency": "Monthly", "taxes_annual": 4600, "flood_zone": "false", "listing_status": "Active Under Contract / Backup", "list_price": 485000, "original_list_price": 495000, "list_date": "2026-02-15", "expiration_date": "2026-08-15", "days_on_market": 83, "listing_commission_offered_buyer_side": 0.025, "listing_commission_offered_seller_side": 0.025},
    {"hs_name": "963 Poplar Blvd", "mls_number": "MLS012", "property_address": "963 Poplar Blvd", "city": "Springfield", "state": "IL", "zip": "62712", "property_type": "Commercial", "bedrooms": 0, "bathrooms_full": 2, "square_feet_living": 5000, "square_feet_lot": 15000, "year_built": 1995, "garage_spaces": 10, "stories": 1, "pool": "false", "waterfront": "false", "hoa_fee": 0, "hoa_frequency": "None", "taxes_annual": 12000, "flood_zone": "false", "listing_status": "Active", "list_price": 1200000, "original_list_price": 1250000, "list_date": "2026-01-10", "expiration_date": "2026-07-10", "days_on_market": 119, "listing_commission_offered_buyer_side": 0.03, "listing_commission_offered_seller_side": 0.03},
]

# Deal stage labels will be mapped to IDs after pipeline creation
DEAL_STAGE_TEMPLATES: list[dict[str, Any]] = [
    {"dealname": "Smith Family - 123 Main St", "amount": 445000, "commission_total": 11125, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "123 Main St", "mls_number": "MLS001", "financing_type": "Conventional", "pipeline": "Buyer Pipeline", "dealstage_label": "Under Contract"},
    {"dealname": "Doe Family - 456 Oak Ave", "amount": 310000, "commission_total": 7750, "commission_percent": 0.025, "buyer_side_or_seller_side": "Seller Side", "property_address": "456 Oak Ave", "mls_number": "MLS002", "financing_type": "Cash", "pipeline": "Seller Pipeline", "dealstage_label": "Listing Live"},
    {"dealname": "Johnson Investor - 654 Maple Dr", "amount": 405000, "commission_total": 10125, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "654 Maple Dr", "mls_number": "MLS005", "financing_type": "Hard Money", "pipeline": "Investor / Off-Market Pipeline", "dealstage_label": "Under Contract"},
    {"dealname": "Williams Family - 321 Elm Blvd", "amount": 540000, "commission_total": 13500, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "321 Elm Blvd", "mls_number": "MLS004", "financing_type": "Conventional", "pipeline": "Buyer Pipeline", "dealstage_label": "Active Search (Touring)"},
    {"dealname": "Brown Family - 741 Ash Ave", "amount": 290000, "commission_total": 7250, "commission_percent": 0.025, "buyer_side_or_seller_side": "Seller Side", "property_address": "741 Ash Ave", "mls_number": "MLS010", "financing_type": "Cash", "pipeline": "Seller Pipeline", "dealstage_label": "Pre-Listing Prep"},
    {"dealname": "Thomas Rental - 258 Willow Ct", "amount": 200000, "commission_total": 4000, "commission_percent": 0.02, "buyer_side_or_seller_side": "Lease Side", "property_address": "258 Willow Ct", "mls_number": "MLS008", "financing_type": "Cash", "pipeline": "Lease Pipeline", "dealstage_label": "Lease Signed"},
    {"dealname": "Anderson Family - 852 Hickory Rd", "amount": 480000, "commission_total": 12000, "commission_percent": 0.025, "buyer_side_or_seller_side": "Both Sides (Double End)", "property_address": "852 Hickory Rd", "mls_number": "MLS011", "financing_type": "VA", "pipeline": "Buyer Pipeline", "dealstage_label": "Under Contract"},
    {"dealname": "Davis Family - 789 Pine Rd", "amount": 375000, "commission_total": 9375, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "789 Pine Rd", "mls_number": "MLS003", "financing_type": "FHA", "pipeline": "Buyer Pipeline", "dealstage_label": "Closed Won", "closedate": "2026-05-01"},
    {"dealname": "Miller Referral - 147 Birch Way", "amount": 735000, "commission_total": 18375, "commission_percent": 0.025, "buyer_side_or_seller_side": "Seller Side", "property_address": "147 Birch Way", "mls_number": "MLS007", "financing_type": "Conventional", "pipeline": "Seller Pipeline", "dealstage_label": "Closed Won", "closedate": "2025-11-15"},
    {"dealname": "Jackson Upgrade - 369 Spruce St", "amount": 405000, "commission_total": 10125, "commission_percent": 0.025, "buyer_side_or_seller_side": "Buyer Side", "property_address": "369 Spruce St", "mls_number": "MLS009", "financing_type": "Conventional", "pipeline": "Buyer Pipeline", "dealstage_label": "Offer Submitted"},
]

# Tickets use default pipeline - stage IDs are 1,2,3,4
SAMPLE_TICKETS: list[dict[str, Any]] = [
    {"subject": "Inspection Report Missing", "content": "Still waiting for inspection report on 123 Main St", "ticket_category": "Transaction Document", "hs_pipeline": "0", "hs_pipeline_stage": "1"},
    {"subject": "Repair Request - Roof", "content": "Buyer requests roof repair credit of $3,500", "ticket_category": "Inspection Repair", "hs_pipeline": "0", "hs_pipeline_stage": "2"},
    {"subject": "Closing Delay - Lender Issue", "content": "Lender needs additional 5 days for final approval", "ticket_category": "Closing Issue", "hs_pipeline": "0", "hs_pipeline_stage": "2"},
    {"subject": "Post-Close HVAC Repair", "content": "HVAC unit failed 2 weeks after closing", "ticket_category": "Post-Close Repair", "hs_pipeline": "0", "hs_pipeline_stage": "3"},
    {"subject": "Home Warranty Claim - Dishwasher", "content": "Dishwasher leaking, filed warranty claim", "ticket_category": "Home Warranty Claim", "hs_pipeline": "0", "hs_pipeline_stage": "2"},
    {"subject": "Vendor Coordination - Painter", "content": "Schedule pre-listing painting for 741 Ash Ave", "ticket_category": "Vendor Coordination", "hs_pipeline": "0", "hs_pipeline_stage": "1"},
    {"subject": "Client Complaint - Communication", "content": "Seller feels they were not updated during showings", "ticket_category": "Client Complaint", "hs_pipeline": "0", "hs_pipeline_stage": "2"},
    {"subject": "Compliance Review - Disclosure", "content": "Missing lead paint disclosure in file", "ticket_category": "Compliance Issue", "hs_pipeline": "0", "hs_pipeline_stage": "1"},
    {"subject": "Lead Routing Error", "content": "Lead from Zillow was not assigned to agent for 4 hours", "ticket_category": "Lead Routing Issue", "hs_pipeline": "0", "hs_pipeline_stage": "4"},
    {"subject": "Title Commitment Issue", "content": "Cloud on title from prior lien needs clearance", "ticket_category": "Closing Issue", "hs_pipeline": "0", "hs_pipeline_stage": "2"},
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
    {"hs_name": "Open House 2026-04-05", "event_date": "2026-04-05T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Zillow;Yard Signs", "marketing_spend": 150, "attendee_count": 25, "sign_ins_collected": 18, "qualified_leads_generated": 5, "offers_received_within_72hrs": 2},
    {"hs_name": "Open House 2026-04-12", "event_date": "2026-04-12T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Facebook Ad;Email Blast", "marketing_spend": 300, "attendee_count": 32, "sign_ins_collected": 24, "qualified_leads_generated": 8, "offers_received_within_72hrs": 3},
    {"hs_name": "Broker's Open 2026-04-19", "event_date": "2026-04-19T11:00:00Z", "duration_minutes": 120, "event_type": "Broker's Open", "event_status": "Completed", "marketing_channels_used": "MLS;Email Blast", "marketing_spend": 50, "attendee_count": 12, "sign_ins_collected": 10, "qualified_leads_generated": 2, "offers_received_within_72hrs": 0},
    {"hs_name": "Open House 2026-04-26", "event_date": "2026-04-26T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Scheduled", "marketing_channels_used": "MLS;Zillow;Realtor.com;Yard Signs", "marketing_spend": 200, "attendee_count": 0, "sign_ins_collected": 0, "qualified_leads_generated": 0, "offers_received_within_72hrs": 0},
    {"hs_name": "Twilight Tour 2026-03-20", "event_date": "2026-03-20T10:00:00Z", "duration_minutes": 240, "event_type": "Twilight Tour", "event_status": "Completed", "marketing_channels_used": "MLS;Instagram Post;Direct Mail", "marketing_spend": 400, "attendee_count": 15, "sign_ins_collected": 12, "qualified_leads_generated": 3, "offers_received_within_72hrs": 1},
    {"hs_name": "Open House 2026-05-01", "event_date": "2026-05-01T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Scheduled", "marketing_channels_used": "MLS;Zillow;Yard Signs;Facebook Ad", "marketing_spend": 250, "attendee_count": 0, "sign_ins_collected": 0, "qualified_leads_generated": 0, "offers_received_within_72hrs": 0},
    {"hs_name": "Caravan 2026-04-08", "event_date": "2026-04-08T11:00:00Z", "duration_minutes": 120, "event_type": "Caravan", "event_status": "Completed", "marketing_channels_used": "MLS;Email Blast", "marketing_spend": 75, "attendee_count": 8, "sign_ins_collected": 8, "qualified_leads_generated": 1, "offers_received_within_72hrs": 0},
    {"hs_name": "Open House 2026-04-15", "event_date": "2026-04-15T14:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Yard Signs;Door Knocking", "marketing_spend": 100, "attendee_count": 20, "sign_ins_collected": 15, "qualified_leads_generated": 4, "offers_received_within_72hrs": 1},
    {"hs_name": "Open House 2026-03-25", "event_date": "2026-03-25T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Completed", "marketing_channels_used": "MLS;Zillow;Realtor.com", "marketing_spend": 175, "attendee_count": 28, "sign_ins_collected": 22, "qualified_leads_generated": 6, "offers_received_within_72hrs": 2},
    {"hs_name": "Open House 2026-05-10", "event_date": "2026-05-10T13:00:00Z", "duration_minutes": 180, "event_type": "Public Open House", "event_status": "Scheduled", "marketing_channels_used": "MLS;Yard Signs", "marketing_spend": 125, "attendee_count": 0, "sign_ins_collected": 0, "qualified_leads_generated": 0, "offers_received_within_72hrs": 0},
]

SAMPLE_COMMISSIONS: list[dict[str, Any]] = [
    {"hs_name": "Commission - 11125", "commission_gross": 11125, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 2225, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-20"},
    {"hs_name": "Commission - 7750", "commission_gross": 7750, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 1550, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Awaiting CDA", "closed_date": "2026-05-30"},
    {"hs_name": "Commission - 10125", "commission_gross": 10125, "commission_split_basis": "Gross", "referral_fee_amount": 1000, "brokerage_split_percent": 0.20, "brokerage_amount": 2025, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Disbursement", "closed_date": "2026-06-01"},
    {"hs_name": "Commission - 13500", "commission_gross": 13500, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 2700, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-30"},
    {"hs_name": "Commission - 7250", "commission_gross": 7250, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 1450, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Awaiting CDA", "closed_date": "2026-05-31"},
    {"hs_name": "Commission - 4000", "commission_gross": 4000, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 800, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Paid", "payment_date": "2026-05-01", "closed_date": "2026-05-01"},
    {"hs_name": "Commission - 24000", "commission_gross": 24000, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 4800, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-20"},
    {"hs_name": "Commission - 9375", "commission_gross": 9375, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 1875, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Paid", "payment_date": "2026-05-01", "closed_date": "2026-05-01"},
    {"hs_name": "Commission - 18375", "commission_gross": 18375, "commission_split_basis": "Gross", "referral_fee_amount": 1500, "brokerage_split_percent": 0.20, "brokerage_amount": 3675, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Paid", "payment_date": "2025-11-15", "closed_date": "2025-11-15"},
    {"hs_name": "Commission - 10125", "commission_gross": 10125, "commission_split_basis": "Gross", "referral_fee_amount": 0, "brokerage_split_percent": 0.20, "brokerage_amount": 2025, "transaction_fee": 395, "e_o_insurance_fee": 50, "payment_status": "Pending Close", "closed_date": "2026-06-30"},
]


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

class Builder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.created: dict[str, list[str]] = {
            "contacts": [], "companies": [], "deals": [], "tickets": [],
            "listings": [], "showings": [], "offers": [], "open_houses": [], "commissions": [],
        }
        self.errors: list[dict[str, Any]] = []
        self.object_type_ids: dict[str, str] = {}  # name -> objectTypeId
        self.pipeline_stage_map: dict[str, dict[str, str]] = {}  # pipeline_label -> stage_label -> stage_id

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body or {})
        return resp.body

    async def _get(self, path: str) -> dict[str, Any]:
        resp = await self.client.get(path, portal_id=self.portal_id)
        return resp.body

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
            existing = await self._get(f"/crm/v3/schemas/{name}")
            if "objectTypeId" in existing:
                print(f"  Custom object {name} already exists")
                self.object_type_ids[name] = existing["objectTypeId"]
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
            # Store objectTypeId from response
            obj_id = resp.body.get("objectTypeId") or resp.body.get("id")
            if obj_id:
                self.object_type_ids[name] = str(obj_id)
            return name
        except Exception as exc:
            print(f"  ERROR creating custom object {name}: {exc}")
            self.errors.append({"action": "custom_object", "name": name, "error": str(exc)})
            return None

    async def refresh_object_type_ids(self) -> None:
        """Fetch all custom object schemas to populate objectTypeId mapping."""
        try:
            resp = await self._get("/crm/v3/schemas")
            for schema in resp.get("results", []):
                name = schema.get("name", "")
                obj_type_id = schema.get("objectTypeId", "")
                if name and obj_type_id:
                    self.object_type_ids[name] = obj_type_id
        except Exception as exc:
            print(f"  WARNING: could not refresh object type IDs: {exc}")

    async def build_pipeline_stage_map(self, object_type: str) -> None:
        """Fetch all pipelines and map stage labels to IDs."""
        try:
            resp = await self._get(f"/crm/v3/pipelines/{object_type}")
            for pipeline in resp.get("results", []):
                label = pipeline.get("label", "")
                self.pipeline_stage_map[label] = {}
                for stage in pipeline.get("stages", []):
                    stage_label = stage.get("label", "")
                    stage_id = stage.get("id", "")
                    if stage_label and stage_id:
                        self.pipeline_stage_map[label][stage_label] = stage_id
        except Exception as exc:
            print(f"  WARNING: could not build pipeline stage map for {object_type}: {exc}")

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
            await asyncio.sleep(0.1)
        return created_ids


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"No portal config found for {PORTAL_ID}")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = Builder(client, PORTAL_ID)

    try:
        # 1. Fix boolean properties on standard objects
        print("\n=== Fixing boolean properties ===")
        for object_type, prop in BOOLEAN_PROPERTIES_TO_FIX:
            await builder.create_custom_property(object_type, prop)

        # 2. Create missing custom objects (showings, offers)
        print("\n=== Creating missing custom objects ===")
        for key, schema in CUSTOM_OBJECTS_TO_CREATE.items():
            await builder.create_custom_object(schema)

        # 3. Refresh all objectTypeIds
        print("\n=== Refreshing object type IDs ===")
        await builder.refresh_object_type_ids()
        print(f"  Object type IDs: {builder.object_type_ids}")

        # 4. Build pipeline stage maps for deals
        print("\n=== Building pipeline stage maps ===")
        await builder.build_pipeline_stage_map("deals")
        for pipeline_label, stage_map in builder.pipeline_stage_map.items():
            print(f"  {pipeline_label}: {list(stage_map.keys())[:3]}... ({len(stage_map)} stages)")

        # 5. Create sample contacts
        print("\n=== Creating sample Contacts ===")
        await builder.batch_create_records("contacts", SAMPLE_CONTACTS)

        # 6. Create sample companies
        print("\n=== Creating sample Companies ===")
        await builder.batch_create_records("companies", SAMPLE_COMPANIES)

        # 7. Create sample listings (using name as object type)
        print("\n=== Creating sample Listings ===")
        listings_type = builder.object_type_ids.get("listings", "listings")
        await builder.batch_create_records(listings_type, SAMPLE_LISTINGS)

        # 8. Create sample deals (with stage ID mapping)
        print("\n=== Creating sample Deals ===")
        deals_to_create: list[dict[str, Any]] = []
        for template in DEAL_STAGE_TEMPLATES:
            pipeline_label = template["pipeline"]
            stage_label = template["dealstage_label"]
            stage_id = builder.pipeline_stage_map.get(pipeline_label, {}).get(stage_label, stage_label)
            deal = {k: v for k, v in template.items() if k not in ("dealstage_label",)}
            deal["dealstage"] = stage_id
            deals_to_create.append(deal)
        await builder.batch_create_records("deals", deals_to_create)

        # 9. Create sample tickets (default pipeline)
        print("\n=== Creating sample Tickets ===")
        await builder.batch_create_records("tickets", SAMPLE_TICKETS)

        # 10. Create sample showings
        print("\n=== Creating sample Showings ===")
        showings_type = builder.object_type_ids.get("showings", "showings")
        await builder.batch_create_records(showings_type, SAMPLE_SHOWINGS)

        # 11. Create sample offers
        print("\n=== Creating sample Offers ===")
        offers_type = builder.object_type_ids.get("offers", "offers")
        await builder.batch_create_records(offers_type, SAMPLE_OFFERS)

        # 12. Create sample open houses
        print("\n=== Creating sample Open Houses ===")
        oh_type = builder.object_type_ids.get("open_houses", "open_houses")
        await builder.batch_create_records(oh_type, SAMPLE_OPEN_HOUSES)

        # 13. Create sample commissions
        print("\n=== Creating sample Commissions ===")
        comm_type = builder.object_type_ids.get("commissions", "commissions")
        await builder.batch_create_records(comm_type, SAMPLE_COMMISSIONS)

        # Summary
        print("\n=== Summary ===")
        for obj_type, ids in builder.created.items():
            print(f"  {obj_type}: {len(ids)} created")
        if builder.errors:
            print(f"\n  {len(builder.errors)} errors encountered")
            for err in builder.errors[:20]:
                print(f"    {err}")
        else:
            print("\n  No errors!")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
