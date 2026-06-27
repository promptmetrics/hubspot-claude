from pathlib import Path

import httpx
import pytest

from hubspot_agent.capabilities import CapabilityMatrix
from hubspot_agent.config import PortalConfig, load_portal_config, save_portal_config
from hubspot_agent.setup import REQUIRED_SCOPES, run_setup


def _patch_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.maintenance.Path.home", lambda: tmp_path)


@pytest.mark.asyncio
async def test_setup_needs_auth_no_method(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    result = await run_setup("123")
    assert result["status"] == "needs_auth"
    assert "no token configured" in result["message"]


@pytest.mark.asyncio
async def test_setup_private_app_token(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    result = await run_setup("123", method="token", token="pat-na1-test")
    assert result["status"] == "complete"
    assert "Setup complete" in result["message"]

    loaded = load_portal_config("123")
    assert loaded is not None
    assert loaded.token == "pat-na1-test"


@pytest.mark.asyncio
async def test_setup_private_app_alias(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    result = await run_setup("123", method="private_app", token="pat-na1-test")
    assert result["status"] == "complete"
    assert "Setup complete" in result["message"]

    loaded = load_portal_config("123")
    assert loaded is not None
    assert loaded.auth_type == "private_app"


@pytest.mark.asyncio
async def test_setup_token_missing_token(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    result = await run_setup("123", method="token")
    assert result["status"] == "error"
    assert "Usage" in result["message"]


@pytest.mark.asyncio
async def test_setup_unknown_method(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    result = await run_setup("123", method="unknown")
    assert result["status"] == "error"
    assert "Unknown auth method" in result["message"]


@pytest.mark.asyncio
async def test_setup_existing_portal_probes_capabilities(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    probe_called = False
    warm_called = False

    async def mock_probe(portal_config):
        nonlocal probe_called
        probe_called = True
        return CapabilityMatrix(workflows=True, tier="Professional")

    async def mock_warm(portal_config):
        nonlocal warm_called
        warm_called = True
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert probe_called
    assert warm_called
    assert result["capabilities"] is not None
    assert result["capabilities"].workflows is True
    assert result["capabilities"].tier == "Professional"
    assert "Capabilities:" in result["message"]
    assert "contacts:" in result["message"]
    assert "workflows:" in result["message"]


@pytest.mark.asyncio
async def test_setup_scope_gaps_reported(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=True)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(
        PortalConfig(
            portal_id="123",
            token="test-token",
            scopes_granted=["crm.objects.contacts.read"],
        )
    )

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["missing_scopes"] is not None
    assert "crm.objects.contacts.write" in result["missing_scopes"]
    assert "crm.objects.contacts.read" not in result["missing_scopes"]
    assert "Missing scopes:" in result["message"]
    assert "Granted scopes:" in result["message"]


@pytest.mark.asyncio
async def test_setup_all_scopes_granted(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=True)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(
        PortalConfig(
            portal_id="123",
            token="test-token",
            scopes_granted=[
                "crm.objects.contacts.read",
                "crm.objects.contacts.write",
                "crm.objects.companies.read",
                "crm.objects.companies.write",
                "crm.objects.deals.read",
                "crm.objects.deals.write",
                "crm.schemas.contacts.read",
                "crm.schemas.contacts.write",
                "crm.schemas.companies.read",
                "crm.schemas.companies.write",
                "crm.schemas.deals.read",
                "crm.schemas.deals.write",
                "tickets",
                "crm.lists.read",
                "crm.lists.write",
                "automation",
                "crm.pipelines.orders.read",
                "crm.pipelines.orders.write",
                "settings.users.read",
                "settings.users.write",
                "crm.objects.appointments.read",
                "crm.objects.appointments.write",
                "sales-email-read",
            ],
        )
    )

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["missing_scopes"] == []
    assert "All required scopes are granted" in result["message"]


@pytest.mark.asyncio
async def test_setup_maintenance_failure_ignored(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_maintenance(portal_id):
        raise RuntimeError("disk full")

    monkeypatch.setattr("hubspot_agent.setup.run_maintenance", mock_maintenance)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert "Setup complete" in result["message"]


@pytest.mark.asyncio
async def test_setup_probe_failure_ignored(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        raise RuntimeError("network error")

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["capabilities"] is None


@pytest.mark.asyncio
async def test_setup_warm_failure_ignored(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_warm(portal_config):
        raise RuntimeError("cache error")

    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert "Setup complete" in result["message"]


@pytest.mark.asyncio
async def test_setup_post_auth_token_missing(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)
    # Make save_portal_config a no-op so load_portal_config still returns None
    monkeypatch.setattr("hubspot_agent.setup.save_portal_config", lambda portal: None)
    result = await run_setup("123", method="token", token="pat-na1-test")
    assert result["status"] == "error"
    assert "token is still missing" in result["message"]


@pytest.mark.asyncio
async def test_setup_schema_counts_reported(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=True)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    from hubspot_agent.cache import SchemaCache
    expected_dir = tmp_path / ".claude" / "hubspot" / "123"
    cache = SchemaCache("123", base_dir=expected_dir)
    cache.set("contacts", {"results": [{"name": "email"}, {"name": "phone"}]})
    cache.set("companies", {"results": [{"name": "domain"}]})
    cache.set("deals", {"results": [{"name": "amount"}, {"name": "stage"}, {"name": "close_date"}]})

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["schema_counts"] is not None
    assert result["schema_counts"]["contacts"] == 2
    assert result["schema_counts"]["companies"] == 1
    assert result["schema_counts"]["deals"] == 3
    assert result["schema_counts"].get("tickets") is None
    assert "Schema cached:" in result["message"]
    assert "contacts: 2 properties" in result["message"]
    assert "companies: 1 properties" in result["message"]
    assert "deals: 3 properties" in result["message"]


@pytest.mark.asyncio
async def test_setup_capability_report_all_features(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(
            tier="Enterprise",
            workflows=True,
            users=True,
            custom_objects=True,
            calculated_properties=True,
        )

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert "Portal Tier:** Enterprise" in result["message"]
    for feature in [
        "contacts", "companies", "deals", "tickets",
        "workflows", "lists", "pipelines", "users",
        "custom_objects", "calculated_properties",
    ]:
        assert f"{feature}: ✓" in result["message"]


@pytest.mark.asyncio
async def test_setup_capability_report_disabled_features(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(
            tier="Starter",
            workflows=False,
            users=False,
            custom_objects=False,
            calculated_properties=False,
        )

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    for feature in [
        "contacts", "companies", "deals", "tickets",
        "lists", "pipelines",
    ]:
        assert f"{feature}: ✓" in result["message"]
    for feature in ["workflows", "users", "custom_objects", "calculated_properties"]:
        assert f"{feature}: ✗" in result["message"]


@pytest.mark.asyncio
async def test_setup_cli_integration(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=False)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    from hubspot_agent.cli import _handle_setup

    save_portal_config(PortalConfig(portal_id="456", token="test-token"))

    output = _handle_setup("456", str(tmp_path))
    assert "Setup complete" in output
    assert "456" in output

    portal_file = tmp_path / ".hubspot-portal"
    assert portal_file.exists()
    assert portal_file.read_text().strip() == "456"


@pytest.mark.asyncio
async def test_setup_schema_counts_empty(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=True)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["schema_counts"] is None
    assert "Schema cached:" not in result["message"]


@pytest.mark.asyncio
async def test_setup_scope_gaps_none_granted(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=True)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["missing_scopes"] is not None
    assert len(result["missing_scopes"]) == len(REQUIRED_SCOPES)
    assert "crm.objects.contacts.read" in result["missing_scopes"]
    assert "Missing scopes:" in result["message"]


@pytest.mark.asyncio
async def test_setup_schema_counts_malformed_cache(respx_mock, tmp_path, monkeypatch):
    _patch_config_dir(monkeypatch, tmp_path)

    async def mock_probe(portal_config):
        return CapabilityMatrix(workflows=True)

    async def mock_warm(portal_config):
        return None

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", mock_probe)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", mock_warm)
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    from hubspot_agent.cache import SchemaCache
    expected_dir = tmp_path / ".claude" / "hubspot" / "123"
    cache = SchemaCache("123", base_dir=expected_dir)
    cache.set("contacts", {"results": "not_a_list"})
    cache.set("companies", {"results": [{"name": "domain"}]})

    result = await run_setup("123")
    assert result["status"] == "complete"
    assert result["schema_counts"] is not None
    assert "contacts" not in result["schema_counts"]
    assert result["schema_counts"].get("companies") == 1


# Registry of HubSpot OAuth scopes that are officially SELECTABLE in the
# developer app's Auth-tab scope picker (the set we may request at authorize
# time). Sourced from https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/scopes
#
# DELIBERATELY EXCLUDED: crm.objects.notes/calls/meetings/tasks/emails.{read,write}
# are HubSpot "hidden scopes" — the API references them in 403 MISSING_SCOPES
# responses, but they are NOT selectable in any app picker (OAuth or private
# app). Requesting them at authorize time makes HubSpot reject the whole
# authorize call. They are intentionally absent here so the regression test
# below catches any re-introduction into REQUIRED_SCOPES. The internal
# scope_registry still names them as the honest API requirement for the
# engagement create tools (those 403 at call time on OAuth portals).
#
# The regression test below guards against re-introducing invented OR hidden
# scope strings (e.g. automation.workflows.*, crm.pipelines.*,
# crm.objects.engagements.*, crm.objects.tickets.*, crm.objects.notes.*).
_VALID_HUBSPOT_SCOPES = {
    # CRM objects (granular, selectable)
    "crm.objects.contacts.read", "crm.objects.contacts.write",
    "crm.objects.companies.read", "crm.objects.companies.write",
    "crm.objects.deals.read", "crm.objects.deals.write",
    "crm.objects.appointments.read", "crm.objects.appointments.write",
    # CRM schemas
    "crm.schemas.contacts.read", "crm.schemas.contacts.write",
    "crm.schemas.companies.read", "crm.schemas.companies.write",
    "crm.schemas.deals.read", "crm.schemas.deals.write",
    # Tickets (single R/W scope)
    "tickets",
    # Lists
    "crm.lists.read", "crm.lists.write",
    # Automation (Pro/Enterprise)
    "automation",
    # Pipelines (orders only)
    "crm.pipelines.orders.read", "crm.pipelines.orders.write",
    # Users / settings
    "settings.users.read", "settings.users.write",
    # Email engagements (legacy, still required for /crm/v3/objects/emails)
    "sales-email-read",
    # Timeline events
    "timeline",
}


def test_required_scopes_are_valid_hubspot_scopes():
    """Every scope we request at OAuth authorize time must be selectable by the
    app (never an invented or hidden HubSpot scope)."""
    invalid = [s for s in REQUIRED_SCOPES if s not in _VALID_HUBSPOT_SCOPES]
    assert invalid == [], f"REQUIRED_SCOPES contains non-selectable HubSpot scopes: {invalid}"
