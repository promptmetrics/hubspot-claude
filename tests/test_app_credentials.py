from hubspot_agent.app_credentials import load_app_credentials, save_app_credentials


def test_save_and_load_app_credentials(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    save_app_credentials(client_id="cid-123", client_secret="csec-456", app_id="aid-789")
    creds = load_app_credentials()
    assert creds is not None
    assert creds["client_id"] == "cid-123"
    assert creds["client_secret"] == "csec-456"
    assert creds["app_id"] == "aid-789"


def test_load_app_credentials_missing(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert load_app_credentials() is None
