from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig


class CapabilityMatrix(BaseModel):
    tier: str = "unknown"
    contacts: bool = True
    companies: bool = True
    deals: bool = True
    tickets: bool = True
    workflows: bool = False
    lists: bool = True
    pipelines: bool = True
    users: bool = False
    custom_objects: bool = False
    calculated_properties: bool = False
    service_automation: bool = False
    marketing: bool = False
    cms: bool = False


class CapabilityCache:
    TTL_SECONDS = 86400  # 24 hours

    def __init__(self, portal_id: str, base_dir: Path | None = None) -> None:
        self.portal_id = portal_id
        self.base_dir = base_dir or (Path.home() / ".claude" / "hubspot" / portal_id)
        self.cache_file = self.base_dir / "capabilities.json"
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_file.exists():
            try:
                self._data = json.loads(self.cache_file.read_text())
            except json.JSONDecodeError:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self._data, indent=2))

    def get(self) -> CapabilityMatrix | None:
        entry = self._data.get("matrix")
        if entry is None:
            return None
        ts = entry.get("_timestamp", 0)
        if time.time() - ts > self.TTL_SECONDS:
            return None
        return CapabilityMatrix.model_validate(entry.get("data", {}))

    def set(self, matrix: CapabilityMatrix) -> None:
        self._data["matrix"] = {"_timestamp": time.time(), "data": matrix.model_dump()}
        self._save()

    def invalidate(self) -> None:
        self._data = {}
        if self.cache_file.exists():
            self.cache_file.unlink()


_AGENT_CAPABILITY_REQUIREMENTS: dict[str, list[str]] = {
    "workflows": ["workflows"],
    "users": ["users"],
    "service": ["service_automation"],
    "marketing": ["marketing"],
    "cms": ["cms"],
}


async def probe_portal(portal_config: PortalConfig) -> CapabilityMatrix:
    cache = CapabilityCache(portal_config.portal_id)
    cached = cache.get()
    if cached is not None:
        return cached

    client = HubSpotClient(portal_config)
    matrix = CapabilityMatrix()

    try:
        try:
            resp = await client.get("/account-info/v3/details", portal_id=portal_config.portal_id)
            matrix.tier = resp.body.get("tier", "unknown")
        except Exception:
            pass

        try:
            await client.get("/crm/v3/schemas", portal_id=portal_config.portal_id)
            matrix.custom_objects = True
        except Exception:
            matrix.custom_objects = False

        try:
            await client.get("/automation/v4/workflows?limit=1", portal_id=portal_config.portal_id)
            matrix.workflows = True
        except Exception:
            matrix.workflows = False

        try:
            await client.get("/settings/v3/users?limit=1", portal_id=portal_config.portal_id)
            matrix.users = True
        except Exception:
            matrix.users = False

        try:
            resp = await client.get("/crm/v3/properties/contacts", portal_id=portal_config.portal_id)
            results = resp.body.get("results", [])
            has_calc = any(p.get("type") == "calculation" for p in results)
            if not has_calc:
                resp2 = await client.get("/crm/v3/properties/companies", portal_id=portal_config.portal_id)
                results2 = resp2.body.get("results", [])
                has_calc = any(p.get("type") == "calculation" for p in results2)
            matrix.calculated_properties = has_calc
        except Exception:
            matrix.calculated_properties = False

        try:
            await client.get("/marketing/v3/emails?limit=1", portal_id=portal_config.portal_id)
            matrix.marketing = True
        except Exception:
            matrix.marketing = False

        try:
            await client.get("/cms/v3/pages/site-pages?limit=1", portal_id=portal_config.portal_id)
            matrix.cms = True
        except Exception:
            matrix.cms = False
    finally:
        await client.close()

    cache.set(matrix)
    return matrix


def has_capability(matrix: CapabilityMatrix, feature: str) -> bool:
    return getattr(matrix, feature, False)


def validate_capabilities(
    agent_names: list[str],
    matrix: CapabilityMatrix,
) -> dict[str, list[str]]:
    blocked: dict[str, list[str]] = {}
    for name in agent_names:
        required = _AGENT_CAPABILITY_REQUIREMENTS.get(name, [])
        missing = [f for f in required if not has_capability(matrix, f)]
        if missing:
            blocked[name] = missing
    return blocked


def capability_explanation(feature: str) -> str:
    explanations: dict[str, str] = {
        "workflows": "Workflow automation requires a Professional or Enterprise HubSpot subscription.",
        "users": "User management requires a Professional or Enterprise HubSpot subscription.",
        "custom_objects": "Custom objects require an Enterprise HubSpot subscription.",
        "calculated_properties": "Calculated properties require an Enterprise HubSpot subscription.",
        "service_automation": "Service automation requires a Professional or Enterprise HubSpot subscription.",
        "marketing": "Marketing emails and campaigns require a Marketing Hub Professional or Enterprise subscription.",
        "cms": "CMS content management requires a CMS Hub or Content Hub subscription.",
    }
    return explanations.get(feature, f"{feature} is not available on this portal.")
