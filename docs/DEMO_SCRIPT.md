# HubSpot Admin Agent — Live Demo Script

> A step-by-step presenter guide for demonstrating the `/hubspot` Claude Code skill to stakeholders.
> **Total estimated runtime:** 25–30 minutes
> **Audience:** Product, engineering, sales-ops, or executive stakeholders
> **Prerequisites:** A HubSpot developer test portal with sample data

---

## 1. Pre-Demo Setup

Complete these steps at least 15 minutes before the demo starts.

### Environment

1. Open a terminal in `/Users/izzy/Documents/hubspot`.
2. Ensure the virtual environment is active: `source .venv/bin/activate`.
3. Verify the skill loads without errors by running `/hubspot status` inside Claude Code.

### Portal & Auth

1. Create or identify a HubSpot developer test portal (free at developers.hubspot.com).
2. Generate a Private App token with these scopes:
   - `crm.objects.contacts.read`, `crm.objects.contacts.write`
   - `crm.objects.companies.read`, `crm.objects.companies.write`
   - `crm.objects.deals.read`, `crm.objects.deals.write`
   - `crm.schemas.contacts.write`, `crm.schemas.deals.write`
   - `automation.workflows.write`
   - `crm.lists.write`
   - `crm.pipelines.write`
   - `settings.users.write`
   - `crm.objects.engagements.write`
3. Seed the portal with sample data:
   - 3 contacts: Dana Smith, Alex Rivera, Jordan Lee
   - 2 companies: Acme Corp, Globex Industries
   - 2 deals: "Acme Renewal" ($50,000), "Globex New Deal" ($120,000)
   - 1 existing workflow named "Welcome Sequence" (inactive)
   - 1 existing list named "Newsletter Subscribers"
4. Create a `.hubspot-portal` file in the working directory containing the portal ID (e.g., `1234567`).

### Demo-Day Hygiene

- Close unrelated browser tabs and terminal panes.
- Increase terminal font size to at least 14 pt.
- Have a backup portal ID ready in case of rate-limiting.
- Keep the HubSpot UI open in a browser tab for side-by-side verification.

---

## 2. Demo Script by Scene

### Scene 1: Setup and Authentication
**Duration:** 2 minutes

**Narrator script:**
> "Before we can do anything, the agent needs to know which HubSpot portal to talk to and how to authenticate. I will show the two supported auth methods: Private App token for quick setup, and OAuth 2.0 with PKCE for production teams."

**Commands to type:**

```
/hubspot setup 1234567 token <paste-private-app-token>
```

**Expected output:**
```
Portal 1234567 configured.
Auth type: Private App Token
Scopes detected: crm.objects.contacts.read, crm.objects.contacts.write, ... (15 scopes)
Token stored securely. It will never be logged or displayed.
```

**Talking points:**
- No API keys — HubSpot deprecated them, so we only support Private App tokens and OAuth 2.0.
- Tokens are stored in Claude Code's secure credential storage, not in files.
- The `.hubspot-portal` file means the team never has to type the portal ID repeatedly.

**Optional second command (show OAuth flow):**
```
/hubspot setup 1234567 oauth
```
**Expected output:**
```
Opening browser for HubSpot OAuth 2.0 authorization...
PKCE challenge generated. Return here after approving in HubSpot.
Authorization successful. Refresh token stored.
```

---

### Scene 2: Portal Management and Status
**Duration:** 2 minutes

**Narrator script:**
> "Most admins manage more than one portal — maybe a production org and a sandbox. Let's see how the agent handles multi-portal context and gives us a health check at any time."

**Commands to type:**

```
/hubspot status
```

**Expected output:**
```
Portal: 1234567 (Developer Test)
Tier: Enterprise Trial
Active auth: Private App Token (15/15 scopes granted)
Cache: warm (last refreshed 4 min ago)
Pending approvals: 0
Rate limit: 87/100 requests remaining (resets in 6s)
```

**Second command:**
```
/hubspot portal list
```

**Expected output:**
```
Configured portals:
  1234567  Developer Test    [ACTIVE]  Private App
  7654321  Staging Sandbox            OAuth 2.0
```

**Third command:**
```
/hubspot portal switch 7654321
```

**Expected output:**
```
Switched to portal 7654321 (Staging Sandbox).
Note: pending approvals for portal 1234567 were abandoned.
```

**Switch back:**
```
/hubspot portal switch 1234567
```

**Talking points:**
- Context switches instantly without losing the Claude Code conversation history.
- Each portal has isolated token storage and cache.
- The status line is shown on every `/hubspot` response so the user never accidentally runs commands against the wrong portal.

---

### Scene 3: Read Operations
**Duration:** 2 minutes

**Narrator script:**
> "Let's start with the safest operations: reads. The ObjectsAgent handles contacts, companies, deals, and tickets. I will ask natural-language questions and the agent routes them automatically."

**Commands to type:**

```
/hubspot find contacts named Dana
```

**Expected output:**
```
ObjectsAgent dispatched.
Search results (1):
| ID     | First Name | Last Name | Email                  | Company   |
|--------|------------|-----------|------------------------|-----------|
| 101    | Dana       | Smith     | dana.smith@acme.com    | Acme Corp |
```

**Second command:**
```
/hubspot search deals over $75,000
```

**Expected output:**
```
ObjectsAgent dispatched.
Search results (1):
| Deal ID | Deal Name          | Amount   | Stage        | Close Date |
|---------|--------------------|----------|--------------|------------|
| 501     | Globex New Deal    | $120,000 | appointmentscheduled | 2026-06-15 |
```

**Third command:**
```
/hubspot list companies
```

**Expected output:**
```
ObjectsAgent dispatched.
Total companies: 2
| ID  | Name                | Domain           | Industry    | Create Date |
|-----|---------------------|------------------|-------------|-------------|
| 201 | Acme Corp           | acme.com         | Software    | 2026-01-10  |
| 202 | Globex Industries   | globex.com       | Manufacturing| 2026-02-22 |
```

**Talking points:**
- No SQL, no filters to memorize. Natural language is parsed and translated into HubSpot API calls.
- Read operations carry no approval gate — they are instant.
- The agent respects HubSpot pagination automatically (100 per page) and iterates behind the scenes.

---

### Scene 4: Create Operations with Approval
**Duration:** 3 minutes

**Narrator script:**
> "Now let's create data. Every write operation shows a preview before execution. The user approves with a single keystroke. This eliminates the 'oops, I clicked the wrong button' problem."

**Commands to type:**

```
/hubspot create contact Jordan Lee with email jordan.lee@example.com and phone +1-555-0199
```

**Expected output:**
```
ObjectsAgent dispatched — preview mode.
Risk level: MEDIUM (create operation)
Preview:
  Object type: contact
  Properties:
    firstname: Jordan
    lastname: Lee
    email: jordan.lee@example.com
    phone: +1-555-0199

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing create contact...
Contact created successfully.
| ID  | First Name | Last Name | Email                     |
|-----|------------|-----------|---------------------------|
| 103 | Jordan     | Lee       | jordan.lee@example.com    |

Undo available: delete contact 103
Action ID: act_20260511_001
```

**Second create — deal:**
```
/hubspot create deal Acme Expansion for $75,000 closing 2026-08-01 associated with Acme Corp
```

**Expected output:**
```
ObjectsAgent dispatched — preview mode.
Risk level: MEDIUM (create operation)
Preview:
  Object type: deal
  Properties:
    dealname: Acme Expansion
    amount: 75000
    closedate: 2026-08-01
  Associated company: Acme Corp (ID 201)

Approve? (y/n/details)
```

**Type:**
```
y
```

**Talking points:**
- Preview-first design means stakeholders can review exactly what will be created before it hits HubSpot.
- Undo snapshots are stored locally so updates can be rolled back.
- The action ID lets teams reference the exact operation in audit logs.

---

### Scene 5: Update Operations with Approval
**Duration:** 2 minutes

**Narrator script:**
> "Updates show a side-by-side diff. Let's change Dana Smith's phone number and job title. The agent fetches the current record, shows the diff, and waits for approval."

**Commands to type:**

```
/hubspot update contact Dana Smith set phone to +1-555-0142 and jobtitle to VP of Engineering
```

**Expected output:**
```
ObjectsAgent dispatched — preview mode.
Risk level: MEDIUM (update single record)
Target: contact ID 101 (Dana Smith)

Diff:
  phone      | +1-555-0100      -> +1-555-0142
  jobtitle   | (not set)        -> VP of Engineering

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing update contact 101...
Contact updated successfully.
Updated fields: phone, jobtitle
Undo available: restore previous values
Action ID: act_20260511_002
```

**Talking points:**
- Inline diffs make it obvious what is changing.
- Only the fields that differ are sent to the API, reducing unnecessary writes.
- Original values are snapshotted before execution so undo is one command away.

---

### Scene 6: Bulk Operations with Batch Mode
**Duration:** 3 minutes

**Narrator script:**
> "Bulk updates are where mistakes get expensive. The agent caps chunk sizes, shows estimated impact, and requires explicit confirmation for anything over ten records. Let's reassign all unassigned contacts in the Northeast region to Dana Smith."

**Commands to type:**

```
/hubspot bulk update contacts where region is Northeast set owner to Dana Smith
```

**Expected output:**
```
HygieneAgent dispatched — preview mode.
Risk level: HIGH (bulk update, 34 records)
Preview (first 10 of 34):
| ID  | Name            | Current Owner | New Owner  |
|-----|-----------------|---------------|------------|
| 104 | Sam Patel       | (unassigned)  | Dana Smith |
| 105 | Riley Nguyen    | (unassigned)  | Dana Smith |
| ... | ...             | ...           | ...        |

Estimated impact: 34 contacts will have owner updated.
Batch size: 10 per chunk (4 chunks total).

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing bulk update in 4 chunks...
Chunk 1/4: 10 updated
Chunk 2/4: 10 updated
Chunk 3/4: 10 updated
Chunk 4/4: 4 updated

Bulk update complete.
Succeeded: 34
Failed: 0
Action ID: act_20260511_003
```

**Talking points:**
- Bulk operations are auto-chunked behind the scenes to respect HubSpot rate limits.
- The preview caps at 1,000 records with a warning for larger sets.
- Partial failures are reported per-record so nothing is silently lost.

---

### Scene 7: Destructive Operations
**Duration:** 2 minutes

**Narrator script:**
> "Deletes are irreversible in HubSpot. We treat them with the highest risk level. The user must type the exact count of affected records to confirm — a simple 'yes' is not enough."

**Commands to type:**

```
/hubspot delete contacts where lifecyclestage is subscriber and last activity was before 2025-01-01
```

**Expected output:**
```
ObjectsAgent dispatched — preview mode.
Risk level: DESTRUCTIVE (delete operation, 8 records)
Preview:
| ID  | Name          | Email                 | Last Activity |
|-----|---------------|-----------------------|---------------|
| 301 | Chris Doe     | chris.d@oldmail.com   | 2024-08-12    |
| 302 | Pat Miller    | pat.m@oldmail.com     | 2024-09-03    |
| ... | ...           | ...                   | ...           |

WARNING: Deletions cannot be undone via HubSpot API.

To confirm, type the exact number of records that will be deleted: _
```

**Type:**
```
8
```

**Expected output:**
```
Destructive gate passed (8 records confirmed).
Executing deletion...
Deleted: 8 contacts
Errors: 0
Action ID: act_20260511_004
Audit log entry written.
```

**Talking points:**
- Count-based confirmation prevents accidental bulk deletion.
- No undo snapshot is taken for deletes because HubSpot does not support restore.
- Every destructive operation is written to a local audit log for compliance.

---

### Scene 8: Properties Agent — Create Custom Field
**Duration:** 2 minutes

**Narrator script:**
> "Sales ops teams constantly need new fields. The PropertiesAgent lets us create custom properties without leaving the terminal — complete with type validation and group assignment."

**Commands to type:**

```
/hubspot create a custom deal property called Renewal Probability, type number, percentage format, in group dealinformation
```

**Expected output:**
```
PropertiesAgent dispatched — preview mode.
Risk level: MEDIUM (schema change)
Preview:
  Object type: deals
  Property name: renewal_probability
  Label: Renewal Probability
  Type: number
  Display format: percentage
  Field type: number
  Group: dealinformation

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing create property...
Property created successfully.
Internal name: renewal_probability
Label: Renewal Probability
Type: number
Group: dealinformation

This property is now available on all deal records.
```

**Talking points:**
- Schema changes are previewed just like data changes.
- The agent validates property type compatibility before calling the API.
- No need to open HubSpot Settings > Properties > Deals.

---

### Scene 9: Workflows Agent — Build Automation
**Duration:** 2 minutes

**Narrator script:**
> "Let's build a workflow. I want to enroll any contact whose job title contains 'Engineer' into a nurture sequence, then create a task for their owner."

**Commands to type:**

```
/hubspot create workflow named Engineer Nurture: enroll contacts where jobtitle contains Engineer, then create task for owner titled Follow up with engineer lead
```

**Expected output:**
```
WorkflowsAgent dispatched — preview mode.
Risk level: MEDIUM (create workflow)
Preview:
  Workflow name: Engineer Nurture
  Enrollment trigger:
    - Contact property: jobtitle contains "Engineer"
  Actions:
    1. Create task for contact owner
       Title: "Follow up with engineer lead"
       Due: 2 business days
  Status: inactive (review before enabling)

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing create workflow...
Workflow created successfully.
| Workflow ID | Name            | Status   |
|-------------|-----------------|----------|
| wf_901      | Engineer Nurture| inactive |

To activate: /hubspot activate workflow Engineer Nurture
```

**Talking points:**
- Complex automations are expressed in plain English.
- Workflows are created inactive by default so teams can review in HubSpot before enabling.
- The agent understands HubSpot's trigger and action syntax internally.

---

### Scene 10: Lists Agent — Create Segment
**Duration:** 2 minutes

**Narrator script:**
> "Lists are critical for marketing segmentation. Let's build a dynamic list of all contacts at companies in the Software industry with an open deal value over $50,000."

**Commands to type:**

```
/hubspot create dynamic list named High-Value Software Prospects: contacts at companies in Software industry with open deals over $50,000
```

**Expected output:**
```
ListsAgent dispatched — preview mode.
Risk level: MEDIUM (create list)
Preview:
  List name: High-Value Software Prospects
  Type: DYNAMIC
  Filters:
    - Company property: industry = Software
    - Associated deal property: amount > 50000
    - Deal property: dealstage is not closedwon, closedlost

Estimated membership: 12 contacts (preview)

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing create list...
List created successfully.
| List ID | Name                         | Type    | Member Count |
|---------|------------------------------|---------|--------------|
| lst_701 | High-Value Software Prospects| DYNAMIC | 12           |
```

**Talking points:**
- Dynamic lists update automatically as HubSpot data changes.
- The agent translates natural-language conditions into HubSpot filter groups.
- Static lists are also supported for one-off campaigns.

---

### Scene 11: Pipelines Agent — View and Rename Stages
**Duration:** 2 minutes

**Narrator script:**
> "Pipeline management usually means clicking through Settings. Let's view our deal pipeline and rename a stage to match our new sales process."

**Commands to type:**

```
/hubspot show deal pipeline
```

**Expected output:**
```
PipelinesAgent dispatched.
Pipeline: Sales Pipeline (default)
| Stage ID | Label                     | Probability | Display Order |
|----------|---------------------------|-------------|---------------|
| 101      | Appointment Scheduled     | 20%         | 0             |
| 102      | Qualified to Buy          | 40%         | 1             |
| 103      | Presentation Scheduled    | 60%         | 2             |
| 104      | Decision Maker Bought-In  | 80%         | 3             |
| 105      | Closed Won                | 100%        | 4             |
| 106      | Closed Lost               | 0%          | 5             |
```

**Second command:**
```
/hubspot rename deal stage 103 to Demo Completed
```

**Expected output:**
```
PipelinesAgent dispatched — preview mode.
Risk level: MEDIUM (update pipeline stage)
Preview:
  Stage ID: 103
  Current label: Presentation Scheduled
  New label: Demo Completed
  Probability remains: 60%

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing rename stage...
Stage 103 updated to "Demo Completed".
All deals currently in stage 103 retain the new label.
```

**Talking points:**
- Pipeline changes are instant and reflect across all deals in that stage.
- Stage reordering and custom pipeline creation are also supported.
- The agent prevents duplicate stage labels within the same pipeline.

---

### Scene 12: Users Agent — Onboard User
**Duration:** 2 minutes

**Narrator script:**
> "Onboarding a new sales rep usually requires three different screens in HubSpot. Here, we create the user, assign them to the Sales team, and set their role in one command."

**Commands to type:**

```
/hubspot onboard user Taylor Morgan with email taylor.morgan@acme.com as Sales Manager in team Sales
```

**Expected output:**
```
UsersAgent dispatched — preview mode.
Risk level: MEDIUM (create user + assign roles)
Preview:
  Email: taylor.morgan@acme.com
  First name: Taylor
  Last name: Morgan
  Role: Sales Manager
  Team: Sales
  Seat type: Sales Hub (detected from portal tier)

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Executing onboard user...
User invited successfully.
| User ID | Name           | Email                     | Role         | Team  |
|---------|----------------|---------------------------|--------------|-------|
| 401     | Taylor Morgan  | taylor.morgan@acme.com    | Sales Manager| Sales |

An invitation email has been sent. The user will appear as pending until accepted.
```

**Talking points:**
- User provisioning is often a bottleneck in fast-growing teams.
- The agent infers first and last names from the email or explicit input.
- Deactivation and role updates are also supported.

---

### Scene 13: Analytics Agent — Dashboard Metrics
**Duration:** 2 minutes

**Narrator script:**
> "Executives want numbers without hunting through dashboards. Let's pull pipeline velocity and conversion metrics directly into the chat."

**Commands to type:**

```
/hubspot show pipeline velocity this quarter
```

**Expected output:**
```
AnalyticsAgent dispatched.
Pipeline Velocity — Q2 2026
| Metric                     | Value   |
|----------------------------|---------|
| Avg days from open to close| 28.4    |
| Avg days in each stage     | 4.2     |
| Deals closed this quarter  | 17      |
| Total pipeline value       | $840,000|
| Win rate                   | 47%     |

Data source: HubSpot deals API, computed client-side.
```

**Second command:**
```
/hubspot report conversion rate from MQL to SQL this month
```

**Expected output:**
```
AnalyticsAgent dispatched.
Conversion Report — May 2026
| Stage Transition | Count | Conversion Rate |
|------------------|-------|-----------------|
| MQL -> SQL       | 42    | 38%             |
| SQL -> Opportunity| 28   | 67%             |
| Opportunity -> Won| 12    | 43%             |
```

**Talking points:**
- Analytics are computed client-side from raw HubSpot data so the agent can answer questions HubSpot's native reports do not cover.
- Reports can be exported or used to trigger downstream workflows.
- No need to build a custom report in HubSpot's report builder.

---

### Scene 14: Conjunction Routing — Compound Request
**Duration:** 2 minutes

**Narrator script:**
> "Real-world requests are rarely single-domain. Let's ask the agent to create a custom property and then immediately build a workflow that uses it. The parent orchestrator detects dependencies and dispatches agents in the right order."

**Commands to type:**

```
/hubspot create a contact property called NPS Score, type number, and then build a workflow that enrolls contacts where NPS Score is greater than 8 and creates a task for the CSM to send a thank-you gift
```

**Expected output:**
```
Parent Orchestrator: detected compound request with dependency.
Dispatch order: PropertiesAgent -> WorkflowsAgent (workflow references property)

Step 1/2: PropertiesAgent dispatched — preview mode.
Risk level: MEDIUM (create property)
Preview:
  Object type: contacts
  Property name: nps_score
  Label: NPS Score
  Type: number

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Property created. Moving to Step 2/2...

WorkflowsAgent dispatched — preview mode.
Risk level: MEDIUM (create workflow)
Preview:
  Workflow name: NPS Promoter Follow-Up
  Enrollment: contact property nps_score > 8
  Action: create task for CSM — "Send thank-you gift"

Approve? (y/n/details)
```

**Type:**
```
y
```

**Expected output:**
```
Workflow created successfully.
Both steps completed.
Action IDs: act_20260511_005, act_20260511_006
```

**Talking points:**
- The orchestrator understands dependencies between domains.
- Sequential dispatch ensures the property exists before the workflow references it.
- Independent domains are dispatched in parallel to save time.

---

### Scene 15: Raw API Escape Hatch
**Duration:** 2 minutes

**Narrator script:**
> "Even with 13 specialist agents, there will always be edge cases. For power users and unsupported endpoints, the RawAPIAgent provides a fully transparent escape hatch."

**Commands to type:**

```
/hubspot raw api GET /crm/v3/objects/contacts/101?properties=firstname,lastname,email,jobtitle
```

**Expected output:**
```
RawAPIAgent dispatched.
Request: GET /crm/v3/objects/contacts/101
Status: 200 OK

Response:
{
  "id": "101",
  "properties": {
    "firstname": "Dana",
    "lastname": "Smith",
    "email": "dana.smith@acme.com",
    "jobtitle": "VP of Engineering"
  },
  "createdAt": "2026-01-10T14:22:00Z",
  "updatedAt": "2026-05-11T09:45:00Z"
}
```

**Talking points:**
- The raw API tool passes through the exact request and returns the exact JSON.
- No hidden transformations — perfect for debugging or unsupported endpoints.
- Rate limiting and auth are still handled automatically by the shared client.

---

### Scene 16: Error Handling and Recovery
**Duration:** 2 minutes

**Narrator script:**
> "Finally, let's see what happens when things go wrong. I will simulate a request that exceeds our permissions and then show how the agent guides us toward a fix."

**Commands to type:**

```
/hubspot delete company Acme Corp
```

**Expected output (scope error simulation):**
```
ObjectsAgent dispatched — preview mode.
Risk level: DESTRUCTIVE (delete operation, 1 record)

WARNING: Deletions cannot be undone via HubSpot API.

To confirm, type the exact number of records that will be deleted: _
```

**Type:**
```
1
```

**Expected output (permission denied):**
```
HubSpot API error: 403 Forbidden
Required scope: crm.objects.companies.delete
Granted scopes: crm.objects.companies.read, crm.objects.companies.write

The delete scope is missing. Options:
1. Re-authenticate with broader scopes: /hubspot setup 1234567 token <new-token>
2. Request reduced-scope alternative (archive instead of delete)
3. Run raw API to verify: /hubspot raw api GET /integrations/v1/me
```

**Second error demonstration — rate limit:**
```
/hubspot bulk update contacts where createdate is before 2020 set lifecyclestage to other
```

**Expected output:**
```
AnalyticsAgent preview: 1,247 contacts match.
Risk level: HIGH (bulk update > 10 records)
Preview capped at first 1,000. Full operation will affect all 1,247 matching records.

... (user approves) ...

Rate limit reached (429). HubSpot retry-after: 8 seconds.
Pausing execution. Auto-retry in 8s...
Chunk 1/125: 10 updated
...
```

**Talking points:**
- Scope errors are caught proactively, not via cryptic API failures.
- Rate limits are respected with automatic backoff — no manual intervention.
- After max retries, the agent offers clear next steps: rephrase, break into chunks, or use raw API.

---

## 3. Troubleshooting Scenarios

| Issue | Likely Cause | Quick Fix |
|-------|--------------|-----------|
| `Portal not configured` on first `/hubspot` call | Missing `.hubspot-portal` file or setup | Run `/hubspot setup <portal_id> token <pat>` |
| `403 Forbidden` on write | Token lacks required scope | Check scopes in Private App settings and re-auth |
| `429 Rate limit` during bulk ops | Too many requests too fast | The agent auto-retries; if persistent, wait 10s and run `/hubspot refresh` |
| `No contacts found` on search | Sample data not seeded | Create a contact named Dana Smith in the test portal |
| `Workflow creation failed` | Missing `automation.workflows.write` scope | Add the scope in HubSpot and re-authenticate |
| Pending approval seems stuck | User typed `y` but action ID mismatch | Use `approve <id>` with the explicit action ID shown in the preview |
| Wrong portal active | Multi-portal switch incomplete | Run `/hubspot status` to confirm active portal, then `/hubspot portal switch <id>` |
| Agent timeout on large bulk op | Request exceeds sub-agent timeout | Break into smaller segments: `where createdate > 2026-01-01` |
| Undo fails with "snapshot expired" | Undo was attempted after session restart | Undo snapshots are session-local; re-apply changes manually via update commands |

---

## 4. Pre-Demo Checklist

- [ ] Terminal font size increased to 14+ pt
- [ ] Virtual environment activated
- [ ] HubSpot developer test portal is accessible
- [ ] Private App token generated with all required scopes
- [ ] `.hubspot-portal` file present in working directory with correct portal ID
- [ ] Sample contacts, companies, and deals seeded in portal
- [ ] `/hubspot status` returns healthy response with correct portal
- [ ] `/hubspot portal list` shows expected portals
- [ ] Browser tab with HubSpot UI open for side-by-side verification
- [ ] Backup portal ID noted in case of rate-limiting
- [ ] Demo script printed or open on a second screen for the presenter
- [ ] 15-minute buffer scheduled before the demo for last-minute fixes

---

## Appendix: Agent Reference

| Agent | Domain | Sample Trigger Phrases |
|-------|--------|------------------------|
| ObjectsAgent | Core CRUD | contact, company, deal, ticket, record |
| PropertiesAgent | Schema | property, field, custom field, schema |
| WorkflowsAgent | Automation | workflow, automation, trigger, enroll |
| ListsAgent | Segmentation | list, segment, add to list, dynamic list |
| PipelinesAgent | Pipelines | pipeline, stage, move to, rename stage |
| UsersAgent | Permissions | user, onboard, permission, team, owner |
| HygieneAgent | Data Quality | duplicate, merge, dedup, bulk update, clean |
| AnalyticsAgent | Reporting | report, metric, velocity, conversion, how many |
| AssociationsAgent | Relationships | associate, link, relationship, related to |
| EngagementsAgent | Activity | note, task, email, meeting, call, log activity |
| CustomObjectsAgent | Custom Objects | custom object, object schema, custom record type |
| ServiceAgent | Tickets & Feedback | ticket, ticket pipeline, customer feedback, SLA |
| RawAPIAgent | Escape-hatch | raw api, custom endpoint, direct api, not covered |

---

*Document version: 2026-05-11*
*Maintainer: HubSpot Agent team*
*Update cadence: per release or when CLI surface changes*
