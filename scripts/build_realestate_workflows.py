#!/usr/bin/env python3
"""
Build Real Estate CRM Workflows in HubSpot portal 148408595.
Implements all 12 workflows from Section 9 of the architecture doc.
Run with: PYTHONPATH=src .venv/bin/python scripts/build_realestate_workflows.py
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

# ---------------------------------------------------------------------------
# Workflow definitions (12 real estate workflows)
# ---------------------------------------------------------------------------

WORKFLOWS: list[dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # 9.1 Lead-routing and speed-to-lead
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Lead Routing — Speed to Lead",
        "type": "CONTACT_FLOW",
        "enrollment": {
            "type": "EVENT_BASED",
            "event": "CONTACT_CREATION",
            "filter": {
                "filterGroups": [
                    {
                        "filters": [
                            {"property": "lifecyclestage", "operator": "IS_EQUAL_TO", "value": "lead"},
                        ]
                    }
                ]
            },
        },
        "actions": [
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Speed-to-lead: Contact new lead within 5 minutes",
                    "due_date": "{{timestamp + 5m}}",
                    "assignee": "{{contact.hubspot_owner_id}}",
                    "notes": "New lead captured. First contact must happen within 5 minutes for optimal conversion.",
                    "priority": "HIGH",
                },
            },
            {
                "type": "SEND_EMAIL",
                "properties": {
                    "from_email": "{{hubspot.owner.email}}",
                    "subject": "New lead assigned: {{contact.firstname}} {{contact.lastname}}",
                    "body": "A new lead has been assigned to you. Contact them within 5 minutes for best conversion rates.",
                },
            },
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "MINUTES", "amount": 30}},
            },
            {
                "type": "BRANCH",
                "properties": {
                    "condition": {
                        "field": "hs_task_status",
                        "operator": "IS_NOT_EQUAL_TO",
                        "value": "COMPLETED",
                    },
                    "true_actions": [
                        {
                            "type": "CREATE_TASK",
                            "properties": {
                                "title": "ESCALATE: Lead not contacted within 30 min",
                                "due_date": "{{timestamp + 15m}}",
                                "assignee": "{{hubspot.team.lead}}",
                                "notes": "Lead {{contact.firstname}} {{contact.lastname}} was not contacted within 30 minutes. Please follow up immediately.",
                                "priority": "HIGH",
                            },
                        },
                    ],
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.2 Buyer search-criteria matching (digest to agent)
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Buyer Criteria Match — Agent Digest",
        "type": "CONTACT_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "price_range_max",
            "operator": "IS_GREATER_THAN",
            "value": "0",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "HOURS", "amount": 1}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Send matching listings to {{contact.firstname}}",
                    "due_date": "{{timestamp + 1d}}",
                    "assignee": "{{contact.hubspot_owner_id}}",
                    "notes": "Buyer has updated search criteria. Search Active/Coming Soon listings and send a digest of matches.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.3 Pre-listing prep checklist
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Pre-Listing Prep Checklist",
        "type": "DEAL_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "dealstage",
            "operator": "IS_EQUAL_TO",
            "value": "prelistingprep",
        },
        "actions": [
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Order professional photos",
                    "due_date": "{{timestamp + 2d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Schedule photographer for listing. Confirm date/time with seller.",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Schedule cleaner / stager",
                    "due_date": "{{timestamp + 3d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Arrange pre-listing cleaning and staging if needed.",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Install yard signage",
                    "due_date": "{{timestamp + 3d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Order and install For Sale sign with QR code.",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Write MLS public and agent remarks",
                    "due_date": "{{timestamp + 2d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Draft compelling MLS remarks. Get seller approval.",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Schedule first open house",
                    "due_date": "{{timestamp + 5d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Pick date within first weekend of listing. Confirm with seller.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.4 Contingency deadline alerts (Buyer Pipeline >= Under Contract)
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Buyer Contingency — Inspection Alert",
        "type": "DEAL_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "contingency_inspection_deadline",
            "operator": "IS_KNOWN",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 3, "direction": "BEFORE", "anchor_property": "contingency_inspection_deadline"}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Inspection contingency expires in 3 days — confirm objection deadline",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Inspection contingency deadline is approaching. Confirm with buyer if they intend to submit objections.",
                    "priority": "HIGH",
                },
            },
        ],
    },
    {
        "name": "[RE] Buyer Contingency — Appraisal Alert",
        "type": "DEAL_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "contingency_appraisal_deadline",
            "operator": "IS_KNOWN",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 3, "direction": "BEFORE", "anchor_property": "contingency_appraisal_deadline"}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Appraisal contingency expires in 3 days",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Appraisal contingency deadline approaching. Ensure appraisal is scheduled and lender is updated.",
                    "priority": "HIGH",
                },
            },
        ],
    },
    {
        "name": "[RE] Buyer Contingency — Financing Alert",
        "type": "DEAL_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "contingency_financing_deadline",
            "operator": "IS_KNOWN",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 3, "direction": "BEFORE", "anchor_property": "contingency_financing_deadline"}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Financing contingency expires in 3 days",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Financing contingency deadline approaching. Check with lender on loan commitment timeline.",
                    "priority": "HIGH",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.5 Showing follow-up
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Showing — Post-Showing Feedback Task",
        "type": "CUSTOM_OBJECT_FLOW",
        "objectTypeId": "showings",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "showing_status",
            "operator": "IS_EQUAL_TO",
            "value": "Completed",
        },
        "actions": [
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Capture showing feedback from buyer",
                    "due_date": "{{timestamp + 1d}}",
                    "assignee": "{{showing.showing_agent_contact_id}}",
                    "notes": "Showing completed. Call/text buyer for feedback and update showing record with likes, concerns, and objection category.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.6 Offer presentation cadence
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Offer — Present to Seller within 24h",
        "type": "CUSTOM_OBJECT_FLOW",
        "objectTypeId": "offers",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "offer_status",
            "operator": "IS_EQUAL_TO",
            "value": "Submitted",
        },
        "actions": [
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Present offer to seller within 24 hours",
                    "due_date": "{{timestamp + 1d}}",
                    "assignee": "{{offer.listing_agent_contact_id}}",
                    "notes": "New offer received. Schedule presentation to seller and document seller response.",
                    "priority": "HIGH",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.7 Open House lead processing
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Open House — New Sign-In Follow-Up",
        "type": "CONTACT_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "source_detail",
            "operator": "IS_EQUAL_TO",
            "value": "Open House Sign-In",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "HOURS", "amount": 1}},
            },
            {
                "type": "SEND_EMAIL",
                "properties": {
                    "from_email": "{{hubspot.owner.email}}",
                    "subject": "Thanks for visiting our open house!",
                    "body": "Hi {{contact.firstname}}, thanks for stopping by! Here's a link to similar listings: [LINK]. Let me know if you'd like to schedule a private showing.",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Call open house sign-in to qualify",
                    "due_date": "{{timestamp + 1d}}",
                    "assignee": "{{contact.hubspot_owner_id}}",
                    "notes": "Follow up with open house attendee. Qualify timeline, budget, and search criteria.",
                },
            },
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 3}},
            },
            {
                "type": "BRANCH",
                "properties": {
                    "condition": {
                        "field": "lifecyclestage",
                        "operator": "IS_EQUAL_TO",
                        "value": "lead",
                    },
                    "true_actions": [
                        {
                            "type": "SEND_SMS",
                            "properties": {
                                "message": "Hi {{contact.firstname}}, just following up from the open house. Any questions about the property or area? — {{hubspot.owner.firstname}}",
                            },
                        },
                    ],
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.8 Stale-deal alerts
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Stale Buyer Deal — No Showings in 14 Days",
        "type": "DEAL_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "dealstage",
            "operator": "IS_ANY_OF",
            "value": ["activesearch", "touring", "offersubmitted"],
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 14}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Stale deal alert: No showing activity in 14 days",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "This buyer deal has been idle for 14+ days. Re-engage buyer with new listings or check if they've gone cold.",
                },
            },
        ],
    },
    {
        "name": "[RE] Stale Listing — High DOM, No Showings",
        "type": "CUSTOM_OBJECT_FLOW",
        "objectTypeId": "listings",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "listing_status",
            "operator": "IS_EQUAL_TO",
            "value": "Active",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 21}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Stale listing: 21+ days on market, review pricing",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{listing.listing_agent_contact_id}}",
                    "notes": "Listing has been active 21+ days with low showing activity. Consider price reduction, improved staging, or enhanced marketing.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.9 Closing-day workflow
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Closing Day — Post-Close Sequence",
        "type": "DEAL_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "dealstage",
            "operator": "IS_EQUAL_TO",
            "value": "closedwon",
        },
        "actions": [
            {
                "type": "SET_PROPERTY",
                "properties": {
                    "property": "lifecyclestage",
                    "value": "customer",
                },
            },
            {
                "type": "SET_PROPERTY",
                "properties": {
                    "property": "anniversary_date",
                    "value": "{{timestamp}}",
                },
            },
            {
                "type": "SEND_EMAIL",
                "properties": {
                    "from_email": "{{hubspot.owner.email}}",
                    "subject": "Congratulations on your closing!",
                    "body": "Dear {{contact.firstname}}, congratulations on your new home! I'm here if you need anything. Welcome to the neighborhood!",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "30-day post-close check-in call",
                    "due_date": "{{timestamp + 30d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Call client to check how they're settling in. Ask for feedback and any issues.",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "6-month post-close check-in",
                    "due_date": "{{timestamp + 180d}}",
                    "assignee": "{{deal.hubspot_owner_id}}",
                    "notes": "Check in with past client. Offer market update and referral request.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.10 Anniversary and nurture cadences
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Anniversary Touch — Annual Check-In",
        "type": "CONTACT_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "lifecyclestage",
            "operator": "IS_EQUAL_TO",
            "value": "customer",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 335, "direction": "AFTER", "anchor_property": "anniversary_date"}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Anniversary touch — call {{contact.firstname}} today",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{contact.hubspot_owner_id}}",
                    "notes": "It's been nearly a year since closing. Call to congratulate, offer market update, and ask for referrals.",
                },
            },
            {
                "type": "SEND_EMAIL",
                "properties": {
                    "from_email": "{{hubspot.owner.email}}",
                    "subject": "Happy home-iversary!",
                    "body": "Hi {{contact.firstname}}, it's been a year since you closed on your home! I hope you're loving it. Here's a quick market update for your neighborhood. Let me know if you ever have real estate questions.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.11 Vendor insurance and license expiry
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Vendor — Insurance/License Expiry Alert",
        "type": "COMPANY_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "insurance_expiry_date",
            "operator": "IS_KNOWN",
        },
        "actions": [
            {
                "type": "DELAY",
                "properties": {"delay": {"unit": "DAYS", "amount": 30, "direction": "BEFORE", "anchor_property": "insurance_expiry_date"}},
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Re-verify {{company.name}} insurance/license before next referral",
                    "due_date": "{{timestamp}}",
                    "assignee": "{{hubspot.team.admin}}",
                    "notes": "Vendor insurance or license expires in 30 days. Request updated certificate before referring to clients.",
                },
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 9.12 Compliance / data hygiene
    # -----------------------------------------------------------------------
    {
        "name": "[RE] Hygiene — Unassigned Contact Routing",
        "type": "CONTACT_FLOW",
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "hubspot_owner_id",
            "operator": "IS_UNKNOWN",
        },
        "actions": [
            {
                "type": "SET_PROPERTY",
                "properties": {
                    "property": "hubspot_owner_id",
                    "value": "{{hubspot.team.lead}}",
                },
            },
            {
                "type": "CREATE_TASK",
                "properties": {
                    "title": "Unassigned contact routed — review and reassign",
                    "due_date": "{{timestamp + 1d}}",
                    "assignee": "{{hubspot.team.lead}}",
                    "notes": "Contact {{contact.firstname}} {{contact.lastname}} had no owner and was routed to team lead. Please review and assign to appropriate agent.",
                },
            },
        ],
    },
]


class WorkflowBuilder:
    def __init__(self, client: HubSpotClient, portal_id: str):
        self.client = client
        self.portal_id = portal_id
        self.created: list[str] = []
        self.errors: list[str] = []

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.client.post(path, portal_id=self.portal_id, body=body)
        return resp.body

    async def create_workflow(self, workflow: dict[str, Any]) -> str | None:
        try:
            body = {
                "name": workflow["name"],
                "type": workflow["type"],
                "actions": workflow.get("actions", []),
                "enrollment": workflow.get("enrollment", {}),
            }
            if workflow.get("objectTypeId"):
                body["objectTypeId"] = workflow["objectTypeId"]
            result = await self._post("/automation/v4/workflows", body=body)
            if "error" in result or "message" in result:
                self.errors.append(f"Workflow '{workflow['name']}': {result.get('message', result)}")
                return None
            wf_id = result.get("id")
            self.created.append(workflow["name"])
            print(f"  Created workflow: {workflow['name']} (id={wf_id})")
            return wf_id
        except Exception as exc:
            self.errors.append(f"Workflow '{workflow['name']}': {exc}")
            return None


async def main() -> None:
    portal = load_portal_config(PORTAL_ID)
    if not portal:
        print(f"Portal {PORTAL_ID} not configured. Run /hubspot portal token {PORTAL_ID}")
        sys.exit(1)

    client = HubSpotClient(portal)
    builder = WorkflowBuilder(client, PORTAL_ID)

    try:
        print(f"\n=== Creating {len(WORKFLOWS)} real estate workflows ===")
        for wf in WORKFLOWS:
            await builder.create_workflow(wf)

        print("\n=== Summary ===")
        print(f"  Created: {len(builder.created)} workflows")
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
