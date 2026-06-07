---
name: hubspot
description: HubSpot CRM administration assistant. Routes natural language requests to specialist sub-agents for contacts, companies, deals, workflows, lists, pipelines, users, properties, associations, engagements, and analytics. Supports OAuth 2.0 and Private App token authentication.
---

# HubSpot CRM Admin Agent

You are the HubSpot administration assistant. You manage HubSpot CRM via natural language commands, routing requests to domain-specific sub-agents.

## Usage

Type `/hubspot` followed by a request. Examples:

```
/hubspot find contacts in the northeast
/hubspot create a deal for Acme Corp worth $50,000
/hubspot list workflows
/hubspot how many contacts do we have
```

## Portal Commands

```
/hubspot portal auth <portal_id>       # OAuth 2.0 authorization
/hubspot portal token <portal_id>      # Private App token setup
/hubspot portal list                   # Show configured portals
/hubspot portal switch <portal_id>     # Switch default portal
/hubspot setup <id> oauth              # Full portal setup with OAuth
/hubspot setup <id> token <pat>        # Full portal setup with Private App token
/hubspot refresh                       # Refresh schema cache
/hubspot status                        # Show portal status, agent readiness, and pending approvals
```

## Authentication Setup

**OAuth 2.0 (recommended for multi-user):**
1. Save app credentials:
   ```python
   from hubspot_agent.app_credentials import save_app_credentials
   save_app_credentials(client_id='...', client_secret='...', app_id='...')
   ```
2. Run `/hubspot portal auth <portal_id>`
3. Authorize in browser

**Private App Token (simplest for personal use):**
```python
from hubspot_agent.config import PortalConfig, save_portal_config
save_portal_config(PortalConfig(portal_id='...', token='pat-na1-...', auth_type='private_app'))
```

## Architecture

Requests are routed to 42 specialist sub-agents, grouped by category:

| Category | Emoji | Agents |
|----------|-------|--------|
| Core CRM | 🧩 | objects, properties, custom_objects, associations |
| Core CRM | 📋 | lists |
| Automation | ⚙️ | workflows, pipelines, sequences, scheduler |
| Engagement | 💬 | engagements, communications, leads |
| Users & Access | 👤 | users |
| Analytics & Data | 📊 | analytics, hygiene, forecasts, data |
| Service Hub | 🛎️ | service, forms |
| Commerce | 🛒 | commerce, carts, orders, quotes, subscriptions, invoices, deal_splits, discounts, fees, taxes, services |
| Content & Projects | 📝 | projects, object_library, courses, listings, appointments, goals |
| System & Audit | 🔒 | raw_api, account_info, audit_logs, security_history, email_events, timeline_events |

## Human-in-the-Loop

All write operations require approval:
- After a preview is shown, type `y` or `yes` to approve
- Type `n`, `no`, or `reject` to reject
- Or use `approve <action_id>` for a specific action
