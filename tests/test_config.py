import os
from pathlib import Path


def test_detect_portal_from_file(tmp_path):
    from hubspot_agent.config import detect_default_portal
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("1234567\n")
    result = detect_default_portal(str(tmp_path))
    assert result == "1234567"


def test_detect_portal_no_file(tmp_path):
    from hubspot_agent.config import detect_default_portal
    result = detect_default_portal(str(tmp_path))
    assert result is None


def test_load_portal_config_from_env(monkeypatch):
    from hubspot_agent.config import load_portal_config
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "token-123")
    monkeypatch.setenv("HUBSPOT_TIER_123", "Professional")
    config = load_portal_config("123")
    assert config is not None
    assert config.token == "token-123"
    assert config.tier == "Professional"


def test_save_and_load_portal_config(tmp_path, monkeypatch):
    from hubspot_agent.config import save_portal_config, load_portal_config, PortalConfig
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path / "hubspot")
    portal = PortalConfig(portal_id="456", token="secret-token")
    save_portal_config(portal)
    loaded = load_portal_config("456")
    assert loaded is not None
    assert loaded.token == "secret-token"
