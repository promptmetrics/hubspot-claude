# Real Estate CRM — Manual Setup Guide

## Portal: 148408595

The following components **cannot be created via public HubSpot API** and must be built manually in the HubSpot UI.

---

## Workflows (Section 9)

**Location:** Settings > Automation > Workflows

### 9.1 [RE] Lead Routing — Speed to Lead
- **Type:** Contact-based
- **Trigger:** Contact is created AND `lifecyclestage = lead`
- **Actions:**
  1. Create task: *"Speed-to-lead: Contact new lead within 5 minutes"* → assign to `hubspot_owner_id`, due in 5 min, HIGH priority
  2. Send internal email notification to `hubspot_owner_id` → *"New lead assigned: {{contact.firstname}} {{contact.lastname}}"*
  3. Delay 30 minutes
  4. If task status is NOT completed → Create escalation task for team lead due in 15 min, HIGH priority

### 9.2 [RE] Buyer Criteria Match — Agent Digest
- **Type:** Contact-based
- **Trigger:** `price_range_max` is known OR `preferred_neighborhoods` is known
- **Actions:**
  1. Delay 1 hour
  2. Create task: *"Send matching listings to {{contact.firstname}}"* → assign to owner, due in 1 day

### 9.3 [RE] Pre-Listing Prep Checklist
- **Type:** Deal-based
- **Trigger:** Deal stage moves to *Pre-Listing*
- **Actions:**
  1. Set property `listing_status = Off-Market - Pre-Listing`
  2. Create task: *"Order professional photos"* due in 3 days
  3. Create task: *"Schedule staging consultation"* due in 5 days
  4. Create task: *"Complete CMA and pricing strategy"* due in 7 days
  5. Create task: *"Confirm MLS entry date"* due in 10 days

### 9.4 [RE] Buyer Contingency — Inspection Alert
- **Type:** Deal-based
- **Trigger:** `inspection_deadline` is known AND deal stage = *Under Contract*
- **Actions:**
  1. Create task: *"Schedule inspection"* due 3 days before deadline
  2. Delay until 1 day before `inspection_deadline`
  3. If inspection not completed → Create escalation task for team lead

### 9.5 [RE] Buyer Contingency — Appraisal Alert
- **Type:** Deal-based
- **Trigger:** `appraisal_deadline` is known AND deal stage = *Under Contract*
- **Actions:**
  1. Create task: *"Confirm appraisal ordered"* due 5 days before deadline
  2. Delay until 2 days before `appraisal_deadline`
  3. If appraisal not completed → Create escalation task

### 9.6 [RE] Buyer Contingency — Financing Alert
- **Type:** Deal-based
- **Trigger:** `financing_deadline` is known AND deal stage = *Under Contract*
- **Actions:**
  1. Create task: *"Confirm loan commitment"* due 5 days before deadline
  2. Delay until 2 days before `financing_deadline`
  3. If financing not cleared → Create escalation task

### 9.7 [RE] Showing — Post-Showing Feedback Task
- **Type:** Custom object (Showings)
- **Trigger:** Showing record is created
- **Actions:**
  1. Delay 2 hours after showing `showing_datetime`
  2. Create task: *"Collect buyer feedback from showing {{showing.id}}"* → assign to showing agent

### 9.8 [RE] Offer — Present to Seller within 24h
- **Type:** Custom object (Offers)
- **Trigger:** Offer record is created
- **Actions:**
  1. Create task: *"Present offer to seller"* due in 24 hours → assign to listing agent
  2. Delay 24 hours
  3. If offer status is still *Pending Presentation* → Create escalation task

### 9.9 [RE] Open House — New Sign-In Follow-Up
- **Type:** Contact-based
- **Trigger:** Contact is added to list `[RE] Open House Attendees`
- **Actions:**
  1. Delay 2 hours
  2. Send marketing email: *"Thanks for visiting {{open_house.address}}"*
  3. Delay 2 days
  4. Create task: *"Follow up with open house attendee {{contact.firstname}}"*

### 9.10 [RE] Stale Buyer Deal — No Showings in 14 Days
- **Type:** Deal-based
- **Trigger:** Deal stage = *Active Buyer* AND `last_showing_date` is more than 14 days ago
- **Actions:**
  1. Create task: *"Re-engage buyer — no showings in 14 days"* → assign to agent
  2. Send internal email to deal owner

### 9.11 [RE] Stale Listing — High DOM, No Showings
- **Type:** Listing-based (native object)
- **Trigger:** `listing_status = Active` AND `days_on_market > 21` AND `total_showings_count = 0`
- **Actions:**
  1. Create task: *"Listing stale — review pricing and marketing"* → assign to listing agent
  2. Set property `price_alert_sent = true`

### 9.12 [RE] Closing Day — Post-Close Sequence
- **Type:** Deal-based
- **Trigger:** Deal stage moves to *Closed Won*
- **Actions:**
  1. Set property `lifecyclestage = customer`
  2. Set property `anniversary_date = {{today}}`
  3. Create task: *"30-day check-in call"* due in 30 days
  4. Create task: *"6-month anniversary touch"* due in 6 months
  5. Create task: *"1-year anniversary gift"* due in 1 year
  6. Add contact to list `[RE] Past Clients]`

### 9.13 [RE] Anniversary Touch — Annual Check-In
- **Type:** Contact-based
- **Trigger:** `[RE] Customers for Anniversary` list membership AND today's date = `anniversary_date`
- **Actions:**
  1. Send marketing email: *"Happy Home-iversary!"*
  2. Create task: *"Send anniversary card/gift"* due in 3 days

### 9.14 [RE] Vendor — Insurance/License Expiry Alert
- **Type:** Company-based
- **Trigger:** `license_expiration_date` is known AND is in next 60 days
- **Actions:**
  1. Create task: *"Vendor license expiring — follow up"* due 30 days before expiry
  2. Delay until 7 days before expiry
  3. If license status still active → Create escalation task

### 9.15 [RE] Hygiene — Unassigned Contact Routing
- **Type:** Contact-based
- **Trigger:** `hubspot_owner_id` is unknown AND contact is created
- **Actions:**
  1. Rotate to team (round-robin)
  2. Create task: *"New lead auto-assigned — confirm contact within 5 min"*

---

## Reports & Dashboards (Section 10)

**Location:** Reports > Dashboards

### Pipeline Health Dashboard
1. **[RE] Weighted Pipeline by Stage**
   - Data source: Deals
   - Metrics: Deal amount, Deal stage
   - Filter: Deal stage is not Closed Lost
   - Visualization: Funnel

2. **[RE] Projected Close (Next 90 Days)**
   - Data source: Deals
   - Metrics: Deal amount, Close date
   - Filter: Close date in next 90 days
   - Visualization: Line

3. **[RE] Reason Lost (Trailing 90 Days)**
   - Data source: Deals
   - Metrics: Reason lost
   - Filter: Deal stage = Closed Lost
   - Visualization: Pie

### Listing Performance Dashboard
4. **[RE] Median DOM by Neighborhood**
   - Data source: Listings
   - Metrics: Days on market, Subdivision
   - Filter: Listing status is Active or Sold
   - Visualization: Bar

5. **[RE] List-to-Sale Price Ratio**
   - Data source: Deals
   - Metrics: List price, Amount (sale price)
   - Filter: Deal stage = Closed Won
   - Visualization: Bar

6. **[RE] Showings per Listing**
   - Data source: Listings
   - Metrics: Total showings count, MLS number
   - Group by: Listing agent
   - Visualization: Bar

### Lead Source ROI Dashboard
7. **[RE] Leads by Source Detail**
   - Data source: Contacts
   - Metrics: Source detail
   - Visualization: Bar

8. **[RE] Conversion Rate by Source**
   - Data source: Contacts
   - Metrics: Source detail, Lifecycle stage
   - Visualization: Stacked bar

### Agent Performance Dashboard
9. **[RE] Agent Pipeline Value**
   - Data source: Deals
   - Metrics: Amount
   - Filter: Deal stage is not Closed Lost
   - Group by: Owner
   - Visualization: Bar

10. **[RE] Agent Closed YTD Revenue**
    - Data source: Deals
    - Metrics: Commission total
    - Filter: Deal stage = Closed Won AND Close date in this year
    - Group by: Owner
    - Visualization: Bar

### Service Quality Dashboard
11. **[RE] Open Tickets by Category**
    - Data source: Tickets
    - Metrics: Ticket category
    - Filter: Priority is High/Medium/Low
    - Visualization: Pie

12. **[RE] Client Satisfaction Rating**
    - Data source: Tickets
    - Metrics: Client satisfaction rating
    - Filter: Rating is known
    - Visualization: Bar

### Referral Engine Dashboard
13. **[RE] Top Referral Sources by GCI**
    - Data source: Deals
    - Metrics: Commission total
    - Filter: Deal stage = Closed Won
    - Group by: Referred by
    - Visualization: Bar

14. **[RE] Customers vs Evangelists**
    - Data source: Contacts
    - Metrics: Lifecycle stage
    - Filter: Lifecycle stage is Customer or Evangelist
    - Visualization: Donut

---

## Automation Notes

- **Workflow branching** requires the V4 Flows API `STATIC_BRANCH` action type (`actionTypeId` varies). Branch conditions are configured in the `fields` object with `trueActionId` and `falseActionId` edges.
- **Send Email** actions (`actionTypeId: 0-4`) require a pre-existing marketing email `content_id`.
- **Reports** and **Dashboards** have no public POST endpoint in the HubSpot API as of 2026. They must be created via the Custom Report Builder UI.
