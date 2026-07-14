from hubspot_agent.app_credentials import (
    get_api_base_url,
    get_oauth_endpoints,
    get_region,
    load_app_credentials,
    save_app_credentials,
)


def test_save_app_credentials_sets_0o600(tmp_path, monkeypatch):
    # M2: client_secret must be 0600 from birth, never briefly world-readable.
    import os
    import stat
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    save_app_credentials(client_id="cid-123", client_secret="csec-456")
    p = tmp_path / ".claude" / "hubspot" / "app_credentials.json"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_save_and_load_app_credentials(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    save_app_credentials(client_id="cid-123", client_secret="csec-456", app_id="aid-789")
    creds = load_app_credentials()
    assert creds is not None
    assert creds["client_id"] == "cid-123"
    assert creds["client_secret"] == "csec-456"
    assert creds["app_id"] == "aid-789"
    assert creds["region"] == "us"  # default region


def test_load_app_credentials_missing(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert load_app_credentials() is None


def test_get_region_default_when_missing(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert get_region() == "us"
    assert get_oauth_endpoints() == (
        "https://app.hubspot.com/oauth/authorize",
        "https://api.hubapi.com/oauth/v1/token",
    )
    assert get_api_base_url() == "https://api.hubapi.com"


def test_save_app_credentials_eu_region(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    save_app_credentials(client_id="cid-eu", client_secret="csec-eu", region="eu")
    assert get_region() == "eu"
    assert get_oauth_endpoints() == (
        "https://app-eu1.hubspot.com/oauth/authorize",
        "https://api-eu1.hubapi.com/oauth/v1/token",
    )
    assert get_api_base_url() == "https://api-eu1.hubapi.com"


def test_save_app_credentials_rejects_unknown_region(tmp_path, monkeypatch):
    from pathlib import Path
    import pytest
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(ValueError):
        save_app_credentials(client_id="cid", client_secret="sec", region="asia")
