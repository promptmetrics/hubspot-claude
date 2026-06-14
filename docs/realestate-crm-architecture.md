# HubSpot CRM Architecture for a Real Estate Company

**Version:** 1.0
**Date:** 2026-05-09
**Audience:** RevOps, Brokerage owners, Sales/Listing managers, HubSpot administrators
**Scope:** End-to-end CRM design — object model, properties, associations, engagements, pipelines, automations, and reporting — for a residential real estate brokerage that also handles light commercial leasing and investor representation.

---

## 1. Why this design exists

Real estate is a relationship-driven, asset-centric business. A buyer or seller will transact every 5–10 years, but the underlying *property* outlives any single transaction. A standard CRM model that treats every interaction as a "Deal between a Contact and a Company" loses two things that matter to brokers: (1) the property itself as a long-lived record with its own history of listings, showings, offers, and owners, and (2) the dense network of supporting players (lenders, title officers, inspectors, attorneys, contractors) that determine whether a transaction closes.

This architecture extends HubSpot's standard four-object model (Contacts, Companies, Deals, Tickets) with five custom objects (Listings, Showings, Offers, Open Houses, Commissions) so that every aspect of the business — people, properties, transactions, marketing events, money — has a first-class home, can be reported on, and can hang engagement records (notes, calls, emails, meetings, tasks) off of it.

The design assumes HubSpot Sales Hub Professional or Enterprise (custom objects require Enterprise on Sales/Service Hub, or any Operations Hub tier). If the brokerage is on a tier without custom objects, every object below other than Contacts/Companies/Deals/Tickets degrades gracefully into a HubSpot list with strict naming conventions, but loses the ability to be associated and reported on natively — call this out before quoting the project.

---

## 2. Business context

A residential brokerage's day-to-day work has four loops, each of which the CRM must support:

The **lead loop** captures inbound interest from Zillow, the brokerage website, open house sign-ins, referrals, and past clients. Leads need to be qualified, routed to an agent within minutes, and nurtured for months or years before they're transaction-ready.

The **listing loop** runs from listing appointment to "sold" sign — preparing the property for market (photos, staging, repairs), pricing it, marketing it, hosting showings and open houses, fielding offers, and managing the seller through closing.

The **buyer loop** runs from initial interest to closing — qualifying the buyer, securing pre-approval, defining search criteria, touring properties, writing offers, negotiating, managing inspection and appraisal, and closing.

The **service loop** is everything that happens after closing — referrals, anniversary touches, maintenance referrals, eventual repeat business. Brokerages that win this loop get 60%+ of revenue from repeat-and-referral; those that don't fight for every lead.

Every object below earns its place by being something one of these loops needs to track over time, with multiple parties involved, and with reportable fields. If a piece of data doesn't meet that bar, it lives as a property on an existing object instead of a new one.

---

## 3. Object model overview

The full object model uses the four standard HubSpot objects plus four custom objects and one native object. Standard objects are battle-tested by HubSpot and benefit from native integrations; custom objects exist where standard objects can't represent the domain cleanly. HubSpot provides a native `listings` object (type ID `0-420`) as of 2025+ — this should be used rather than creating a custom listings object, because the native object already has 47 standard properties (address, price, beds/baths, etc.) and integrates with HubSpot's property search and mapping features.

The object inventory is:

| Object | Type | Purpose | Roughly how many per year (mid-size brokerage, 200 closings/yr) |
|---|---|---|---|
| Contact | Standard | Every individual person — buyers, sellers, tenants, lenders, attorneys, vendors, referral sources | 5,000–15,000 |
| Company | Standard | Every organization — partner brokerages, builders, lenders, title companies, HOAs, vendors | 200–800 |
| Deal | Standard | A specific transaction (buy-side, sell-side, lease) moving through a pipeline | 250–400 |
| Ticket | Standard | Service requests — pre-close issues, post-close support, repair coordination, complaints | 100–300 |
| Listing | Native (0-420) | A specific physical property — survives any single deal, can be relisted, rented, or sold multiple times across years | 200–300 |
| Showing (custom) | Custom | One scheduled tour of one Listing by one or more Contacts | 1,000–3,000 |
| Offer (custom) | Custom | A formal written offer on a Listing, with terms and status | 400–800 |
| Open House (custom) | Custom | A scheduled open-house event tied to a Listing | 150–300 |
| Commission (custom) | Custom | The commission payout record for a closed Deal — tracks splits, referral fees, brokerage cuts | 200–400 |

The reason for separating Listings from Deals is the most important design decision in this model. A Listing is a *thing in the world* — 123 Main Street. A Deal is a *transaction* — "the Smith family buying 123 Main Street in March 2026." 123 Main Street might be the subject of three Deals over a decade (sold in 2016, listed-and-withdrawn in 2022, sold again in 2026), and tracking it as one Listing record with three associated Deals gives the brokerage a property history that no Deal-only model can produce.

The reason for separating Offers from Deals is that, on the listing side, a single Listing routinely receives 3–10 offers before one is accepted. Treating each offer as a Deal pollutes the pipeline with 9 "Closed Lost" Deals for every "Closed Won" and makes win-rate reporting useless. Offers are their own object; the accepted Offer is what graduates into an active Deal.

The reason for separating Showings, Open Houses, and Commissions is that each has its own properties, reporting needs, and associations that don't fit cleanly on any standard object: showings need feedback and conversion tracking, open houses need attendee counts and lead-source attribution, and commissions need split percentages and payee references for accounting.

---

## 4. Standard objects in detail

### 4.1 Contact

The Contact object represents one human being. Every person the brokerage interacts with — past, present, or prospective — is a Contact. Personas are tracked via properties, not separate objects, so the same person can be a Buyer in 2026 and a Seller in 2032 without creating duplicate records.

**Why it's standard, not custom:** Contacts have ~30 native HubSpot integrations (Gmail, Outlook, Calendar, marketing emails, forms, ads, chat) that all break the moment you try to substitute a custom object.

**Key business questions this object answers:** Who are our active leads? Which past clients haven't been touched in 12+ months? Who are our top-producing referral sources? Which agent owns each lead?

**Properties:**

The standard HubSpot fields (firstname, lastname, email, phone, lifecyclestage, lead_status, hubspot_owner_id, createdate, hs_lifecyclestage_*_date) are all kept and used as-is. The lifecycle stages are the standard set (Subscriber → Lead → MQL → SQL → Opportunity → Customer → Evangelist → Other), with the brokerage's own definitions written into the property description so agents agree on what each stage means.

Custom contact properties to add are described below.

`contact_role` is a multi-select that captures every role this person currently plays: Buyer, Seller, Tenant, Landlord, Investor, Past Client, Sphere of Influence, Referral Partner, Vendor, Attorney, Lender Loan Officer, Title Officer, Inspector, Appraiser, Photographer, Stager, Contractor, Internal Agent. Multi-select because one person can be a Past Client *and* a Referral Partner simultaneously.

`buyer_qualification_status` is a single-select used during the buyer loop: Not Qualified, Pre-Qualified, Pre-Approved, Cash Buyer, Lost — Couldn't Qualify. Drives whether the lead gets routed to a senior agent.

`seller_motivation` is a single-select for sellers: Upgrading, Downsizing, Relocating, Investment Sale, Distressed, Estate Sale, Other. Influences pricing strategy and timeline.

`price_range_min` and `price_range_max` are number fields capturing the buyer's budget. Used by the search-criteria workflow to suggest matching Listings.

`preferred_areas` is a multi-line text or multi-select (depending on whether the brokerage operates in a fixed set of neighborhoods). Holds the buyer's target geography.

`bedrooms_min`, `bathrooms_min`, `square_feet_min`, `year_built_min` are number fields capturing minimum search criteria.

`property_types_of_interest` is a multi-select: Single Family, Condo, Townhome, Multi-Family, Land, Commercial, New Construction.

`timeline_to_buy` is a single-select: 0–30 days, 30–90 days, 3–6 months, 6–12 months, 12+ months, Just Browsing. Drives nurture cadence.

`current_home_owned` is a yes/no — affects whether they need a contingent offer.

`current_home_address` and `current_home_estimated_value` capture seller info for buyers who must sell to buy.

`lender_contact_id` and `attorney_contact_id` are association-style references to the buyer's preferred lender and attorney (implemented either via labeled associations on Contact–Contact or as text fields holding the Contact's HubSpot ID; the labeled-association approach is preferred because it keeps the relationship reportable).

`source_detail` complements the standard `hs_analytics_source` with brokerage-specific detail: Zillow Tech Connect, Realtor.com lead, Open House Sign-In, Past Client Referral, Sphere Referral, Vendor Referral, Walk-In, Sign Call, Online Form, Cold Call, Door Knocking, Geographic Farm.

`referred_by_contact_id` is a labeled association to the Contact who referred this person — critical for paying out referral fees and reporting on referral-source ROI.

`anniversary_date` is the closing date of their last transaction with the brokerage; powers the post-close anniversary workflow.

`do_not_contact_reason` is a single-select used when a Contact opts out, so the brokerage knows whether they unsubscribed from marketing only or from all contact: Marketing Only, All Contact, Hostile, Deceased, Moved Out of Service Area.

`gdpr_consent_date` and `gdpr_consent_basis` if the brokerage operates in or markets to EU/UK jurisdictions.

**Lifecycle stage logic for real estate** maps to the standard HubSpot stages with brokerage-specific definitions: Lead = inbound contact info captured but not yet qualified; MQL = lead has engaged with property-search emails or filled out a buyer/seller form; SQL = lead has had a real conversation with an agent and confirmed buying or selling intent; Opportunity = lead is in an active Deal pipeline (Buyer Pipeline ≥ "Touring", Seller Pipeline ≥ "Listing Appointment Done"); Customer = at least one Deal has closed-won; Evangelist = past customer has referred at least one closed-won Deal.

### 4.2 Company

The Company object represents an organization. In real estate, Companies are usually *not* the buyer or seller (those are Contacts) — they're the *supporting cast*: lenders, title companies, builders, partner brokerages, HOAs, vendors. The exception is investor accounts and commercial leases, where a Company can absolutely be on the principal side of the transaction.

**Why it's standard, not custom:** Companies feed naturally into Contacts (via the standard primary-company association) and Deals.

**Key business questions this object answers:** Which lenders are funding the most of our deals? Which partner brokerages do we co-op with most often? Which title companies have the cleanest closings? Are any HOAs creating recurring friction?

**Properties:**

Standard fields (name, domain, industry, phone, address, hubspot_owner_id, createdate) are kept.

`company_type` is a single-select that drives almost every report: Brokerage (Cooperating), Lender — Bank, Lender — Mortgage Broker, Lender — Hard Money, Title Company, Escrow Company, Law Firm, Inspection Company, Appraisal Firm, Photography / Media, Staging Company, General Contractor, Specialty Trade (Plumbing, Electric, Roofing, etc.), HOA / Property Manager, Builder / Developer, Investor — Individual LLC, Investor — Institutional, Insurance, Home Warranty, Marketing Vendor, Referral Partner, Other.

`primary_contact_id` is a labeled association to the main Contact at this Company.

`preferred_partner` is a yes/no flag. Brokerages keep a short list of "preferred" lenders, title companies, and inspectors they recommend to clients; this property powers a workflow that surfaces the right preferred-partner contact when a buyer reaches the appropriate stage.

`partnership_tier` is single-select (Tier 1, Tier 2, Backup, Avoid) and is used internally to rank vendors. Combined with a `partnership_notes` long-text field that captures *why* a vendor is rated as such.

`co_brokerage_split_default` is a percent field used when this Company is a cooperating brokerage on the other side of a deal — defaults the commission split.

`license_number` and `license_state` capture state-issued license info for any company that needs to be licensed (brokerages, lenders, contractors).

`insurance_expiry_date` for vendors — drives a workflow that warns the office manager when a contractor's insurance is about to lapse before referring them to a client.

`hoa_management_company` is a yes/no, and `hoa_dues_amount` and `hoa_dues_frequency` are properties that apply when company_type = HOA — used to populate listing data automatically when the same HOA covers multiple Listings.

`investor_focus` is a multi-select for investor accounts: Buy-and-Hold, Flip, Wholesale, BRRRR, Multifamily, Commercial, New Construction. Drives matching of off-market opportunities to investor interest.

### 4.3 Deal

The Deal object represents one transaction moving through a pipeline. Each side of a co-brokered transaction is a separate Deal — i.e., if your brokerage represents the buyer and the listing brokerage represents the seller, that's one Deal in your CRM. If you double-end (represent both), that's two Deals tied to the same Listing.

**Why it's standard, not custom:** Deals power HubSpot's pipeline, forecasting, and revenue reporting. Substituting a custom object for transactions costs you all of that.

**Key business questions this object answers:** What's in the pipeline this month? What's our weighted forecast? Which agent is closing fastest? What's our average DOM (days on market) by price band? Where in the funnel are we losing deals?

**Pipelines:** A real estate brokerage runs at least three Deal pipelines, possibly four:

The **Buyer Pipeline** runs deals where this brokerage represents the buyer. Stages: New Buyer Lead → Consultation Scheduled → Consultation Completed → Pre-Approved / Cash Verified → Active Search (Touring) → Offer Submitted → Under Contract → Inspection / Due Diligence → Appraisal → Loan Clear-to-Close → Closing Scheduled → Closed Won / Closed Lost. Probability percentages on each stage drive forecasting; calibrate them quarterly against actual conversion data.

The **Seller Pipeline** runs deals where this brokerage represents the seller. Stages: New Seller Lead → Listing Appointment Scheduled → Listing Appointment Completed → Pre-Listing Prep (Photos, Staging, Repairs) → Listing Live → Under Contract → Inspection Negotiation → Appraisal → Closing Scheduled → Closed Won / Closed Lost / Withdrawn / Expired. The Seller Pipeline is associated to a Listing record; the Buyer Pipeline may or may not be (depending on whether the buyer is under contract on a known property yet).

The **Lease Pipeline** runs rental transactions: New Tenant Lead → Application → Approved → Lease Signed → Move-In Scheduled → Active Lease → Renewed / Moved Out. Lease deals have lower commissions but high volume in some markets.

The **Investor / Off-Market Pipeline** runs deals where this brokerage represents an investor buying off-market or wholesale. Stages: Lead → Property Identified → LOI Submitted → Under Contract → Due Diligence → Closing → Closed. Optional — only set up if the brokerage actually has an investor practice.

**Properties (across all pipelines):**

Standard Deal fields (dealname, dealstage, pipeline, amount, closedate, hubspot_owner_id, dealtype, createdate) are kept. `amount` is the gross contract price (not commission). `closedate` is the contract close date — set tentatively at contract acceptance, updated as the schedule slips.

`commission_total` (currency) is the gross commission earned on this side of the deal — this is what drives revenue reporting, not `amount`.

`commission_percent` is the agent's commission rate (typically 2.5–3% for residential).

`buyer_side_or_seller_side` is a single-select: Buyer Side, Seller Side, Both Sides (Double End), Lease Side. Backstops the pipeline assignment in case someone files a deal in the wrong pipeline.

`property_address` is a free-text field denormalized from the associated Listing (when one exists). Stored on the Deal because a fair number of buyer-side Deals enter the pipeline before the buyer has a specific property identified, in which case there's no associated Listing yet.

`mls_number` denormalized from Listing.

`contract_date` is the date the purchase agreement was signed (≠ closedate, which is the closing date).

`contingency_inspection_deadline`, `contingency_appraisal_deadline`, `contingency_financing_deadline` are date fields. These are the legal deadlines from the contract; missing one is a six-figure mistake. Workflows fire reminder tasks 3 days before each deadline.

`earnest_money_amount` and `earnest_money_held_by` (text) capture EMD details for closing reconciliation.

`financing_type` is a single-select: Cash, Conventional, FHA, VA, USDA, Jumbo, Hard Money, Seller Financing, Other.

`buyer_lender_company_id` and `buyer_lender_loan_officer_contact_id` are labeled associations.

`title_company_id`, `escrow_company_id`, `attorney_company_id` are labeled associations.

`inspection_company_id` is a labeled association (often empty until the buyer schedules inspection).

`co_op_brokerage_id` is a labeled association to the cooperating brokerage Company.

`co_op_agent_contact_id` is a labeled association to the cooperating agent Contact.

`days_on_market_at_contract` is a number set at contract acceptance — used in seller-side reporting.

`list_price` (currency, denormalized from Listing) and `sale_price` (currency, = Deal amount) — having both lets you report list-to-sale price ratio.

`reason_lost` is a single-select used when dealstage = Closed Lost: Buyer Withdrew, Buyer Couldn't Qualify, Seller Withdrew, Inspection Killed Deal, Appraisal Killed Deal, Financing Fell Through, Title Issue, Better Offer Accepted, Buyer Found Other Property, Listing Expired, Withdrawn — Off Market, Other. Trains future pipeline.

`reason_lost_notes` is long-text.

`expected_close_date_changes` is a number that increments every time closedate moves — a leading indicator of a deal in trouble.

### 4.4 Ticket

The Ticket object represents a service issue, post-close support request, or transaction-coordination task that needs explicit tracking and resolution.

**Why it's standard, not custom:** Tickets get HubSpot's queue management, SLAs, and Service Hub features for free.

**Key business questions this object answers:** What's open right now? Are we hitting our SLAs on transaction-coordination tasks? Where are post-close issues clustering (specific home warranties? specific subdivisions?)? Which agents have the most service issues per closed deal — a quality signal?

**Pipelines:** Two Ticket pipelines — Transaction Coordination and Client Service.

**Transaction Coordination Pipeline** stages: New → Awaiting Documents → Sent for Signature → Signed → Filed With Brokerage → Closed. Used by transaction coordinators to track every required document from contract to close (inspection report, repair addenda, lender disclosures, HOA docs, title commitment, closing disclosure, etc.).

**Client Service Pipeline** stages: New → Triaged → In Progress → Awaiting Vendor → Awaiting Client → Resolved → Closed. Used for post-close issues, complaints, and repair-coordination requests.

**Properties:**

Standard fields (subject, content, hs_pipeline, hs_pipeline_stage, hubspot_owner_id, hs_ticket_priority, createdate) kept.

`ticket_category` is a single-select: Transaction Document, Inspection Repair, Closing Issue, Post-Close Repair, Home Warranty Claim, Vendor Coordination, Client Complaint, Compliance Issue, Lead Routing Issue, Other.

`related_deal_id` is a labeled association to the Deal this ticket belongs to.

`related_listing_id` is a labeled association to the Listing.

`vendor_company_id` is a labeled association if a vendor is doing the work.

`sla_due_date` is a date field, set by workflow based on category and priority.

`resolution_notes` is long-text, captured at close.

`client_satisfaction_rating` is a 1–5 number, optional, captured via NPS-style follow-up.

---

## 5. Custom objects in detail

Each custom object below assumes Sales/Service Hub Enterprise or Operations Hub Pro+, which is required to create custom objects. The objects are listed in dependency order — Listing comes first because it's referenced by all the others.

### 5.1 Listing (native object, type ID 0-420)

The Listing represents one specific physical property — a deed, an address, a parcel. It exists from the moment your brokerage starts tracking the property (which can be before it's listed; "coming soon" or "off market" Listings are common) and persists across multiple Deals over years.

**Why it's the native object, not custom:** HubSpot introduced a native `listings` object (type ID `0-420`) with 47 standard properties including `hs_address_1`, `hs_city`, `hs_state_province`, `hs_zip`, `hs_bedrooms`, `hs_bathrooms`, `hs_square_footage`, `hs_price`, `hs_year_built`, and `hs_listing_type`. The native object integrates with HubSpot's property search, mapping, and standard reporting. Custom properties are added via `/crm/v3/properties/0-420` to fill in brokerage-specific fields (MLS number, listing status, commission offered, off-market flags). Attempting to create a custom "listings" object will fail with a name-conflict error.

**Key business questions this object answers:** What's our active inventory? What's the median DOM by neighborhood? Which Listings have stalled — high showings but no offers? What's the property history of any address I'm typing into?

**Properties:**

**Native properties (47 built-in, do not recreate):** `hs_name` (required, use address as display name), `hs_address_1`, `hs_address_2`, `hs_city`, `hs_state_province`, `hs_zip`, `hs_bedrooms`, `hs_bathrooms`, `hs_square_footage`, `hs_price`, `hs_year_built`, `hs_listing_type` (valid values: `house`, `townhouse`, `multi_family`, `condos_co_ops`, `lots_land`, `apartments`, `manufactured`).

**Custom properties to add via API:** `mls_number` (text, primary unique-id field), `unit_number` (text), `county` (text), `subdivision` (text), `parcel_id` (text), `latitude` (number), `longitude` (number), `google_place_id` (text).

`listing_status` (single-select: Coming Soon, Active, Active Under Contract / Backup, Pending, Sold, Withdrawn, Expired, Off-Market — Pre-Listing, Off-Market — Investor, Cancelled), `original_list_price` (number), `list_date` (date), `expiration_date` (date), `withdrawal_date` (date), `sold_date` (date), `sold_price` (number), `days_on_market` (number), `price_per_square_foot` (number).

`listing_agent_contact_id` (text), `co_listing_agent_contact_id` (text), `listing_brokerage_company_id` (text), `listing_commission_offered_buyer_side` (number), `listing_commission_offered_seller_side` (number), `seller_contact_id` (text).

`professional_photos_url` (text), `virtual_tour_url` (text), `mls_remarks_public` (textarea), `mls_remarks_agent` (textarea), `marketing_started_date` (date), `signage_installed_date` (date).

`total_showings_count` (number), `total_offers_count` (number), `last_showing_date` (date), `total_open_houses_count` (number), `last_price_change_date` (date), `price_changes_count` (number).

`is_off_market` (bool), `off_market_reason` (single-select: Pre-Listing, Pocket Listing, Investor Hold, FSBO Watch, Foreclosure Watch, Probate Watch, Distressed, Expired Listing — Working Owner), `estimated_arv` (number), `estimated_rehab_cost` (number), `current_owner_contact_id` (text).

**Important:** All custom properties must be created in property group `listing_information` (with underscore). The native object ships with zero custom property groups, so this group must be created first or the property creation will fail.

### 5.2 Showing (custom object, type ID 2-202484491)

A Showing is one event: one Listing, one or more Contacts, one specific date and time. Tracking each showing is what lets you measure conversion (showings per offer, showings per close), capture buyer feedback, and report on listing-agent activity.

**Why it's a custom object:** Showings are first-class events with their own lifecycle (scheduled → completed → feedback received → converted). Treating them as Meetings (an engagement type) loses reportability and makes it impossible to ask "how many showings did this listing get last week?" without crunching engagement data.

**Key business questions this object answers:** Which Listings are getting shown but not offered on (a pricing or condition signal)? How many showings does the average buyer attend before writing? Which showing agents have the highest showing-to-offer conversion? Are buyer feedback themes clustering (kitchen, schools, traffic noise)?

**Properties:**

`showing_date` (datetime), `showing_status` (single-select: Scheduled, Confirmed, Completed, No-Show, Cancelled, Rescheduled), `showing_type` (single-select: Private Showing, Open House Attendance, Virtual Showing, Second Showing, Final Walkthrough, Inspection Walkthrough), `duration_minutes` (number).

Associations: `listing_id` (labeled association — the property), `attending_contact_ids` (labeled association — the buyer(s) and any spouse/family member; supports multiple), `showing_agent_contact_id` (labeled association — the agent who hosted; usually but not always the buyer's own agent), `listing_agent_at_time_contact_id` (labeled association — which listing agent represented the seller; can change if the listing rolls).

Outcome properties: `feedback_received` (yes/no), `feedback_rating` (single-select: Loved It, Liked It, Neutral, Didn't Like, Hated It), `feedback_likes` (long-text — what they liked), `feedback_concerns` (long-text — what they didn't), `objection_category` (multi-select: Price Too High, Condition Issues, Layout, Location, Schools, Traffic / Noise, Yard / Lot, HOA, Specific Repair Needed, Other), `would_consider_at_lower_price` (yes/no), `target_price` (currency — what they'd pay).

Conversion properties: `resulted_in_offer` (yes/no — set by workflow when an Offer is created on the same Listing by the same Contact), `resulted_in_offer_id` (labeled association to the Offer when applicable).

### 5.3 Offer (custom object, type ID 2-202484492)

An Offer is a formal written offer made on a Listing. Every Listing typically receives multiple Offers — many Listings receive 5–15 in hot markets — and only one becomes a Deal. Tracking each Offer separately gives the seller a full negotiation history and lets the brokerage report on offer activity that never converted.

**Why it's a custom object:** Offers have specific properties (offer price, terms, contingencies, expiration) that don't fit on Deal. Most Offers don't become Deals (they're rejected or beaten by another Offer), so they shouldn't pollute the Deal pipeline. The accepted Offer is what graduates into a Deal.

**Key business questions this object answers:** How many offers did this Listing get? What was the highest offer? What was the average list-to-offer ratio? Which buyer's agents are writing the most offers but losing the most? What contingency types are most common?

**Properties:**

`offer_amount` (currency), `offer_date` (date), `offer_status` (single-select: Submitted, Countered, Counter-Submitted, Accepted, Rejected, Withdrawn, Expired), `offer_type` (single-select: Initial, Counter, Best-and-Final, Backup), `expiration_date` (datetime — when the offer expires if not accepted).

Terms: `down_payment_amount` (currency), `down_payment_percent` (percent), `earnest_money_amount` (currency), `closing_date_proposed` (date), `financing_type` (single-select — same options as on Deal), `pre_approval_attached` (yes/no), `proof_of_funds_attached` (yes/no — for cash offers).

Contingencies: `contingency_inspection` (yes/no), `contingency_inspection_days` (number), `contingency_appraisal` (yes/no), `contingency_appraisal_days` (number), `contingency_financing` (yes/no), `contingency_financing_days` (number), `contingency_sale_of_home` (yes/no), `contingency_other` (long-text).

Concessions / extras: `seller_concessions_requested` (currency), `appliances_included` (multi-select: Refrigerator, Washer, Dryer, Hot Tub, Pool Equipment, Riding Mower, Other), `repairs_requested_at_offer` (long-text), `home_warranty_requested` (yes/no), `closing_costs_credit` (currency).

Associations: `listing_id` (labeled association — the property being offered on), `buyer_contact_ids` (labeled association — the buyer(s) making the offer), `buyer_agent_contact_id` (labeled association), `buyer_brokerage_company_id` (labeled association), `competing_offers_at_time` (number — how many other offers were on the table when this one was made), `accepted_into_deal_id` (labeled association — populated when this Offer becomes the accepted one and a Deal is created).

Win/loss properties: `lost_to_competing_offer_id` (labeled association — when rejected because another offer won), `lost_reason` (single-select: Price Too Low, Bad Terms, Contingencies Too Heavy, Closing Date Mismatch, Buyer Not Pre-Approved, Other Offer Accepted, Withdrawn by Buyer, Other).

### 5.4 Open House (custom object, type ID 2-202481647)

An Open House is a scheduled event where a Listing is open to the public for a window of time. Each Open House has its own set of attendees and produces leads.

**Why it's a custom object:** Open Houses generate measurable lead volume that needs to be attributed back. Treating them as Meetings loses attendee-count reporting and lead-source attribution.

**Key business questions this object answers:** How many leads is each Open House generating? Cost per lead by neighborhood? Conversion rate of Open House sign-ins to closed deals? Which agents host Open Houses that produce the most converting leads?

**Properties:**

`event_date` (datetime), `duration_minutes` (number), `event_type` (single-select: Public Open House, Broker's Open, Twilight Tour, Caravan), `event_status` (single-select: Scheduled, Live, Completed, Cancelled).

Marketing: `marketing_channels_used` (multi-select: MLS, Zillow, Realtor.com, Facebook Ad, Instagram Post, Yard Signs, Direct Mail, Email Blast, Door Knocking), `marketing_spend` (currency).

Outcomes: `attendee_count` (number), `sign_ins_collected` (number), `qualified_leads_generated` (number — sign-ins who became Lead-stage Contacts), `offers_received_within_72hrs` (number).

Associations: `listing_id` (labeled association), `host_agent_contact_ids` (labeled association — hosting agent(s); on-floor agents often co-host), `attendee_contact_ids` (labeled association — every sign-in becomes a Contact and gets associated here).

### 5.5 Commission (custom object, type ID 2-202481648)

A Commission represents the money side of a closed Deal — the gross commission earned, how it's split among agents and the brokerage, and any referral fees deducted.

**Why it's a custom object:** Real estate commission accounting is non-trivial — commission gets split between buyer-side and seller-side brokerages, then between brokerage and agent (per the agent's split agreement, which often has tiers), then has referral fees, transaction fees, and team splits deducted. Each leg of the split needs its own line item with its own payee. A simple amount-on-Deal property can't represent that.

**Key business questions this object answers:** What's each agent's earned commission YTD? What's the brokerage's net revenue per deal after splits? How much went to referral partners? Are any agents close to a split threshold (e.g., the 80/20 → 90/10 cap that triggers at $X in production)?

**Properties:**

`commission_gross` (currency — the gross commission earned on this side of the deal), `commission_split_basis` (single-select: Gross, Net After Brokerage Cut), `referral_fee_amount` (currency), `referral_fee_paid_to_contact_id` (labeled association — referring agent or partner), `referral_fee_paid_to_company_id` (labeled association — referring brokerage if applicable).

Brokerage cut: `brokerage_split_percent` (percent — what the brokerage keeps), `brokerage_amount` (currency, calculated), `transaction_fee` (currency — flat fee charged by brokerage), `e_o_insurance_fee` (currency).

Agent payouts: each Commission has one or more associated `commission_line_item` (sub-records, or modeled as labeled associations to Contacts with payout amounts as association properties — depending on whether the brokerage is on Operations Hub Enterprise, which supports association properties). Each line captures: `payee_contact_id` (labeled association), `payee_role` (single-select: Lead Agent, Co-Agent, Buyer's Agent, Listing Agent, Showing Agent, Team Lead Override, ISA Bonus, Other), `payout_percent_of_net` (percent), `payout_amount` (currency).

Status: `payment_status` (single-select: Pending Close, Awaiting CDA, Pending Disbursement, Paid, Disputed, Refunded), `payment_date` (date), `disbursement_authorization_signed_date` (date).

Associations: `deal_id` (labeled association — required, one Commission per Deal), `closed_date` (date, denormalized from Deal closedate).

---

## 6. Engagements

HubSpot's engagement records (Notes, Tasks, Calls, Meetings, Emails, and SMS via integration) attach to *any* CRM record — standard or custom. The architecture below specifies which engagement types are most important for each object and what conventions the brokerage should standardize on.

The first principle of engagements in real estate is that **the property is the timeline**. When an agent opens 123 Main Street, they should see every interaction that has ever touched that property: every showing, every offer, every note from the listing agent, every email to the seller, every call about an inspection issue. HubSpot's standard behavior is to roll up engagements from associated records onto the parent record's activity stream, so as long as engagements are logged against the *most specific* record possible, they aggregate up correctly.

The second principle is that **timer-driven engagements drive the business**. Real estate has hard deadlines (inspection contingency, financing contingency, closing date) and soft deadlines (follow up with this lead in 2 weeks, anniversary call in 11 months). Tasks with due dates, automated by workflows, are the operating system of a productive brokerage.

### 6.1 Notes

Notes capture context that doesn't fit into structured properties — listing agent's read of the seller's motivation, buyer's offhand comment about wanting to be near the school district, color from a phone call, photos taken during a private showing.

Notes should be logged against the most specific record they apply to: a note about a buyer's reaction during a Showing belongs on the Showing, not the Contact, because (a) it'll roll up to the Contact via association anyway, and (b) it's findable later when reviewing that Showing specifically.

Use note titles as a poor-man's tagging: "Pricing Discussion — 4/12", "Repair Request Conversation — 5/3", "Seller Mood Check — 4/28". Makes the activity stream scannable.

Voice-to-text on the mobile app is the productivity unlock here — agents who learn to dictate a 30-second note after every showing produce vastly more useful records than agents who try to type at the end of the day.

### 6.2 Tasks

Tasks are the engagement type that disproportionately determines whether a brokerage runs well. The convention should be:

Tasks always have an owner (assigned to a specific agent or coordinator, never to "the team"), a due date, and a queue (Buyer Tasks, Seller Tasks, Transaction Coordinator Tasks, Marketing Tasks, Service Tasks).

Workflow-generated tasks fire automatically at every contingency deadline, every required follow-up cadence, and every lifecycle transition. Examples: "Inspection contingency expires in 3 days — confirm objection deadline" (3 days before `contingency_inspection_deadline` on Deal); "Anniversary call due — last closing was 1 year ago today" (annual on `anniversary_date` for Customer-stage Contacts); "New buyer lead — make first contact within 5 minutes" (immediately on Contact creation when `lifecyclestage` = Lead and `contact_role` includes Buyer).

Task templates per object: Buyer Pipeline Deal stages each have a checklist of tasks that auto-create on entry; Seller Pipeline same; Listing has pre-listing prep checklist (order photos, schedule cleaner, install signage, write MLS remarks, schedule open house); Open House has setup checklist (signage, materials, sign-in sheet, refreshments).

### 6.3 Calls

Call records can be logged manually (after-the-fact, with notes) or captured automatically via a HubSpot calling integration (Aircall, Kixie, JustCall, RingCentral, native HubSpot Calling).

For real estate, the calling integration pays for itself within a quarter because (a) agents need transcripts of buyer-consultation calls to reference later, (b) listing-agent-to-listing-agent calls during negotiations should be on the Listing or Offer record so the next agent who picks it up has context, and (c) call disposition data ("connected", "left voicemail", "wrong number") is the single best leading indicator of pipeline health.

Required call dispositions to standardize on: Connected — Conversation, Connected — Brief, Left Voicemail, No Answer, Wrong Number, Bad Number, Not Interested, Do Not Call. Used in lead-routing reports.

Calls should be logged against the most specific record: an inspection-negotiation call belongs on the Deal; a buyer-consultation call belongs on the Contact (because no Deal exists yet); a listing-presentation follow-up call belongs on the Contact (the seller) but should also surface on the eventual Listing if they sign.

### 6.4 Meetings

Meetings (in-person or video) are logged against the records they pertain to. Standard real estate meeting types: Buyer Consultation (on Contact), Listing Appointment (on Contact, then back-associated to Listing once signed), Showing Tour (on Showing — yes, a Showing record can have a Meeting engagement attached for the calendar-block aspect), Open House (on Open House), Inspection Walkthrough (on Deal), Final Walkthrough (on Deal), Closing (on Deal).

Calendar integration with Google Calendar or Outlook Calendar is essential — meetings booked on the calendar should auto-create a Meeting engagement on the associated record via the connector. Without this, agents stop logging meetings within 60 days of go-live.

### 6.5 Emails

Emails are logged automatically via the HubSpot–Gmail or HubSpot–Outlook integration, with the BCC-to-HubSpot fallback for any email sent from outside the integrated client.

Emails to a Contact roll up to that Contact's activity stream automatically; emails to a Contact who is associated to an active Deal also surface on that Deal. This is why labeled associations matter — without them, emails to the buyer's lender don't surface on the Deal where they're most needed.

Email templates per stage: Buyer Pipeline has templates for first response, pre-approval request, search-criteria confirmation, listing send, offer follow-up, closing-day welcome. Seller Pipeline has templates for listing-appointment confirmation, pre-listing prep, listing-live announcement, weekly seller update, offer presentation. Past-Client cadence has templates for 30-day post-close, 6-month, anniversary, and seasonal touchpoints.

Sequences (Sales Hub Pro+) automate multi-step email-and-task cadences for nurture and follow-up — particularly valuable for the long-tail buyer ("12+ month timeline") where manual touchpoints don't scale.

### 6.6 SMS

SMS isn't native to HubSpot but is essential for real estate (response rates 4–6× higher than email for time-sensitive matters). Use a HubSpot-integrated SMS provider (Sakari, Salesmsg, ZipWhip via integration partners) so SMS messages log to the Contact's timeline.

SMS conventions: use SMS for time-sensitive matters only (showing confirmations, contingency reminders to clients, "we got the offer" notifications) — *never* for marketing without explicit TCPA-compliant opt-in, which most CRMs handle but the brokerage's compliance officer must sign off on.

### 6.7 Per-object engagement strategy summary

The matrix below shows which engagement types matter most for each object:

**Contact:** All engagement types. The Contact's activity stream is the source of truth for "what's the last thing we did with this person?" — a question agents ask 100× a day.

**Company:** Notes (vendor performance, partnership intel) and Calls (BD conversations with cooperating brokerages and lenders) are primary; Emails and Meetings secondary. Tasks are rare on Company except for partnership-management cadences.

**Deal:** Tasks dominate (every contingency deadline, every required transaction-coordination step). Notes are heavy during negotiation. Calls and Emails surface from associated Contacts but are also logged directly when they pertain to the deal as a whole (e.g., a 3-way call with both attorneys).

**Ticket:** Tasks for next-actions, Notes for resolution detail, Calls for vendor coordination.

**Listing:** Notes are the workhorse — pricing discussions, seller-mood check-ins, agent-to-agent intel. Tasks for pre-listing prep checklist and price-reduction follow-ups. Showings and Open Houses live as their own associated records (not engagements). Marketing emails to "prospective buyer" segments may surface here via association.

**Showing:** Notes (post-showing dictation by the agent) and Tasks (follow-up to the buyer, follow-up to the listing agent) are the primary engagement types. Meetings record the calendar block; Calls record the post-showing feedback call to the buyer's agent.

**Offer:** Notes (negotiation history — what was countered, what the seller said), Tasks (counter-deadline reminders), Emails (offer transmittal, response).

**Open House:** Tasks for pre-event prep; Notes for post-event recap (what worked, attendee themes); Emails (the post-event sign-in follow-up campaign).

**Commission:** Tasks only (CDA signature reminders, payout-overdue alerts). Engagement-light by design — Commission is mostly structured data, not conversation.

---

## 7. Associations

Associations are the wiring that makes the model navigable. HubSpot supports labeled associations on the standard four objects (Sales Hub Pro+) and on custom objects (Enterprise), which means each association can be tagged with a role (e.g., a Contact–Deal association can be labeled "Buyer", "Co-Buyer", "Seller", "Buyer's Lender", "Listing Agent", "Co-op Agent", etc.).

The full association map for this architecture is described below. Each row is one association type; the (M:N) cardinality and labels determine how each end of the relationship is queried.

### 7.1 Contact-centric associations

Contact ↔ Company is the standard primary-company relationship plus optional labeled secondary companies. Labels: Primary Employer, Affiliated Brokerage, Affiliated Lender, Vendor Of, Investor In.

Contact ↔ Contact (labeled, M:N) captures relationships among people. Labels: Spouse / Partner, Co-Buyer, Co-Seller, Referred By, Referred, Family Member, Business Partner, Attorney For, Lender For, Inspector For. The Referred By / Referred pair is the single most important Contact–Contact association — it powers referral-source reporting and is what your top agents already track in their heads.

Contact ↔ Deal (labeled, M:N) captures every person involved in a transaction. Labels: Buyer, Co-Buyer, Seller, Co-Seller, Buyer's Agent, Listing Agent, Co-Listing Agent, Cooperating Agent, Buyer's Lender — Loan Officer, Buyer's Attorney, Seller's Attorney, Title Officer, Inspector, Appraiser, Photographer, Stager, Other Vendor. Multi-select labels allow one Contact to play multiple roles on one Deal (e.g., spouse who is also co-buyer).

Contact ↔ Listing (labeled, M:N). Labels: Seller / Owner, Co-Owner, Listing Agent, Co-Listing Agent, **Agent** (for internal agents representing the listing), **Buyer**, Buyer Interested, Buyer Showed Property, Buyer Made Offer, Buyer Closed, Past Owner, Tenant. The Buyer Interested / Showed / Made Offer / Closed progression is what powers "show me everyone who has ever engaged with this property."

**Custom labels created during implementation:** `Agent` (typeId 197, contact→listing) / `Represented By Agent` (typeId 198, listing→contact); `Buyer` (typeId 199, contact→listing) / `Bought By` (typeId 200, listing→contact).

Contact ↔ Ticket (labeled, M:N). Labels: Reporter, Subject Of, Vendor Assigned, Resolver.

### 7.2 Company-centric associations

Company ↔ Company (labeled, M:N). Labels: Subsidiary Of, Partnered With, Competitor Of, Owns. Used for tracking brokerage-of-brokerage relationships and lender-of-lender chains.

Company ↔ Deal (labeled, M:N). Labels: Buyer's Brokerage, Listing Brokerage, Buyer's Lender, Title Company, Escrow Company, Buyer's Attorney's Firm, Seller's Attorney's Firm, Inspection Company, Appraisal Firm, Home Warranty Provider.

Company ↔ Listing (labeled, M:N). Labels: Listing Brokerage, HOA, Builder, Property Management, Past Listing Brokerage.

### 7.3 Deal-centric associations

Deal ↔ Listing (labeled, M:N — though most Deals associate to one Listing, leases can run multiple Deals over the life of one Listing). Labels: Subject Property, Backup Property, Investor Acquisition Of.

Deal ↔ Offer (labeled, 1:1 effectively but modeled as M:N for safety). Label: Accepted Offer. Only the accepted Offer associates to the Deal; the rejected/lost Offers stay associated to the Listing only.

Deal ↔ Commission (labeled, 1:1). Label: Commission Record.

Deal ↔ Ticket (labeled, 1:M). Labels: Transaction Coordination, Service Issue.

### 7.4 Listing-centric associations

Listing ↔ Showing (labeled, 1:M). Label: Showing.
Listing ↔ Offer (labeled, 1:M). Label: Offer.
Listing ↔ Open House (labeled, 1:M). Label: Open House.
Listing ↔ Listing (labeled, M:N). Labels: Comparable Sale, Adjacent Property, Replaces Listing (for relistings).
Listing ↔ Ticket (labeled, 1:M). Label: Property Issue.

### 7.5 Other custom-object associations

Showing ↔ Contact (labeled, M:N). Labels: Attendee, Showing Agent, Listing Agent At Time.
Showing ↔ Offer (labeled, M:N). Label: Resulted In Offer.
Offer ↔ Contact (labeled, M:N). Labels: Buyer, Co-Buyer, Buyer's Agent.
Offer ↔ Offer (labeled, M:N). Labels: Counter Of, Replaced By, Beat.
Open House ↔ Contact (labeled, M:N). Labels: Host Agent, Sign-In Attendee.
Commission ↔ Contact (labeled, M:N). Labels: Lead Agent Payee, Co-Agent Payee, Referral Payee, ISA Bonus Payee, Override Payee.

### 7.6 Why labels matter

Without labeled associations, a Deal with five associated Contacts is just "five people." With labels, you can write a workflow that says "send the closing-day welcome email to every Contact on this Deal where the association label is Buyer or Co-Buyer", and a report that says "show me every Listing where Contact X is associated with the label Buyer Closed". Labels turn the CRM from a place-things-go into a place-things-can-be-found.

The cost of labels is upfront discipline. Every brokerage that says "we'll add labels later" ends up with three years of unlabeled data that takes a six-figure data project to fix. Labels are configured in the first week of implementation and enforced via required-fields-on-association rules where the HubSpot tier supports them.

---

## 8. Pipelines and lifecycle stages

Pipelines are stages that a Deal (or Ticket) moves through. Lifecycle stages are stages that a Contact (or Company) moves through. The two systems are independent — a Contact can be in a Customer lifecycle stage while a Deal associated to them is in any pipeline stage.

### 8.1 Buyer Pipeline (Deal pipeline)

Pipeline ID: `3802390752`. Stages are linear; a Deal can move backward (e.g., from Under Contract back to Active Search if the deal falls through and the buyer keeps looking). Each stage has a probability used for forecasting, calibrated quarterly.

**New Buyer Lead** (5%) — Lead has been captured but no real conversation has happened. Workflow auto-creates a "first-contact-in-5-minutes" task.

**Consultation Scheduled** (15%) — A buyer consultation meeting is on the calendar.

**Consultation Completed** (25%) — Buyer consultation has happened; agent has captured needs, budget, timeline.

**Pre-Approved / Cash Verified** (40%) — Buyer has a pre-approval letter or proof of funds. Workflow creates a task to associate the Lender Contact and Company.

**Active Search (Touring)** (50%) — Buyer is actively touring properties. Should have ≥1 associated Showing within 14 days; workflow alerts the agent if they go stale.

**Offer Submitted** (65%) — At least one Offer has been written.

**Under Contract** (80%) — An Offer was accepted; the Listing this Offer was on becomes the Deal's subject property. Contingency-deadline tasks fire.

**Inspection / Due Diligence** (80%) — Inspection is happening; outcome might end the deal.

**Appraisal** (85%) — Appraisal is happening; outcome might end the deal or trigger a renegotiation.

**Loan Clear-to-Close** (95%) — Lender has issued CTC.

**Closing Scheduled** (98%) — Closing is on the calendar.

**Closed Won** (100%) — Closed and funded. Triggers Commission record creation, Customer lifecycle stage on the buyer Contact, anniversary workflow.

**Closed Lost** (0%) — Did not close. Requires `reason_lost`.

### 8.2 Seller Pipeline (Deal pipeline)

Pipeline ID: `3802299622`.

**New Seller Lead** (5%) — Inbound seller interest.

**Listing Appointment Scheduled** (15%) — Listing presentation on the calendar.

**Listing Appointment Completed** (30%) — Presentation done; awaiting signature.

**Pre-Listing Prep** (45%) — Listing agreement signed; photos / staging / repairs / pre-inspection happening. Listing record is created at this stage with status = Coming Soon.

**Listing Live** (55%) — On MLS, status = Active. Listing record's `list_date` is set.

**Under Contract** (75%) — An Offer has been accepted on the Listing; the accepted Offer associates to this Deal.

**Inspection Negotiation** (80%) — Inspection done; repair amendments under negotiation.

**Appraisal** (85%) — Appraisal happening.

**Closing Scheduled** (95%) — Closing on calendar.

**Closed Won** (100%) — Closed and funded. Listing status = Sold; Commission record created; seller Contact moves to Customer lifecycle; anniversary workflow.

**Closed Lost** (0%) — Did not close. Reasons: Withdrawn, Expired, Cancelled.

### 8.3 Lease Pipeline (Deal pipeline)

Lower-stakes, higher-volume version of the Buyer Pipeline. Stages: New Tenant Lead → Application Received → Application Approved → Lease Signed → Move-In Scheduled → Active Lease → Renewed / Moved Out. The Active Lease stage is a long-running parking lot — a Deal can sit there for a year or more — which is unusual for HubSpot but acceptable; the alternative (closing the Deal and reopening at renewal) loses continuity.

### 8.4 Investor / Off-Market Pipeline (Deal pipeline, optional)

Pipeline ID: `3802390753`.

For brokerages that work investors. Stages: Investor Lead → Property Identified → LOI Submitted → Under Contract → Due Diligence → Closing → Closed.

### 8.5 Transaction Coordination Pipeline (Ticket pipeline)

Used by transaction coordinators to track each required document. One Ticket per document type per Deal. Stages: New → Awaiting Documents → Sent for Signature → Signed → Filed With Brokerage → Closed.

### 8.6 Client Service Pipeline (Ticket pipeline)

For post-close issues, complaints, repair coordination. Stages: New → Triaged → In Progress → Awaiting Vendor → Awaiting Client → Resolved → Closed.

### 8.7 Contact lifecycle stages

The standard HubSpot lifecycle stages are kept, with brokerage-specific definitions documented in the property description and enforced via workflow:

**Subscriber** — Email captured (newsletter, blog) but no real estate intent expressed.

**Lead** — Inbound contact info captured with implicit or explicit real estate interest (filled out a property-search form, requested a home valuation, attended an open house).

**Marketing Qualified Lead (MQL)** — Lead has engaged with property-search emails, returned to the website ≥3 times, or filled out a buyer/seller form. Behaviorally qualified.

**Sales Qualified Lead (SQL)** — Has had a real conversation with an agent and confirmed buying or selling intent within a known timeline. Agent-qualified.

**Opportunity** — Associated to an active Deal in Buyer Pipeline ≥ Touring or Seller Pipeline ≥ Listing Appointment Done.

**Customer** — At least one Deal closed-won. Triggers anniversary workflow.

**Evangelist** — Past customer who has referred at least one closed-won Deal. Top of the food chain; gets concierge-level communication.

**Other** — Anyone outside the buyer/seller funnel: vendors, internal agents, etc. Usually combined with `contact_role` to disambiguate.

---

## 9. Automations and workflows

**API limitation:** As of 2025–2026, HubSpot does **not** expose a public POST endpoint for creating workflows or reports via API. The V4 Flows API (`/automation/v4/flows`) exists for graph-based automations but requires an entirely different payload structure from the UI builder and is not production-ready for complex real estate workflows. All workflows must be built manually in the HubSpot UI.

A companion document (`docs/WORKFLOWS_AND_REPORTS_SETUP_GUIDE.md`) provides the exact configuration for each workflow: trigger, enrollment criteria, actions, and branching logic, ready to be copied into the UI. The set below is the minimum recommended starting point; brokerages typically run 50–150 workflows once mature.

### 9.1 Lead-routing and speed-to-lead

When a new Contact is created with lifecycle = Lead and `contact_role` includes Buyer or Seller, route the Contact to an agent within 5 minutes of capture. Routing logic depends on the brokerage's structure — round-robin among on-floor agents, tiered by lead source quality, or geographic by `preferred_areas` / `current_home_address`. Workflow creates a high-priority task on the assigned agent and sends them an SMS via the SMS integration. If the task is not marked complete within 30 minutes, escalate to a senior agent and notify the team lead.

The single highest-ROI workflow in any real estate CRM is speed-to-lead. Industry research consistently shows lead conversion rates 5–10× higher when the first response happens within 5 minutes vs. 30+ minutes. This workflow is non-negotiable.

### 9.2 Buyer search-criteria matching

When a Buyer Contact is updated with `price_range_max`, `bedrooms_min`, `bathrooms_min`, or `preferred_areas`, search Listings in the CRM where `listing_status` is Active or Coming Soon and properties match, and email the agent a digest of matches. If the brokerage uses an MLS integration that pulls non-brokerage listings into the Listings object, this becomes a near-automatic property-search service.

### 9.3 Pre-listing prep checklist

When a Deal in Seller Pipeline moves to Pre-Listing Prep, create the associated Listing record (or link to existing Listing if relisting) with status = Coming Soon, and create a checklist of Tasks: order professional photos, schedule cleaner, schedule stager, install yard signage, write MLS public remarks, write MLS agent remarks, schedule first open house. Each Task has a default due date relative to the listing-go-live target.

### 9.4 Contingency deadline alerts

For every Deal in Buyer Pipeline ≥ Under Contract, fire a Task 3 days before each of `contingency_inspection_deadline`, `contingency_appraisal_deadline`, `contingency_financing_deadline`, and `closedate`. Subject: "Contingency [type] deadline in 3 days for [Deal name]". Owner: the Deal owner. Same for Seller Pipeline counterparts.

### 9.5 Showing follow-up

When a Showing is created with status = Scheduled, fire a confirmation SMS to the Buyer Contact 24 hours before. After the Showing is marked Completed, fire a Task to the showing agent: "Capture feedback from [buyer] within 24 hours". When `feedback_received` flips to yes, fire an Email to the listing agent with a templated feedback summary.

### 9.6 Offer presentation cadence

When an Offer is created with status = Submitted, fire a Task to the listing agent: "Present offer to seller within 24 hours". When `offer_status` flips to Accepted, automatically create a Deal in Seller Pipeline at stage Under Contract (if one doesn't exist) and Buyer Pipeline at stage Under Contract from the buyer's brokerage perspective (cross-brokerage workflows live in each side's CRM).

### 9.7 Open House lead processing

When a Contact is created with `source_detail` = Open House Sign-In and the Open House association is set, fire an Email to the Contact within 1 hour: "Thanks for visiting [address] today" with a link to similar listings. Fire a Task to the host agent the next morning: "Call [contact] to qualify". Fire a follow-up SMS on day 3 if no reply.

### 9.8 Stale-deal alerts

For every Deal in Buyer Pipeline ≥ Touring, if no associated Showing in the last 14 days, notify the Deal owner. For every Listing with status = Active, if `total_showings_count` in last 7 days is 0 and `days_on_market` ≥ 21, notify the listing agent and team lead — likely pricing problem.

### 9.9 Closing-day workflow

When a Deal moves to Closed Won, in parallel: create the Commission record, update the Listing status to Sold, set `sold_date` and `sold_price` on Listing, set the buyer/seller Contact's lifecycle stage to Customer, set their `anniversary_date` to today, fire the closing-day welcome email, schedule the 30-day post-close check-in Task, schedule the 6-month post-close Task, schedule the annual anniversary Task each year for the next 10 years.

### 9.10 Anniversary and nurture cadences

For every Customer-stage Contact, on each anniversary of `anniversary_date`, fire a Task to the original Deal owner: "Anniversary touch — call [contact] today". For Sphere-of-Influence and Past Client Contacts, run a year-round drip cadence: monthly market update email, quarterly handwritten note Task to the agent, birthday card Task on `birthday`. The cadence is high-value precisely because most agents stop touching past clients and lose them to the agent who didn't.

### 9.11 Vendor insurance and license expiry

For every Vendor / Partner Company with `insurance_expiry_date` or `license_expiry_date` within 30 days, fire a Task to the office manager: "Re-verify [vendor]'s insurance/license before next referral".

### 9.12 Compliance / data hygiene

Daily workflow: find Contacts with no `hubspot_owner_id` and route them. Weekly workflow: find Listings in Active status with stale activity and surface them. Monthly workflow: dedupe Contacts by email and phone, flagging matches for the office manager.

---

## 10. Reporting and dashboards

**API limitation:** As of 2025–2026, HubSpot does **not** expose a public POST endpoint for creating custom reports or dashboards. The Custom Report Builder and Dashboard UI must be used. A companion document (`docs/WORKFLOWS_AND_REPORTS_SETUP_GUIDE.md`) provides the exact data source, metrics, filters, and visualization type for each report, ready to be recreated in the UI.

A useful HubSpot real estate report set is built from properties on the objects above; nothing in this section requires custom code beyond the manual UI setup.

The **Pipeline Health Dashboard** shows current weighted pipeline by Buyer Pipeline and Seller Pipeline, projected close in next 30/60/90 days, average days in each stage (a leading indicator of bottlenecks), conversion rate stage-to-stage, and reason-lost breakdown for the trailing 90 days.

The **Listing Performance Dashboard** shows median days on market by neighborhood, price band, and listing agent; list-to-sale price ratio; showings per Listing; offers per Listing; and the showings-without-offers list (Listings receiving above-median showings but no offers — pricing or condition signal).

The **Lead Source ROI Dashboard** shows leads by `source_detail`, conversion rate from Lead to Customer by source, average commission revenue per closed-won Deal by source, and total marketing spend (from Open House `marketing_spend` and Company-level vendor spend) divided by attributed revenue.

The **Agent Performance Dashboard** shows each agent's pipeline value, closed-YTD GCI and net commission, average DOM on their listings, average days from contact to close on their buyers, ratio of listings to buyers, showing-to-offer conversion, and average time-to-first-touch on new leads (the speed-to-lead metric).

The **Service / Quality Dashboard** shows open Tickets by category and SLA compliance, post-close issues per closing by agent (a quality signal), and client satisfaction ratings.

The **Referral Engine Dashboard** shows top referral-source Contacts by GCI generated YTD, top referral-source Companies, and the count of Customers and Evangelists by their `referred_by_contact_id` — the direct measure of how well the past-client engine is running.

---

## 11. Implementation sequencing

A 90-day rollout that keeps the project from collapsing under its own weight is sequenced as follows.

The **first two weeks** focus on the standard objects: install HubSpot, configure Contacts and Companies with the custom properties listed above, configure Buyer and Seller Deal pipelines, configure Ticket pipelines, integrate Gmail/Outlook + Calendar + Calling provider, and set up the speed-to-lead workflow. Migrate Contact data from the existing CRM (typically Wise Agent, Follow Up Boss, kvCORE, BoomTown, or a spreadsheet); accept that the migration will lose some structured data and deduplicate aggressively.

**Weeks three through six** add the Listing custom object, the Showings custom object, and the Offer custom object. These three together unlock the property-history view that drives daily agent productivity. Wire the MLS integration if budget allows (RESO-compliant MLS APIs exist in most US markets via Trestle, Spark, or direct MLS feeds), or build a manual Listing-creation workflow with strict required-fields-on-create.

**Weeks seven through ten** add Open House and Commission custom objects, the full set of labeled associations, and the per-pipeline workflow library. By this point the brokerage has 3+ weeks of usage data and can calibrate workflow timing against actual agent behavior rather than guessing.

**Weeks eleven and twelve** add the dashboards and reports above, train the team on each pipeline, and run a cleanup pass to fix data-quality issues that surfaced during use. After that, expect a continuous-improvement rhythm of one workflow per month, one property per quarter, and one custom object every 12–18 months.

---

## 12. Decisions to make before implementation

Some decisions are brokerage-specific and need to be made up-front:

Whether to use HubSpot's native MLS integration (where available) or rely on manual Listing creation. Native is dramatically better but adds $400–$2,000/month depending on market.

Whether to put internal agents in the CRM as Contacts (with `contact_role` = Internal Agent) or as HubSpot Users only. Putting them as both — User for ownership / permissions, Contact for representation in associations and reporting — is the right answer but creates a sync responsibility (when an agent leaves, both records need to be deactivated).

How to handle co-buyer and co-seller couples — as one Contact with both names or as two associated Contacts. Two associated Contacts is the right answer because it preserves individual emails, phone numbers, and history, but it requires labeled-association discipline.

Whether the brokerage's commission split agreements are simple enough to live as properties on Commission, or complex enough to need sub-records. Most independent brokerages: properties suffice. Teams within larger brokerages: sub-records or a separate accounting system.

Whether the brokerage will adopt the Investor pipeline. Most don't need it; if the brokerage has any wholesale, off-market, or buy-and-hold investor business, it should.

How the brokerage handles compliance retention: closed-won transactions usually need to be kept for 5–7 years per state real estate commission rules. This affects the data-archival strategy — HubSpot retains data indefinitely on paid plans, but the brokerage's compliance officer should sign off on the export-and-archive routine for closed transactions in case of an audit.

---

## 13. What this design deliberately does not do

A few things that look like they belong in this architecture but should live elsewhere:

**Document storage** — HubSpot has files, but contracts, disclosures, inspection reports, and closing documents should live in a transaction-management system (Dotloop, SkySlope, Brokermint, dotloop) that integrates with HubSpot via API or attachment links. CRMs are bad at versioned documents.

**Accounting** — Commission tracking is in HubSpot; ledger and 1099 reporting are in QuickBooks or a brokerage-specific system (Brokermint, Lone Wolf, AccountTECH). Sync via API or weekly export.

**MLS data of record** — HubSpot Listings are a *projection* of MLS data plus brokerage-specific properties, not a substitute for MLS. The MLS is the system of record for listing data; HubSpot is the system of record for relationship and transaction data.

**Marketing automation at scale** — HubSpot Marketing Hub handles brokerage-scale email and ad campaigns well; for hyper-local geographic farming with direct mail and IDX-driven property alerts, kvCORE or BoomTown remain stronger and many brokerages run them in parallel with HubSpot via a contact-sync integration.

**Showing scheduling tools** — ShowingTime, Aligned Showings, and similar tools are what listing agents use to coordinate showings across cooperating agents; the Showing custom object in HubSpot captures the *record* of a showing for reporting, but the scheduling itself happens in those tools and syncs in.

A clear-eyed view of where HubSpot is the system of record vs. where it's a downstream consumer is what keeps the architecture sustainable; the brokerage that tries to make HubSpot do everything ends up with a fragile system that does many things badly.

---

## 14. Summary

This architecture extends HubSpot's standard four-object model with four custom objects (Showings, Offers, Open Houses, Commissions) and one native object (Listings) to cover every aspect of a residential real estate brokerage's operation. The model treats *people* as Contacts with role-flagged personas, *organizations* as Companies, *transactions* as Deals across four pipelines (Buyer, Seller, Lease, Investor), *physical properties* as long-lived Listings that survive any single transaction, *touring* as Showings, *offer activity* as Offers (separate from Deals so the pipeline reflects only contract-stage transactions), *marketing events* as Open Houses, *money* as Commissions with split tracking, and *issues* as Tickets across two pipelines (Transaction Coordination and Client Service). Every object hangs the full HubSpot engagement set — Notes, Tasks, Calls, Meetings, Emails, SMS — with conventions documented per object, and labeled associations wire them into a navigable graph that supports reporting on pipeline health, listing performance, lead-source ROI, agent performance, service quality, and the referral engine. A 12-week phased rollout sequences standard objects first, custom objects second, and reports last, with explicit decision points called out for the brokerage's MLS integration, internal-agent representation, co-buyer modeling, commission complexity, investor practice, and compliance retention.

---

## 15. Implementation Notes (Post-Build Corrections)

This section captures corrections, discoveries, and decisions made during the actual build in portal `148408595` that differ from the original architecture document.

### 15.1 Object Model

- **Listing is native, not custom.** HubSpot object type ID `0-420`. It has 47 built-in properties. Do not attempt to create a custom "listings" object — it will conflict.
- **Custom object type IDs assigned:** Showings `2-202484491`, Offers `2-202484492`, Open Houses `2-202481647`, Commissions `2-202481648`.

### 15.2 Property Corrections

- **Native listing properties** (do not recreate): `hs_name` (required), `hs_address_1`, `hs_address_2`, `hs_city`, `hs_state_province`, `hs_zip`, `hs_bedrooms`, `hs_bathrooms`, `hs_square_footage`, `hs_price`, `hs_year_built`, `hs_listing_type`.
- **Valid `hs_listing_type` values** (lowercase): `house`, `townhouse`, `multi_family`, `condos_co_ops`, `lots_land`, `apartments`, `manufactured`.
- **Custom property group** for listings: `listing_information` (underscore, not camelCase). The native object has zero custom property groups initially; this group must be created first.
- **`contact_role` valid values** (enumeration): Buyer, Seller, Tenant, Landlord, Investor, Past Client, Sphere of Influence, Referral Partner, Vendor, Attorney, Lender Loan Officer, Title Officer, Inspector, Appraiser, Photographer, Stager, Contractor, Internal Agent. "Other Agent" is not valid — use "Internal Agent".
- **`company_type` valid value** for brokerages: "Brokerage (Cooperating)" (not "Brokerage").
- **`buyer_qualification_status` valid values**: Not Qualified, Pre-Qualified, Pre-Approved, Cash Buyer, Lost — Couldn't Qualify. "Not Started" is not valid.
- **`ticket_category` valid values**: Transaction Document, Inspection Repair, Closing Issue, Post-Close Repair, Home Warranty Claim, Vendor Coordination, Client Complaint, Compliance Issue, Lead Routing Issue, Other. "Inspection Issue" is not valid.
- **`offer_status` valid values**: Submitted, Countered, Counter-Submitted, Accepted, Rejected, Withdrawn, Expired. "Pending" is not valid.
- **`offer_type` valid values**: Initial, Counter, Best-and-Final, Backup. "Purchase" is not valid.
- **`showing_type` valid values**: Private Showing, Open House Attendance, Virtual Showing, Second Showing, Final Walkthrough, Inspection Walkthrough. "Open House" is not valid.
- **`feedback_rating` valid values** (enumeration): Loved It, Liked It, Neutral, Didn't Like, Hated It. Numeric values like "4" are rejected.
- **`commission_split_basis` valid values**: Gross, Net After Brokerage Cut. "50/50 Split" is not valid.
- **`payment_status` valid values**: Pending Close, Awaiting CDA, Pending Disbursement, Paid, Disputed, Refunded. "Pending" is not valid.
- **`event_type` valid values**: Public Open House, Broker's Open, Twilight Tour, Caravan. "Open House" is not valid.
- **`marketing_channels_used` valid values** (multi-select): MLS, Zillow, Realtor.com, Facebook Ad, Instagram Post, Yard Signs, Direct Mail, Email Blast, Door Knocking. Free-text comma-separated values are rejected.

### 15.3 Pipeline IDs (Portal 148408595)

| Pipeline | ID |
|---|---|
| Buyer Pipeline | `3802390752` |
| Seller Pipeline | `3802299622` |
| Investor Pipeline | `3802390753` |
| Ticket Pipeline | `0` (default) |

### 15.4 Lists

Created 18 lists via API (`/crm/v3/lists`):
- 10 manual lists (`MANUAL` processing type): `[RE] All Buyers`, `[RE] All Sellers`, `[RE] Past Clients`, `[RE] Sphere of Influence`, `[RE] Investors`, `[RE] Referral Partners`, `[RE] Active Listings`, `[RE] Open House Attendees`, `[RE] Pending Commissions`, `[RE] Preferred Vendors`.
- 8 dynamic lists (`DYNAMIC` processing type with `filterBranch`): `[RE] Active Buyers — Touring`, `[RE] Hot Leads — 0-30 Days`, `[RE] Nurture — 12+ Months`, `[RE] Stale Listings — 21+ DOM`, `[RE] Under Contract — Buyer Side`, `[RE] Under Contract — Seller Side`, `[RE] Closed Won — This Quarter`, `[RE] Customers for Anniversary`.

**Key discovery:** The Lists API uses `MANUAL` (not `STATIC`) for static lists, and requires a root `filterBranchType: "OR"` wrapping nested `AND` branches.

### 15.5 Workflows and Reports

- **Workflows cannot be created via API.** The V4 Flows API (`/automation/v4/flows`) uses a graph-based format (nodes, edges, `actionTypeId`) that is completely different from the UI builder. All 15 workflows must be built manually in the HubSpot UI. A manual setup guide (`docs/WORKFLOWS_AND_REPORTS_SETUP_GUIDE.md`) documents each trigger, action, and branch.
- **Reports and dashboards cannot be created via API.** No public POST endpoint exists. All 14 reports across 6 dashboards must be built manually in the Custom Report Builder UI. The setup guide documents data source, metrics, filters, and visualization for each.

### 15.6 Associations

**Custom association definitions created** (via `/crm/v4/associations/{from}/{to}/labels`):
- Showings ↔ Listings: `Showing For Listing` / `Has Showing`
- Contacts ↔ Showings: `Attended Showing` / `Attendee`
- Offers ↔ Listings: `Offer For Listing` / `Has Offer`
- Contacts ↔ Offers: `Made Offer` / `Offered By`
- Commissions ↔ Deals: `Commission For Deal` / `Has Commission`
- Open Houses ↔ Listings: `Open House For Listing` / `Has Open House`

**New custom labels for contacts→listings:**
- `Agent` (typeId 199, contact→listing) / `Represented By Agent` (typeId 200, listing→contact)
- `Buyer` (typeId 201, contact→listing) / `Bought By` (typeId 202, listing→contact)

### 15.7 Engagements

All engagement types require `hs_timestamp` (datetime in ISO 8601 format). Without it, the API returns: `Error creating NOTE/TASK/MEETING_EVENT/CALL/EMAIL. Some required properties were not set. Properties: [hs_timestamp].`

Valid `hs_meeting_outcome` values: `SCHEDULED`, `COMPLETED`, `RESCHEDULED`, `NO_SHOW`, `CANCELED` (all uppercase).

### 15.8 Sample Data

A sample data script (`scripts/build_sample_data.py`) creates 8 contacts, 2 companies, 2 listings, 3 deals, 2 tickets, 2 showings, 1 offer, 1 commission, 1 open house, 18 associations, and 5 engagements. It includes duplicate detection via the search API and uses only confirmed valid enum values.

**Duplicate detection required:** Emily Davis and several other contacts existed from prior runs. The script skips existing records by searching via email, name, or MLS number before creation.

### 15.9 Build Scripts

All automation scripts live in `scripts/`:
- `fix_native_listings_properties.py` — adds 40 custom properties to native listings
- `build_realestate_lists.py` — creates 18 manual and dynamic lists
- `build_sample_data.py` — creates sample records, associations, and engagements
- `docs/WORKFLOWS_AND_REPORTS_SETUP_GUIDE.md` — manual setup instructions for 15 workflows and 14 reports
