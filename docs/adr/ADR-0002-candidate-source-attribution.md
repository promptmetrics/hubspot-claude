# ADR-0002: Capture Candidate Source at Creation via Channel-Specific Form Variants, Required API Parameters, and a Locked Reporting Copy

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-14 |
| **Deciders** | Izzy |
| **Related** | ADR-0001 (subscription types); `healthcare-recruiter-hubspot-setup.md` §3, §8, §12 |
| **Context tags** | HubSpot, CRM, Attribution, Reporting, Healthcare Recruiting, Professional Tier |

---

## 1. Context

Channel-level attribution is the single most important data point for evaluating marketing and sourcing ROI in a recruiting firm. The recruiter spends money and time on job fairs, online job boards, referral programs, paid advertising, and direct outreach; without per-candidate source attribution, all of those channels become indistinguishable in retrospect and budget allocation becomes guesswork.

The initial design instinct was to **infer Source from the contact's creation mechanism** — contacts created through the website form would be tagged `Website`, and contacts created via API or manual entry would be tagged `Job Fair`. This works in a world with exactly two acquisition channels. The world the recruiter actually operates in includes at minimum: website form submissions, job fair imports, employee referrals, candidate-to-candidate referrals, LinkedIn sourcing, Indeed Resume imports, cold-outreach replies, partner agency imports, walk-ins, phone inquiries, and rehires of past placements. Most of these enter the CRM via API or manual creation, and a single "non-form = job fair" rule collapses all of them into one bucket, producing a dataset that is **confidently wrong rather than usefully accurate** — every report continues to render, but its conclusions are off by a factor of however many real channels were collapsed into "Job Fair."

A second, subtler problem: HubSpot's built-in `Original Source` property is a **web traffic** attribution (Organic / Paid / Direct / Social / Referrals / Offline / Other), not a **recruiting channel** attribution. The two answer different questions and must coexist as separate properties. Conflating them produces reporting that looks reasonable but reads incorrectly — for example, a candidate who first heard about the firm at a job fair, returned home, and Googled the firm later will show `Original Source = Organic Search`, hiding the job fair's actual marketing value entirely.

A third problem is **drift over time**. Even if Source is captured correctly at creation, well-meaning recruiters editing contact records months later will silently rewrite source values during routine data cleanup. Without a locked copy that reporting reads from, historical attribution degrades gradually and invisibly.

The control we need must (a) capture Source deterministically at the moment of creation, regardless of mechanism, (b) distinguish recruiting source from web-traffic source rather than conflate them, and (c) preserve a frozen copy that reporting reads from, so post-hoc edits don't corrupt historical attribution.

---

## 2. Decision

Source attribution will be captured deliberately at the moment of Contact creation, by mechanism appropriate to each acquisition channel, and immediately locked into a separate property that reporting reads from.

1. **Channel-specific form variants on the website.** Rather than one generic application form, the careers site exposes multiple form URLs, each with a hidden `Source` field hard-coded to that channel:
   - `/apply` — generic careers page, hidden `Source = Website`, plus a visible "How did you hear about us?" field for self-reported sub-channel.
   - `/event/[event-slug]` — one URL per job fair or conference, hidden `Source = Job Fair`, hidden `Source Detail = [event name]`. New URL and QR code per event.
   - `/refer` — referral form, hidden `Source = Referral`, visible field for the referring person.
   - Additional variants (e.g., `/partner/[partner-slug]`) as new channels are formalized.

2. **Source as a required parameter on API and manual creation paths.** The hubspot-agent's Contacts specialist refuses to create a Candidate Contact without an explicit `Source` value. Manual creation in the HubSpot UI uses a required-field rule. No inference, no defaults.

3. **A locked reporting copy.** Two properties exist:
   - `Source` and `Source Detail` — the working values, populated at creation, editable for genuine corrections.
   - `Source (Locked)` and `Source Detail (Locked)` — populated by workflow at the moment of creation, treated as immutable, and used by all reporting and dashboards.

4. **HubSpot `Original Source` kept as a complementary property.** For web-acquired contacts, HubSpot's automatic Original Source (and its drill-down properties) continues to capture which web channel referred the visit. It is reported alongside the recruiting `Source`, never substituted for it.

5. **A drift watchdog workflow.** Any change to `Source` or `Source Detail` on a Candidate Contact older than 24 hours notifies the Recruiting Ops admin and creates a follow-up task on the contact. The watchdog does not auto-revert; it creates an audit record and leaves humans in the loop for the rare legitimate correction.

---

## 3. Rationale

### Why creation mechanism is the wrong proxy

The premise "non-form = job fair" requires the assumption that no other creation path will ever exist, which is false at the design stage and certain to break in the first quarter of operation. Once it breaks, the contamination is invisible to the user and undetectable in reports. A correct-looking but wrong dataset is more dangerous than no dataset, because it produces budget decisions that look evidence-based when they are actually guesses.

### Why we want one form per channel rather than one form with a "How did you hear about us?" dropdown

A self-reported dropdown is a useful supplement but a poor primary attribution mechanism. Candidates routinely skip optional questions, pick the first option in the list, choose "Other" with unstructured text, or simply guess. By contrast, a hidden field on a channel-specific form URL captures attribution deterministically based on which link the candidate clicked — the candidate cannot get it wrong because they are not asked. The operational cost is real but small: building a new form variant takes ~15 minutes.

### Why a locked copy and not just discipline

HubSpot Professional does not offer property-level edit permissions for ordinary Contact properties (that capability sits in higher tiers). Without a locked copy, the only enforcement available is procedural — training people not to edit Source after creation — and procedural enforcement degrades. The locked copy is two extra properties and one creation-time workflow, which is a cheap insurance policy against silent historical drift.

### Why we don't auto-revert source edits

A revert workflow would protect the locked copy at the cost of preventing legitimate corrections, including the inevitable data-entry mistake caught a day later. The chosen design favors auditability over enforcement: the watchdog notifies on change, leaving a human in the loop for the rare legitimate edit while still creating a paper trail for any drift.

### Why HubSpot Original Source stays in the picture

Original Source is automatic, free, and captures web-traffic channel with reasonable accuracy. It is the right attribution for understanding the website-to-contact funnel. The recruiting `Source` field, by contrast, captures the broader acquisition strategy (much of which happens off-web). Both are needed; neither substitutes for the other. Reporting must read both separately, never mixed.

---

## 4. Alternatives Considered

### Alternative A — Single universal form with "How did you hear about us?" as the sole capture mechanism

One form for all candidate intake; ask the candidate to self-report.

**Rejected** because self-report attribution is unreliable in practice (skipped questions, default-first-option bias, unstructured "Other" answers). Acceptable as a supplemental sub-channel detail field, not as the primary attribution.

### Alternative B — Infer Source from creation mechanism (the original proposal)

Stamp `Website` for form-created contacts and `Job Fair` for everything else.

**Rejected** because it presumes a two-channel world that does not exist beyond the first quarter of operation. Every non-website, non-job-fair channel becomes invisible. Discussed in §1 and §3.

### Alternative C — Rely solely on HubSpot Original Source

Use the built-in property and skip the custom recruiting Source.

**Rejected** because Original Source answers a different question (web channel) and is not set for non-web acquisitions. It cannot distinguish a job fair from a referral from a cold outreach.

### Alternative D — Use a third-party attribution tool (Segment, dedicated recruitment marketing attribution)

Send acquisition data to an external attribution service and join back to HubSpot via integrations.

**Rejected for now** as overkill at current scale. Volume does not justify the cost or integration complexity, and HubSpot's native form mechanisms plus a disciplined two-property pattern give 90% of the value at near-zero incremental cost. Reconsider at the same 6-month review point flagged in the broader blueprint.

### Alternative E — Make `Source` non-editable via HubSpot field-level edit permissions

Hide the edit affordance entirely after creation.

**Rejected** because reliable property-level edit restrictions are not available on Sales/Service Hub Professional. The two-property + watchdog pattern is the working-tier equivalent.

---

## 5. Consequences

### Positive

- Deterministic attribution at the moment of creation, not after-the-fact reconstruction.
- Channel-specific form URLs double as marketing assets — each is independently trackable, supports its own QR code, and surfaces its own form analytics.
- Reporting reads from the locked copy, so historical attribution stays stable even as recruiters edit working records during routine data cleanup.
- Watchdog workflow creates an audit trail for any post-creation source changes.
- Compatible with HubSpot Professional — no tier upgrade required.

### Negative

- Operational overhead per new channel: building a new form variant takes 10–15 minutes. Acceptable but not zero.
- API and manual creation paths must include Source explicitly. Code paths that omit it will fail loudly (intentional) but every integration point has to honor the rule.
- Two source properties plus Original Source means three attribution fields visible on each contact record. Train new admins on which to read for which purpose.
- The hidden-field approach means a candidate who clicks the wrong URL gets the wrong attribution. Marketing-link discipline matters — job-fair URLs are not to be posted publicly; referral URLs are distributed only through internal channels.

---

## 6. Implementation Steps

### A. Create the source-related Contact properties

1. Navigate to **Settings → Properties → Contact properties**.
2. Create or confirm `Source`:
   - Field type: Dropdown select
   - Options: `Website`, `Job Fair`, `Referral`, `LinkedIn`, `Indeed`, `Cold Outreach`, `Rehire`, `Partner Import`, `Other`
   - Mark as required on Candidate creation forms.
3. Create `Source Detail`:
   - Field type: Single-line text.
4. Create `Source (Locked)`:
   - Field type: Dropdown select, same options as `Source`.
   - Description: *"Populated by workflow at creation. Do not edit. All reporting reads from this property."*
5. Create `Source Detail (Locked)`:
   - Field type: Single-line text.
   - Same description note as step 4.

### B. Build channel-specific HubSpot forms

6. Navigate to **Marketing → Forms → Create form**.
7. Create the **generic application form** (will live at `/apply`):
   - Standard application fields (name, email, phone, specialty, license info, resume upload).
   - Hidden field: `Source` with default value `Website`.
   - Visible field: "How did you hear about us?" — dropdown with options matching the Source list (excluding `Website`), plus "Other."
   - Map the self-reported value into `Source Detail`.
8. For **each upcoming job fair**, create a dedicated form (will live at `/event/[slug]`):
   - Same application fields.
   - Hidden field: `Source = Job Fair`.
   - Hidden field: `Source Detail = [event name + date]`, e.g., "Boston Nursing Career Fair 2026-04".
   - Generate a QR code pointing to this form URL; print on booth materials.
   - Retire the form 90 days after the event (page no-indexed or redirected).
9. Create the **referral form** (`/refer`):
   - Hidden field: `Source = Referral`.
   - Visible field: "Referred by (name + email)" → mapped into `Source Detail`.
10. For each formalized **partner agency relationship**, create a partner-specific variant (`/partner/[slug]`) with hidden `Source = Partner Import` and partner-specific `Source Detail`.

### C. Build the workflows

11. **Source Lock — Initial Copy.** **Automation → Workflows → Create workflow → Contact-based**.
    - Trigger: Contact is created AND `Contact Type = Candidate`.
    - Action: Copy property — `Source` → `Source (Locked)`.
    - Action: Copy property — `Source Detail` → `Source Detail (Locked)`.
    - Re-enrollment: No (this is creation-only).
12. **Source Drift Watchdog.** Workflows → Create workflow → Contact-based.
    - Trigger: `Source` OR `Source Detail` changes AND `Contact Type = Candidate` AND `Create Date` is more than 24 hours ago.
    - Action: Send internal email to Recruiting Ops admin with the contact name, the old value (read from the Locked copy), and the new value.
    - Action: Create a task on the contact: "Source attribution changed after lock window — review and confirm or roll back."

### D. Wire the hubspot-agent API path

13. In the Contacts specialist (or whichever specialist creates Candidate contacts), make `source` a **required parameter** on creation. Refuse the call with a clear error if it's omitted. Do not default.
14. Validate the supplied `source` against the dropdown option list before submitting to HubSpot. Fail closed on unknown sources rather than letting "Other" become a dumping ground.
15. The agent should also populate `Source Detail` when it can (e.g., "Imported from spreadsheet `2026-04-boston-fair-leads.csv`" for a bulk job-fair import).

### E. Marketing link discipline

16. Document internally that job-fair URLs are scanned from QR codes at the booth and not posted on public marketing channels; referral URLs are distributed only through internal channels. The hidden-field model only works if the channel-to-URL mapping holds.
17. Build a saved view: **Contacts with `Source = Other`**. Should remain near-empty. Anything appearing here indicates either a missing form variant or someone forcing a value because no existing option fit — both are signals to add a new form variant.

### F. Reporting convention

18. All dashboards, custom reports, and active lists that reference candidate source MUST read from `Source (Locked)` and `Source Detail (Locked)`, not from `Source` and `Source Detail`. Treat this as a code-review item for any new report. Add a note on each dashboard.
19. Use HubSpot's `Original Source` (and its drill-down properties) as a separate dimension when analyzing the website-to-contact funnel. Do not aggregate it with the recruiting `Source`.

### G. Verification

20. Create a test contact via each path:
    - Submit the `/apply` form with a unique test email.
    - Submit a test `/event/...` form.
    - Have the hubspot-agent create a contact with `source = LinkedIn`.
21. For each, confirm that `Source (Locked)` is populated within 60 seconds and matches the value set at creation.
22. Edit `Source` on one of the test contacts 25 hours after creation; verify the Drift Watchdog fires (notification email arrives, task is created).

---

## 7. Open Items

- **`/apply` self-report dropdown options.** The "How did you hear about us?" visible field needs a curated option list. Recommend starting with the Source options minus `Website` (they're on the website by definition), plus a free-text "Other (please specify)" → captured into a separate `Source Self-Reported Detail` property if granular tracking matters.
- **Event-form sunset policy.** Each job-fair form variant should be retired 90 days after the event closes; leaving them live indefinitely creates a long-tail risk of stale URLs producing wrong attribution.
- **Partner channel formalization.** If partner agency channels become a significant source, consider promoting them to a first-class entity (a Partner Company record) and tracking attribution at the Partner level rather than via Source Detail strings.
- **Six-month review trigger.** Re-evaluate the form-variant approach versus a dedicated marketing attribution tool (Segment, recruitment-specific attribution) once monthly candidate intake exceeds ~500, or once the count of distinct form variants exceeds ~15.

---

## 8. References

- [HubSpot: Use hidden fields in forms](https://knowledge.hubspot.com/forms/use-hidden-fields-in-forms)
- [HubSpot: About Original Source and other default analytics properties](https://knowledge.hubspot.com/contacts/hubspot-crm-default-properties)
- [HubSpot Forms API](https://developers.hubspot.com/docs/api/marketing/forms)
- [HubSpot: Workflow copy property action](https://knowledge.hubspot.com/workflows/copy-a-property-value-in-workflows)
- Related project documents:
  - `/Users/izzy/Documents/hubspot/healthcare-recruiter-hubspot-setup.md` (Sections 3, 8, 12 — amended by this ADR)
  - `/Users/izzy/Documents/hubspot/docs/adr/ADR-0001-hubspot-email-subscription-types.md` (sibling decision on cross-audience send protection)
