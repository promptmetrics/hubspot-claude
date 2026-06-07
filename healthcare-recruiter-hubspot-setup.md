# HubSpot CRM Setup Blueprint — Healthcare B2B Recruiter

**Business model:** B2B recruitment for healthcare (clinics, hospitals). Fee = 1 month of placed candidate's salary per successful hire. Two-sided business: sell side (client companies) and supply side (candidates).

**HubSpot tier:** Sales/Service Hub Professional (no Custom Objects).

**System scope:** HubSpot is the sole system — replaces a dedicated ATS.

---

## 1. Object Architecture (the big picture)

| Object | Represents | Notes |
|---|---|---|
| **Companies** | Clinics, hospitals, healthcare networks (clients) | Standard. One per legal entity. |
| **Contacts** | Two populations, segmented by property: (a) Hiring managers / HR contacts at clients, (b) Job candidates | Segregated via `Contact Type` property. Marketing discipline is critical — see §11. |
| **Services** | Each open job requisition at a client | One Service = one open role. Closes when filled or cancelled. |
| **Deals** | Commercial revenue per requisition | One Deal per Service. Deal amount = expected fee (≈ 1 month placed salary). |
| **Tickets (Pipeline A)** | Candidate Applications | Each application = one Ticket. Stages = the candidate journey. |
| **Tickets (Pipeline B)** | Post-placement Client Support | Replacement requests, guarantee claims, client issues. |

The relationships look like this:

```
Company (Mercy Hospital)
  ├── Contact (Sarah, VP Nursing — Hiring Manager)
  ├── Service (RN, Night Shift — open req)
  │     ├── Deal (Mercy — RN Night Shift, $7,500 expected fee)
  │     └── Tickets [Pipeline A: Applications]
  │           ├── Ticket (Candidate Maria — Stage: Interviewing)
  │           ├── Ticket (Candidate James — Stage: Offer)
  │           └── Ticket (Candidate Lin — Stage: Rejected)
  └── Ticket [Pipeline B: Support] (Replacement claim — guarantee period)

Contact (Maria, RN candidate)
  └── associated to Ticket (Application to Mercy RN Night Shift)
```

---

## 2. Companies — Clients

Standard HubSpot Company object. Add these custom properties:

- **Client Type** (dropdown): Hospital / Clinic / Urgent Care / Long-Term Care / Specialty Practice / Other
- **Facility Size — Bed Count** (number)
- **Specialties** (multi-checkbox): Cardiology, Oncology, Emergency, Pediatrics, etc.
- **Master Services Agreement Signed** (date)
- **MSA Expiry** (date)
- **Fee % of Annual Salary** (number, default 8.33 — i.e., 1/12) — overrideable per client
- **Replacement Guarantee Period (days)** (number, default 90)
- **Net Payment Terms (days)** (number, default 30)
- **Preferred Recruiter** (HubSpot user) — for routing
- **Account Status** (dropdown): Prospect / Active / Paused / Lost / Do-Not-Pursue

---

## 3. Contacts — Two Populations, One Object

The single biggest discipline issue on Professional tier. Both hiring managers and candidates live as Contacts; the entire setup hinges on cleanly separating them.

### Required segmentation property

**Contact Type** (single-select, REQUIRED on creation):
- Hiring Manager
- Candidate
- Both (rare — e.g., a recruiter at a client who also applies later)
- Other (vendor, internal staff)

Every list, workflow, sequence, and marketing send MUST filter on this. Make it required and put it at the top of the contact record card.

### Hiring Manager properties

- **Title** (standard)
- **Decision-making Role** (dropdown): Decision Maker / Influencer / Gatekeeper / End User
- **Department** (dropdown): Nursing / Physician Services / Allied Health / Admin / HR
- **Account Owner** (HubSpot user)

### Candidate properties (the meat of the supply side)

Healthcare recruiting is licensure-heavy and specialty-driven. Build these now:

- **Candidate Status** (dropdown): New / Screening / Active / Placed / Cold / Do-Not-Contact / Blacklisted
- **Specialty / Role** (single-select): RN, LPN, CNA, Physician–Specialty, NP, PA, MA, Radiology Tech, Respiratory Tech, PT, OT, etc.
- **Sub-Specialty** (multi-checkbox): ICU, ER, OR, L&D, Peds, Cardiac, etc.
- **License Type** (dropdown matching Specialty)
- **License Number** (single-line text) — sensitive; restrict view permissions
- **License State** (multi-checkbox — many nurses hold compact licenses)
- **License Expiration Date** (date) — workflow to alert 60 days out
- **NPI Number** (for physicians/NPs/PAs)
- **Years of Experience** (number)
- **Current Employer** (single-line text)
- **Current Salary** (number) — sensitive
- **Desired Salary Min** (number)
- **Desired Salary Max** (number)
- **Shift Preference** (multi-checkbox): Day / Night / Mixed / Per Diem / Weekend
- **Employment Preference** (multi-checkbox): Permanent / Travel / Contract / Per Diem
- **Willing to Relocate** (boolean)
- **Relocation Radius (miles)** (number)
- **Eligible Geographies** (multi-checkbox of states)
- **Resume on File** (boolean) — track separately because HubSpot's file attachments are not searchable on Professional
- **Background Check Status** (dropdown): Not Started / In Progress / Cleared / Flagged / Expired
- **References Verified** (boolean)
- **Source** (dropdown): Website / Job Fair / Referral / LinkedIn / Indeed / Cold Outreach / Rehire / Partner Import / Other — captured at creation via channel-specific form variants or as a required parameter on API/manual creation. See ADR-0002.
- **Source Detail** (single-line text) — free-text specifics, e.g., "Boston Nursing Career Fair 2026-04" or "Referred by Maria Chen (Contact ID 12345)"
- **Source (Locked)** (dropdown — same options as `Source`) — populated by workflow at the moment of creation; used by all reporting and dashboards. Do not edit directly.
- **Source Detail (Locked)** (single-line text) — populated by workflow at creation; used by all reporting. Do not edit directly.
- **Original Source** (HubSpot standard, automatic) — kept alongside the above. Tracks web-traffic channel (Organic / Paid / Direct / Social / Referrals / Offline / Other) for contacts who arrived via the website. NOT a substitute for the recruiting `Source` field above — the two answer different questions.
- **Recruiter Owner** (HubSpot user, separate from Contact Owner to allow ops separation)

### Critical: Marketing Exclusions

Create a static "Candidates — Marketing Suppression" list and add every contact where `Contact Type = Candidate` unless they've explicitly opted in. Apply suppression to every marketing email send. Treat the candidate population as transactional-only by default.

---

## 4. Services Object — Job Requisitions

Each open role at a client is one Service record. This is HubSpot's newer object — well-suited here because each req has a lifecycle and is "delivered" upon fill.

### Properties

- **Service Name** (auto-format): `[Client Short Name] — [Role] — [Location]`, e.g., "Mercy — RN Night Shift — Boston"
- **Job Title** (single-line text)
- **Specialty** (matches candidate Specialty options — enables matching)
- **Sub-Specialty** (multi-checkbox)
- **Shift** (dropdown): Day / Night / Rotating / Weekend / Per Diem
- **Employment Type** (dropdown): Permanent / Contract / Travel / Per Diem
- **Salary Band Min** (number)
- **Salary Band Max** (number)
- **Expected Annual Salary** (number — basis for fee calc)
- **Location** (city, state)
- **License Requirements** (multi-checkbox)
- **Years Experience Required** (number)
- **Headcount** (number — most reqs are 1, but some are bulk)
- **Req Status** (dropdown — separate from a sales pipeline since Services don't have one):
  - Intake → Active → On Hold → Filled → Cancelled
- **Date Opened** (date)
- **Target Fill Date** (date)
- **Date Filled** (date)
- **Days to Fill** (calculated)
- **Hiring Manager** (associated Contact)
- **Recruiter Assigned** (HubSpot user)

### Why Services and not Deals or a Custom Object

You're on Professional so Custom Objects aren't available. Treating reqs as Deals (option we discussed) would conflate the supply-side state machine (req lifecycle) with the sales-side state machine (negotiation, won/lost). Services keeps them separate while still being a first-class linkable object.

---

## 5. Deals — Sales Pipeline

One Deal per Service. Deal represents the commercial outcome: did this requisition produce revenue?

### Deal pipeline stages

1. **Req Received** — client signaled intent / signed engagement letter for this role
2. **Sourcing** — actively recruiting candidates
3. **Submitted** — at least one candidate presented to client
4. **Interviewing** — client interviewing one or more candidates
5. **Offer Out** — client has extended an offer
6. **Placed (Won)** — candidate accepted, start date set
7. **Guarantee Period** — placed but inside guarantee window (new stage, see §6)
8. **Closed Won** — guarantee period elapsed, fee fully earned
9. **Lost — No Fill** (client cancelled or went unfilled)
10. **Lost — Replaced** (we placed but guarantee triggered without success)

> **Probability defaults:** Sourcing 20%, Submitted 40%, Interviewing 60%, Offer Out 80%, Placed 95%, Guarantee 99%, Closed Won 100%.

### Deal properties

- **Service (Requisition)** (associated Service — should auto-link)
- **Expected Salary** (mirror from Service)
- **Fee %** (mirror from Company; overrideable)
- **Expected Fee** (calculated: Expected Salary × Fee %)
- **Placed Candidate** (associated Contact)
- **Actual Placed Salary** (number)
- **Actual Fee** (number — invoice basis)
- **Start Date** (date — the candidate's first day)
- **Guarantee Period Days** (number — mirror from Company)
- **Guarantee End Date** (calculated: Start Date + Guarantee Days)
- **Guarantee Status** (dropdown): Active / Cleared / Triggered / Refunded / Replaced
- **Invoice Sent Date** (date)
- **Invoice Paid Date** (date)
- **Commission Recruiter** (user) and **Commission %** (number) — for internal comp tracking

---

## 6. Tickets — Two Pipelines

### Pipeline A: Candidate Applications

One Ticket = one application = one candidate's progress against one job. This is your ATS.

**Stages:**
1. New Application
2. Screening (recruiter review)
3. Phone Screen Scheduled
4. Phone Screen Complete
5. Submitted to Client
6. Client Interview Scheduled
7. Client Interview Complete
8. Reference Check
9. Background Check
10. Offer Extended
11. Offer Accepted → triggers Deal stage update to **Placed**
12. Hired (closed)
13. Rejected — Client Pass
14. Rejected — Candidate Withdrew
15. Rejected — Failed Screen / Background

**Ticket properties:**
- **Candidate** (associated Contact)
- **Job Requisition** (associated Service)
- **Client** (associated Company — auto-roll from Service)
- **Deal** (associated Deal — auto-roll from Service)
- **Submitted Date**
- **Interview Dates** (array via repeated activity logs)
- **Rejection Reason** (dropdown)
- **Candidate Rating** (1–5)
- **Submission Notes** (rich text)

### Pipeline B: Post-Placement Client Support

Stages: New → Investigating → Action Required → Resolved → Closed.

**Ticket properties:**
- **Issue Type** (dropdown): Performance Concern / No-Show / Guarantee Claim / Invoice Dispute / Other
- **Related Deal** (associated)
- **Related Placed Candidate** (associated Contact)
- **Resolution** (dropdown): Replaced / Refunded / Credited / Coached / No Action / Lost Client

When `Issue Type = Guarantee Claim` AND `Resolution = Replaced`, workflow flips the related Deal's Guarantee Status to "Replaced" and may spawn a new Service + Deal.

---

## 7. Lifecycle Stages (Standard HubSpot)

HubSpot's built-in Lifecycle Stage applies primarily to client-side Contacts and Companies. **Set this on Hiring Manager contacts only** — do NOT use it for Candidates (candidates have their own `Candidate Status`).

Map:
- Subscriber → Lead → MQL → SQL → Opportunity → Customer → Evangelist

Use Lifecycle for hiring managers / companies. Use Candidate Status for candidates.

---

## 8. Workflows (Day-1 Must-Haves)

1. **Candidate Source Stamp** — when a Contact is created with Contact Type = Candidate, lock Source and Source Detail to the value at creation (prevents data drift).
2. **License Expiration Alert** — 60 and 30 days before License Expiration Date, notify Recruiter Owner.
3. **Application → Deal Stage Sync** — when an Application Ticket moves to "Offer Accepted," advance the linked Deal to Placed.
4. **Placement → Guarantee Clock** — when Deal hits Placed and Start Date is set, calculate Guarantee End Date and create a reminder task 7 days before expiry.
5. **Guarantee Cleared → Invoice** — when current date > Guarantee End Date AND Guarantee Status is still "Active," flip to "Cleared," advance Deal to Closed Won, notify Finance.
6. **Stale Application Alert** — Application Ticket sitting in any stage > 14 days notifies recruiter.
7. **Marketing Suppression Auto-Add** — when Contact Type = Candidate, auto-add to "Candidates — Marketing Suppression" list.
8. **Hiring Manager Re-Engagement** — when a Company has no Active Service for 90 days and no Open Deal, notify owner.
9. **Req Stale Alert** — Service Req Status = Active > 45 days with no Application activity → notify recruiter and account owner.
10. **Compliance Hold** — Candidate Status set to "Do-Not-Contact" or "Blacklisted" → auto-remove from all active sequences and suppression lists, set Marketing Opt-Out, log audit note.
11. **Source Lock — Initial Copy** — on Contact creation with `Contact Type = Candidate`, copy `Source` → `Source (Locked)` and `Source Detail` → `Source Detail (Locked)`. Fires once on creation only. See ADR-0002.
12. **Source Drift Watchdog** — when `Source` or `Source Detail` changes on a Candidate Contact older than 24 hours, notify the Recruiting Ops admin with the old (read from the Locked copy) and new values; create a follow-up task on the contact. Does not auto-revert — leaves room for genuine corrections while preserving an audit trail.

---

## 9. Marketing & Consent Discipline

This is the riskiest area of the design and easy to under-plan.

- **Default candidate consent state: transactional only.** Job-related communication (application status, interview scheduling) is transactional. Newsletters, "we have new openings," and any commercial content require explicit opt-in.
- **Track consent per legal basis.** Add Contact properties: `Marketing Consent — Candidate` (boolean, with date) and `Marketing Consent — Hiring Manager` (separate). Even if not subject to GDPR, US state laws (CA, CO, VA, CT, TX) are converging on consent disclosure.
- **Subscription Types in HubSpot:** create separate types for "Candidate Job Alerts," "Hiring Manager Updates," "Industry Newsletter." Never send across types.
- **Healthcare candidates are sensitive.** A nurse currently employed who's quietly looking does not want her hospital to learn she's in your CRM. Do not enable LinkedIn-style social proof or referral nudges by default.

---

## 10. Reporting & Dashboards (Day-1)

**Recruiter Operations Dashboard**
- Open Reqs by Recruiter, by Specialty, by Age
- Applications in flight by Stage
- Time-to-Fill (avg & median) by Specialty and Client
- Applications-per-Placement ratio (a key efficiency metric)

**Sales & Revenue Dashboard**
- Deal pipeline value by Stage
- Expected vs Closed Won fees this month / quarter
- Win Rate by Specialty / Client / Recruiter
- Average Fee per Placement
- Guarantee period exposure (sum of fees in guarantee window — at-risk revenue)

**Account Dashboard (per client)**
- Active Reqs, fills last 12 mo, total fees billed, average days-to-fill, open support tickets, guarantee claims rate

**Candidate Supply Dashboard**
- Active candidates by Specialty, by License State
- Sources of placements (which channels actually convert)
- Candidates with expiring licenses next 90 days

---

## 11. Healthcare-Specific Considerations

- **Licensure verification** is not optional. Background Check Status + License Expiration are auditable. Most state nursing boards offer public verification — link to it in a Contact note.
- **Compact licenses (Nurse Licensure Compact)** matter for placement eligibility. Multi-checkbox State Licenses is the right shape, not a single state.
- **HIPAA does not generally apply to recruiting data** (the candidate is not a patient), but candidate health attestations sometimes appear in pre-employment forms. Do not store those in HubSpot — they belong in a HIPAA-compliant vault.
- **Specialty matching is the core efficiency lever.** Maintain a controlled vocabulary for Specialty / Sub-Specialty across Service and Contact so list-based matching works ("Find me all RN-ICU candidates with active CA license in Active status").
- **Travel vs Permanent placements have different economics.** If they do both, consider a `Placement Type` property on Deal (Travel / Permanent / Contract) and break out the dashboard.

---

## 12. Things to Plan Before Go-Live (gaps I want to flag)

These are the items that aren't in the "objects + properties" answer but will determine whether the system actually works:

1. **Web forms feeding the CRM — one form variant per source channel, not a single universal form.** Each acquisition channel should have its own form URL with a hidden `Source` field hard-coded to that channel; this is the cheapest reliable attribution mechanism. Minimum set at launch:
   - `/apply` — generic careers page application, hidden `Source = Website`, plus a visible "How did you hear about us?" dropdown for self-reported sub-channel.
   - `/event/[event-slug]` — one URL per job fair or conference, hidden `Source = Job Fair`, hidden `Source Detail` hard-coded to the event name. New URL + QR code per event; sunset after the event window.
   - `/refer` — referral form, hidden `Source = Referral`, visible field for the referring person.
   - Add `/partner/[partner-slug]` variants as partner channels are formalized.
   - Each form auto-creates the Contact + an Application Ticket (when a specific role is referenced) and stamps Source / Source Detail via hidden fields. See ADR-0002.
2. **Resume parsing.** HubSpot Professional won't OCR / parse resumes into structured fields. Either parse manually at intake (slow) or integrate a parser (e.g., Sovren, Affinda). Decide now.
3. **Recruiter ownership / round-robin.** Who owns a new candidate? A new req? Workflow rules need a documented routing logic — by Specialty, by Region, or by load balance.
4. **Email integration.** Two-way Gmail/Outlook sync, candidate-facing templates, sequences for screening. Plan templates per stage of Application Pipeline A.
5. **Document storage.** Resumes, offer letters, signed engagement letters. HubSpot's file storage works for small volumes; if recruiters are uploading 200+ resumes a week, consider Google Drive / Dropbox sync.
6. **Phone / calling.** HubSpot Calling on Professional is fine for low volume; if recruiters are dialing 50+/day, integrate Aircall or Dialpad.
7. **Job board / careers page.** Where do open Services get published? Indeed feed, ZipRecruiter, the recruiter's own site? Define the publish pipeline.
8. **Reporting on commission.** If recruiters earn a % of each placement, you need recruiter-attribution and commission rules locked before the first close.
9. **Migration / backfill.** If they have existing candidates or clients in spreadsheets / another system, plan the import in a single coordinated pass.
10. **Permissions.** License Number, Salary, and Source Detail (e.g., poached from competitor) are sensitive. Decide who sees what before importing real data.
11. **Compliance review.** A 30-minute call with employment / privacy counsel before go-live is cheap insurance — especially around candidate consent and license-number storage.
12. **Upgrade trigger.** Track the pain points that would justify moving to Enterprise + Custom Objects: are recruiters complaining about Contacts list bleed-through? Are reports awkward because Service + Deal duplication? Set a 6-month review point.

---

## 13. Open Questions I'd Still Like Answered

These didn't block the blueprint but will sharpen implementation:

- **Volume estimates.** Placements per month? Active reqs at any time? Number of recruiters? Drives whether you need Sales Hub Pro seat counts vs. additional add-ons.
- **Travel nursing vs permanent vs both?** Travel placements have weekly billing and different fee mechanics — needs a different Deal flavor.
- **Geographic scope.** US-only? Multi-state? Multi-country? Affects compliance, currency, and licensing complexity.
- **Existing tooling being replaced.** If migrating from a real ATS (Bullhorn, JobAdder), there's a feature gap to plan around — HubSpot Professional won't match an ATS on every dimension (e.g., bulk resume search, candidate hotlists, advanced Boolean).
- **Does the engagement letter give them exclusivity?** Affects whether you should flag duplicate Service records for the same role at the same client.
- **Commission structure.** Single recruiter per Deal? Split between sourcer + closer? Tiered by fee size? Determines how to model Commission % on Deal.
