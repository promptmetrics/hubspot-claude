# ADR-0001: Use Two HubSpot Email Subscription Types to Prevent Cross-Audience Marketing Sends

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-14 |
| **Deciders** | Izzy |
| **Related** | `healthcare-recruiter-hubspot-setup.md` (Section 11 — Marketing & Consent Discipline) |
| **Context tags** | HubSpot, CRM, Email Compliance, Healthcare Recruiting, Professional Tier |

---

## 1. Context

The healthcare recruiting business operates on **HubSpot Sales/Service Hub Professional**, which does not include Custom Objects. As a result, the Contacts object must hold two operationally distinct populations:

- **Hiring managers and HR contacts** at client healthcare facilities (clinics, hospitals)
- **Job candidates** sourced from the careers page, job fairs, referrals, and outreach

These two populations are segmented inside the Contacts object via a required `Contact Type` property. While this works for record-keeping, it creates a real and asymmetric risk on the marketing side:

> A commercial marketing email intended for hiring managers ("New candidates available in your specialty," "Q3 healthcare staffing trends") that accidentally reaches even a small number of job candidates is a **serious reputational injury**. Many candidates are passively job-seeking from within their current employer; some have profiles publicly identifying their current employer; an email from a recruiter to a candidate's work address can expose their job search to their current employer. The damage is hard to walk back, harder to detect, and the population is large and continually growing.

The failure mode we want to design out is not the deliberate mis-send — it is the **incidental mis-send**: a marketer building a list with one filter wrong, a workflow enrollment criterion that drifts, a copy-and-pasted list that includes the wrong contacts. List-membership filtering is too easy to misconfigure, and the consequences land on third parties (the candidates) rather than on the misconfigurer.

We need a control that:

1. Operates at a lower layer than list membership
2. Cannot be bypassed by ordinary user error in HubSpot
3. Defaults to safe (i.e., a brand-new candidate Contact is protected without any human action)
4. Does not interfere with operational/transactional candidate communication (interview scheduling, application status, offer letters)

---

## 2. Decision

We will use **HubSpot Email Subscription Types** as the primary enforcement layer for cross-audience send protection. Specifically:

1. **Create three subscription types in HubSpot:**
   - `Hiring Manager Updates` — commercial communication aimed at the client / buyer side
   - `Candidate Job Alerts` — commercial communication to candidates who have explicitly opted in
   - `Industry Newsletter` — generic thought-leadership content (created now to avoid retroactive retagging later)

2. **Default-unsubscribe every candidate Contact from `Hiring Manager Updates`** at the moment `Contact Type` is set to `Candidate`. This is enforced two ways for redundancy:
   - A HubSpot Workflow triggered by the property change
   - An API call from the application code that creates the Contact

3. **Mandate subscription-type tagging on every marketing send.** Operational discipline: each marketing email template is permanently tagged with the appropriate subscription type. Hiring-manager content uses `Hiring Manager Updates`; candidate marketing uses `Candidate Job Alerts`.

4. **Leave transactional candidate emails on the standard transactional channel.** Application status, interview scheduling, and offer communications bypass subscription enforcement by design — this is HubSpot's built-in behavior for transactional templates and is the correct policy.

---

## 3. Rationale

### Why subscription types and not lists

HubSpot subscription types are enforced at the **send pipeline**, not at the list level. When a contact is unsubscribed from a subscription type, HubSpot will refuse to send them any email tagged with that subscription type — regardless of how the contact was selected for the send (active list, static list, workflow enrollment, manual selection). This is the same enforcement layer that HubSpot uses for legal compliance (CAN-SPAM, GDPR, CASL).

This gives us the property we want: **the safety control is independent of the list-builder's correctness**. The marketer can configure the list wrong; the workflow can drift; an import can include the wrong contacts. None of those failure modes can override an explicit unsubscribe.

### Why default-unsubscribe rather than opt-in only

HubSpot's default behavior when a new subscription type is created is **implicit opt-in** under a legitimate-interest basis. New contacts are technically subscribed until they opt out. This means a candidate Contact created today is, by default, eligible to receive `Hiring Manager Updates` emails. We therefore actively unsubscribe candidates at the moment their `Contact Type` is set, restoring the default-safe state.

### Why both a workflow and an API call

A single enforcement point would be sufficient under normal conditions, but the cost of redundancy here is near zero and the cost of failure is high. The workflow catches contacts created through any path (forms, imports, manual entry, integrations) without depending on code being correct everywhere. The API call catches the brief window between Contact creation and workflow execution, and provides immediate observability in application logs.

### Why three subscription types and not two

Adding `Industry Newsletter` now is cheap insurance. HubSpot does not allow retroactive re-tagging of historical sends to a different subscription type. The first time someone wants to send thought-leadership content, they will either invent a new subscription type (creating compliance and reporting friction) or — more likely — send it under one of the existing types, polluting the consent semantics.

---

## 4. Alternatives Considered

### Alternative A — List-only segregation

Build "Hiring Managers" and "Candidates" active lists with `Contact Type` filters; require all marketing sends to select only from those lists.

**Rejected** because:
- Enforcement is upstream of the send layer; misconfigured lists still send
- Active list logic can drift if `Contact Type` is ever changed or null
- No defense against ad-hoc one-off sends from a Contact view

### Alternative B — Custom property exclusion filter on every send

Add a "Marketing Eligible" property; require every marketing email to filter on `Marketing Eligible = true`.

**Rejected** because:
- Requires perfect human discipline on every single send
- Easy to forget when sending one-off emails from a contact record
- HubSpot has no enforcement mechanism for "must include this filter"

### Alternative C — Upgrade to Sales/Service Hub Enterprise + Custom Objects

Move candidates into a `Candidate` Custom Object, separating them from Contacts entirely. Subscription concerns largely vanish because Custom Objects do not receive marketing email.

**Rejected at this stage** because:
- Enterprise tier is a substantial cost increase and the business does not yet have the volume to justify it
- Migration effort is non-trivial
- The subscription-type approach gives us most of the safety benefit at the cost of operational discipline rather than dollars
- We have explicitly noted a 6-month review point in the broader setup blueprint to reconsider this

### Alternative D — Separate HubSpot portals (one for the sell side, one for the supply side)

Run two completely independent HubSpot accounts.

**Rejected** because:
- Doubles license cost
- Breaks the unified pipeline (Service ↔ Deal ↔ Application Ticket) that makes recruiting operations observable
- The whole point of using HubSpot as a single system was to avoid the seam between client-side and candidate-side workflows

---

## 5. Consequences

### Positive

- **Hard send-time enforcement.** A candidate cannot receive a `Hiring Manager Updates` email, period, regardless of how badly a list or workflow is configured.
- **Default-safe state.** New candidates are protected without any human action.
- **No tier upgrade required.** The control works on Professional.
- **Compliance posture.** Subscription type enforcement is the same mechanism HubSpot uses for CAN-SPAM / GDPR / CASL, so this is also the foundation for any consent obligations that may apply.

### Negative

- **Subscription types are UI-only to create.** HubSpot does not expose a Create endpoint for subscription types, so the initial setup is manual and depends on someone with HubSpot admin access.
- **Send-side tagging discipline required.** Each marketing email template must be tagged with a subscription type at creation time. A template sent untagged (HubSpot calls this "no subscription type") bypasses our protection. We must enforce template tagging in process.
- **Implicit opt-in default requires explicit override.** We rely on the workflow + API combination to maintain the default-safe state. If either fails silently, new candidates are unprotected during the gap.
- **Visibility burden.** The subscription state of any given contact is not obvious on the contact record; admins need to know where to look (Marketing email tab → subscription preferences).

---

## 6. Implementation Steps

### A. HubSpot UI Setup — Create Subscription Types

These steps must be performed by a user with **Super Admin** or **Marketing → Edit Subscription Types** permissions. Do this once; it is not repeatable on a schedule.

1. Log in to HubSpot.
2. In the top-right, click the **Settings** (gear) icon.
3. In the left sidebar, navigate to **Marketing → Email**.
4. Click the **Subscription Types** tab.
5. Click **Create subscription type** in the upper-right.
6. Create the first type:
   - **Internal name:** `Hiring Manager Updates`
   - **Description (shown to contacts on the preferences page):** *"Updates on staffing trends, candidate availability, and our services for healthcare hiring organizations."*
   - **Subscription source:** Marketing
   - **Lawful basis (if prompted):** Legitimate interest — Other (or your organization's standard basis)
   - Save.
7. Click **Create subscription type** again. Create:
   - **Internal name:** `Candidate Job Alerts`
   - **Description:** *"New healthcare job openings matched to your specialty, location, and preferences."*
   - **Subscription source:** Marketing
   - Save.
8. Click **Create subscription type** again. Create:
   - **Internal name:** `Industry Newsletter`
   - **Description:** *"Periodic newsletter on healthcare staffing, industry trends, and labor market insights."*
   - **Subscription source:** Marketing
   - Save.
9. **Record the subscription type IDs.** After creation, each type has a numeric ID visible in the URL when you view it. Capture all three IDs into the project's configuration store (or `.hubspot-portal.config.json` if using the hubspot-agent project) — the API needs these IDs, not the names.

### B. HubSpot UI Setup — Create the Default-Unsubscribe Workflow

10. Navigate to **Automation → Workflows**.
11. Click **Create workflow → From scratch → Contact-based**.
12. Name: `Candidate — Auto-unsubscribe from Hiring Manager Updates`.
13. **Trigger:** Contact enrollment trigger → "When filter criteria are met" → Filter: `Contact Type` is equal to `Candidate`.
14. Set re-enrollment: **Yes**, re-enroll if `Contact Type` changes to `Candidate`.
15. Add action: **Set marketing subscription status**.
    - Subscription type: `Hiring Manager Updates`
    - Status: `Unsubscribed`
16. (Recommended) Add a second action: **Set marketing subscription status**.
    - Subscription type: `Industry Newsletter`
    - Status: `Unsubscribed`
17. Review and turn the workflow **On**.

### C. Add the Contact Type Property (if not already present)

18. Navigate to **Settings → Properties → Contact properties**.
19. Confirm a property named `Contact Type` exists. If not, create it:
    - **Field type:** Dropdown select
    - **Options:** `Hiring Manager`, `Candidate`, `Both`, `Other`
    - **Required:** Yes (set as required on Contact creation forms)
20. Pin the property to the top of the Contact record sidebar so it's always visible.

### D. API Wiring (in the HubSpot agent code)

21. Add OAuth scopes to the application:
    - `subscriptions-definition-read`
    - `subscriptions-status-read`
    - `subscriptions-status-write`
22. On startup (or first use of the subscription specialist), fetch the subscription type definitions:
    - `GET /communication-preferences/2026-03/definitions`
    - Cache the IDs by internal name. The agent should never hard-code IDs across portals.
23. Wire the Contacts specialist (or whichever module handles Contact creation) to, immediately after creating a Contact where `Contact Type = Candidate`:
    - `POST /communication-preferences/2026-03/unsubscribe` with the contact email and the `Hiring Manager Updates` subscription ID
24. This API call is intentionally **redundant** with the workflow in Step 11–17. Both must be wired. The workflow catches contacts created outside the agent (forms, imports, manual entry); the API call closes the window between Contact create and workflow execution.

### E. Send-Side Discipline (Marketing Process)

25. In **Marketing → Email**, audit every existing marketing template and assign a subscription type to it.
26. Make it a documented internal rule: **no marketing email may be sent without a subscription type assigned**. HubSpot allows sending without one in some flows; treat that as out-of-bounds.
27. Hiring-manager-facing emails → tag `Hiring Manager Updates`. Candidate-facing marketing → tag `Candidate Job Alerts`. Newsletter content → tag `Industry Newsletter`.
28. Transactional candidate communication (interview confirmations, application status, offer letters) uses **transactional email templates**, not marketing. These bypass subscription enforcement and that is the correct behavior.

### F. Verification (Do This Before Going Live)

29. Create a test contact with a unique email address (e.g., `qa-candidate-2026@yourdomain.com`).
30. Set `Contact Type = Candidate`.
31. Wait 30–60 seconds for workflow execution. Open the contact record → **Communication subscriptions** tab.
32. **Verify:** The contact is shown as `Unsubscribed` from `Hiring Manager Updates`.
33. Build a test active list with filter `Contact Type = Hiring Manager OR email = qa-candidate-2026@yourdomain.com` (deliberately includes the test candidate).
34. Send a test marketing email tagged with `Hiring Manager Updates` to that list.
35. **Verify:** The send report shows the candidate **excluded for "Unsubscribed from this subscription type."** This confirms enforcement.
36. Repeat the verification from the API path: have the agent create a test candidate contact via code, and confirm the same exclusion outcome.

### G. Operational Monitoring

37. Build a HubSpot saved view: **Contacts where `Contact Type = Candidate` AND subscribed to `Hiring Manager Updates`.** This view should always be empty. Set a recurring weekly check (manual or via the hubspot-agent's Hygiene specialist).
38. Build a second view: **Marketing emails sent in the last 30 days with no subscription type assigned.** Should always be empty. Anything here is a process violation.

---

## 7. Open Items

- **Consent capture at the candidate intake form.** This ADR covers default-unsubscribe behavior. It does not specify what we do when a candidate explicitly opts in to `Candidate Job Alerts` via a checkbox on the careers page. That belongs in a separate decision once the careers-page form design is finalized.
- **Suppression list interaction.** A separate "Candidates — Marketing Suppression" static list is described in the setup blueprint. That list is now a belt-and-suspenders-and-belt third layer; we should decide whether to keep it or remove it as redundant. Recommendation: keep it for the first 90 days post-launch, then evaluate.
- **Six-month review trigger.** Re-evaluate upgrading to Enterprise + Custom Objects once placement volume reaches ~20/month or the candidate population exceeds ~5,000, whichever comes first.

---

## 8. References

- [HubSpot Communication Preferences API Guide (2026-03)](https://developers.hubspot.com/docs/api-reference/latest/communication-preferences/guide)
- [HubSpot: Set up email subscription types](https://knowledge.hubspot.com/marketing-email/set-up-email-subscription-types)
- [HubSpot: Manage your contacts' messaging subscriptions](https://knowledge.hubspot.com/records/manage-your-subscription-preferences-and-types)
- [HubSpot Community thread confirming UI-only creation of subscription types](https://community.hubspot.com/t5/APIs-Integrations/API-endpoint-for-creating-Email-Subscription-Type/td-p/610599)
- Related project document: `/Users/izzy/Documents/hubspot/healthcare-recruiter-hubspot-setup.md` §11
