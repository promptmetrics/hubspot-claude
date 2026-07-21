from hubspot_agent.cli import _handle_setup, hubspot_command


def test_hubspot_command_empty():
    result = hubspot_command("")
    assert "Usage" in result


def test_hubspot_command_no_portal(tmp_path):
    result = hubspot_command("find contacts", working_dir=str(tmp_path))
    assert "No default portal found" in result


def test_hubspot_command_routing(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")

    import os
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")

    result = hubspot_command("find contacts", working_dir=str(tmp_path))
    assert "Portal: 123" in result
    assert "objects" in result
    assert "Cannot dispatch" not in result


def test_hubspot_command_ambiguous(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

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
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

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


# ---------------------------------------------------------------------------
# Setup command tests
# ---------------------------------------------------------------------------


def test_hubspot_setup_token(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", lambda pc: None)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", lambda pc: None)
    monkeypatch.setattr("hubspot_agent.maintenance.run_maintenance", lambda pid: None)

    result = hubspot_command("setup 123 token pat-na1-test", working_dir=str(tmp_path))
    assert "Setup complete" in result

    portal_file = tmp_path / ".hubspot-portal"
    assert portal_file.exists()
    assert portal_file.read_text().strip() == "123"


def test_hubspot_setup_oauth_success(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

    monkeypatch.setattr("hubspot_agent.setup.probe_portal", lambda pc: None)
    monkeypatch.setattr("hubspot_agent.setup.warm_standard_schemas", lambda pc: None)
    monkeypatch.setattr("hubspot_agent.maintenance.run_maintenance", lambda pid: None)

    from hubspot_agent.config import save_portal_config, PortalConfig
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))

    def mock_auth(portal_id):
        return {"success": True, "message": "OAuth complete"}

    monkeypatch.setattr("hubspot_agent.cli._authenticate_portal_oauth", mock_auth)

    result = hubspot_command("setup 123 oauth", working_dir=str(tmp_path))
    assert "OAuth complete" in result
    assert "Setup complete" in result

    portal_file = tmp_path / ".hubspot-portal"
    assert portal_file.exists()
    assert portal_file.read_text().strip() == "123"


def test_hubspot_setup_oauth_failure(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def mock_auth(portal_id):
        return {"success": False, "message": "Auth failed: no creds"}

    monkeypatch.setattr("hubspot_agent.cli._authenticate_portal_oauth", mock_auth)

    result = hubspot_command("setup 123 oauth", working_dir=str(tmp_path))
    assert "Auth failed: no creds" in result
    assert "Setup complete" not in result

    portal_file = tmp_path / ".hubspot-portal"
    assert portal_file.exists()
    assert portal_file.read_text().strip() == "123"


def test_hubspot_setup_invalid_portal_id(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = hubspot_command("setup abc token pat-na1-test", working_dir=str(tmp_path))
    assert "Invalid portal ID" in result


def test_hubspot_setup_missing_token_arg(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = hubspot_command("setup 123 token", working_dir=str(tmp_path))
    assert "Usage" in result


def test_hubspot_setup_run_setup_raises(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

    def mock_run_setup(portal_id, method=None, token=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("hubspot_agent.setup.run_setup", mock_run_setup)

    result = hubspot_command("setup 456", working_dir=str(tmp_path))
    assert "Setup failed" in result
    assert "boom" in result


def test_hubspot_status_no_portal(tmp_path):
    result = hubspot_command("status", working_dir=str(tmp_path))
    assert "No default portal found" in result


def test_hubspot_status_with_traces(tmp_path, monkeypatch):
    from pathlib import Path
    from hubspot_agent.config import PortalConfig, save_portal_config
    from hubspot_agent.trace import emit_trace, new_trace_id

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)

    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    save_portal_config(PortalConfig(portal_id="123", token="t"))

    tid = new_trace_id()
    emit_trace("123", "request_received", tid, {"request": "find contacts"})
    emit_trace("123", "tool_call", tid, {"tool_name": "hubspot_search_v1"})
    emit_trace("123", "completion", tid, {"estimated_usd": 0.002})

    result = hubspot_command("status", working_dir=str(tmp_path))
    assert "Portal: 123" in result
    assert "Requests: 1" in result
    assert "Est. cost: $0.002" in result
    assert "hubspot_search_v1: 1" in result
