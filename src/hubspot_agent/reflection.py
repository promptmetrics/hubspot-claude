from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.errors import HubSpotError


@dataclass
class ReflectionResult:
    object_id: str
    object_type: str
    verified: bool
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    fetched_properties: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "object_type": self.object_type,
            "verified": self.verified,
            "mismatches": self.mismatches,
            "missing_fields": self.missing_fields,
            "fetched_properties": self.fetched_properties,
            "timestamp": self.timestamp,
        }


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        stripped = value.strip().lower()
        if stripped in ("true", "yes", "1"):
            return True
        if stripped in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value.strip()
    if isinstance(value, (dict, list)):
        return value
    return value


def _values_match(expected: Any, actual: Any) -> bool:
    expected_norm = _normalize_value(expected)
    actual_norm = _normalize_value(actual)
    if type(expected_norm) != type(actual_norm):
        return str(expected_norm) == str(actual_norm)
    if isinstance(expected_norm, dict) and isinstance(actual_norm, dict):
        if set(expected_norm.keys()) != set(actual_norm.keys()):
            return False
        return all(_values_match(expected_norm[k], actual_norm[k]) for k in expected_norm)
    if isinstance(expected_norm, list) and isinstance(actual_norm, list):
        if len(expected_norm) != len(actual_norm):
            return False
        return all(_values_match(e, a) for e, a in zip(expected_norm, actual_norm))
    return expected_norm == actual_norm


async def reflect_on_write(
    portal_config: PortalConfig,
    object_type: str,
    object_id: str,
    expected_properties: dict[str, Any],
    client: HubSpotClient | None = None,
) -> ReflectionResult:
    """Re-fetch a modified resource and verify field-level match.

    Compares the expected property values against the live record
    returned by HubSpot.  Returns a ``ReflectionResult`` detailing
    mismatches, missing fields, and overall verification status.
    """
    should_close = client is None
    if client is None:
        client = HubSpotClient(portal_config)

    try:
        resp = await client.get(
            f"/crm/v3/objects/{object_type}/{object_id}",
            portal_id=portal_config.portal_id,
        )
        body = resp.body
    except HubSpotError as exc:
        return ReflectionResult(
            object_id=object_id,
            object_type=object_type,
            verified=False,
            mismatches=[{"field": "__fetch__", "error": str(exc)}],
        )
    finally:
        if should_close:
            await client.close()

    fetched = body.get("properties", {})
    mismatches: list[dict[str, Any]] = []
    missing: list[str] = []

    for field, expected in expected_properties.items():
        actual = fetched.get(field)
        if actual is None and field not in fetched:
            missing.append(field)
            continue
        if not _values_match(expected, actual):
            mismatches.append({
                "field": field,
                "expected": expected,
                "actual": actual,
            })

    verified = not mismatches and not missing

    return ReflectionResult(
        object_id=object_id,
        object_type=object_type,
        verified=verified,
        mismatches=mismatches,
        missing_fields=missing,
        fetched_properties=fetched,
    )
