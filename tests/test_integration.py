import pytest

from hubspot_agent.cli import hubspot_command


@pytest.fixture
def mock_portal(tmp_path, monkeypatch):
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")
    return str(tmp_path)


def test_integration_read_query(mock_portal):
    from unittest.mock import patch

    # Multi-domain requests now default to the loop orchestrator.
    with patch(
        "hubspot_agent.cli.run_loop",
        return_value="📍 Portal: 123 (unknown)\n\nGoal: count contacts\n\n### Steps\n1. **objects** — search contacts\n2. **analytics** — calculate count",
    ):
        result = hubspot_command("how many contacts", working_dir=mock_portal)
    assert "Portal: 123" in result
    assert "analytics" in result


def test_integration_write_routing(mock_portal):
    from unittest.mock import patch

    with patch(
        "hubspot_agent.cli.run_loop",
        return_value="📍 Portal: 123 (unknown)\n\nGoal: create contact\n\n### Steps\n1. **objects** — create contact",
    ):
        result = hubspot_command("create a contact with email test@example.com", working_dir=mock_portal)
    assert "Portal: 123" in result
    assert "objects" in result


def test_integration_portal_switch(mock_portal):
    result = hubspot_command("portal switch 456")
    assert "Switched to portal 456" in result


def test_integration_refresh(mock_portal):
    result = hubspot_command("refresh", working_dir=mock_portal)
    assert "Cache refreshed" in result
    assert "123" in result
