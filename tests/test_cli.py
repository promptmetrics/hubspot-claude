from hubspot_agent.cli import hubspot_command


def test_hubspot_command_empty():
    result = hubspot_command("")
    assert "Usage" in result


def test_hubspot_command_no_portal(tmp_path):
    result = hubspot_command("find contacts", working_dir=str(tmp_path))
    assert "No default portal found" in result


def test_hubspot_command_routing(tmp_path, monkeypatch):
    from pathlib import Path
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")

    import os
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")

    result = hubspot_command("find contacts", working_dir=str(tmp_path))
    assert "Portal: 123" in result
    assert "objects" in result


def test_hubspot_command_ambiguous(tmp_path, monkeypatch):
    from pathlib import Path
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")

    result = hubspot_command("hello world", working_dir=str(tmp_path))
    assert "not sure" in result.lower()


def test_hubspot_portal_switch():
    result = hubspot_command("portal switch 456")
    assert "Switched to portal 456" in result


def test_hubspot_refresh_no_portal(tmp_path):
    result = hubspot_command("refresh", working_dir=str(tmp_path))
    assert "No default portal found" in result


def test_hubspot_portal_auth_no_credentials(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = hubspot_command("portal auth 123", working_dir=str(tmp_path))
    assert "credentials needed" in result


def test_hubspot_portal_token(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = hubspot_command("portal token 456", working_dir=str(tmp_path))
    assert "Private App Token" in result
    assert "pat-na1" in result


def test_hubspot_portal_list_empty(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)
    result = hubspot_command("portal list", working_dir=str(tmp_path))
    assert "No portals configured yet." in result


def test_hubspot_portal_list_with_portals(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.config import save_portal_config, PortalConfig
    save_portal_config(PortalConfig(portal_id="123", token="t1", auth_type="oauth", expires_at=1700000000.0))
    save_portal_config(PortalConfig(portal_id="456", token="t2", auth_type="private_app"))

    result = hubspot_command("portal list", working_dir=str(tmp_path))
    assert "123" in result
    assert "456" in result
    assert "oauth" in result
    assert "private_app" in result


def test_hubspot_portal_switch_persists(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.config import save_portal_config, PortalConfig
    save_portal_config(PortalConfig(portal_id="789", token="t3"))

    result = hubspot_command("portal switch 789", working_dir=str(tmp_path))
    assert "Switched to portal 789" in result

    portal_file = tmp_path / ".hubspot-portal"
    assert portal_file.exists()
    assert portal_file.read_text().strip() == "789"
