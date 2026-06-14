from pathlib import Path

import pytest

from hubspot_agent.ledger import ActionLedger


@pytest.fixture
def ledger(tmp_path):
    return ActionLedger("123", base_dir=tmp_path)


def test_ledger_start_action_creates_file(ledger, tmp_path):
    ledger.start_action("a1", "objects", "create_contact", {"email": "test@example.com"})
    assert (tmp_path / "action_log.jsonl").exists()


def test_ledger_get_in_flight_empty(ledger):
    assert ledger.get_in_flight() == []


def test_ledger_get_in_flight_one_started(ledger):
    ledger.start_action("a1", "objects", "create_contact", {"email": "test@example.com"})
    in_flight = ledger.get_in_flight()
    assert len(in_flight) == 1
    assert in_flight[0]["action_id"] == "a1"
    assert in_flight[0]["status"] == "started"


def test_ledger_get_in_flight_completed_not_included(ledger):
    ledger.start_action("a1", "objects", "create_contact", {"email": "test@example.com"})
    ledger.complete_action("a1", {"status": "success"})
    assert ledger.get_in_flight() == []


def test_ledger_get_in_flight_partial(ledger):
    ledger.start_action("a1", "objects", "create_contact", {"email": "a@example.com"})
    ledger.start_action("a2", "objects", "create_contact", {"email": "b@example.com"})
    ledger.complete_action("a1", {"status": "success"})
    in_flight = ledger.get_in_flight()
    assert len(in_flight) == 1
    assert in_flight[0]["action_id"] == "a2"


def test_ledger_find_similar_in_flight_match(ledger):
    payload = {"email": "test@example.com"}
    ledger.start_action("a1", "objects", "create_contact", payload)
    found = ledger.find_similar_in_flight("objects", "create_contact", payload)
    assert found is not None
    assert found["action_id"] == "a1"


def test_ledger_find_similar_in_flight_mismatch_agent(ledger):
    payload = {"email": "test@example.com"}
    ledger.start_action("a1", "objects", "create_contact", payload)
    found = ledger.find_similar_in_flight("properties", "create_contact", payload)
    assert found is None


def test_ledger_find_similar_in_flight_mismatch_action(ledger):
    payload = {"email": "test@example.com"}
    ledger.start_action("a1", "objects", "create_contact", payload)
    found = ledger.find_similar_in_flight("objects", "update_contact", payload)
    assert found is None


def test_ledger_find_similar_in_flight_mismatch_payload(ledger):
    ledger.start_action("a1", "objects", "create_contact", {"email": "a@example.com"})
    found = ledger.find_similar_in_flight("objects", "create_contact", {"email": "b@example.com"})
    assert found is None


def test_ledger_find_similar_excludes_completed(ledger):
    payload = {"email": "test@example.com"}
    ledger.start_action("a1", "objects", "create_contact", payload)
    ledger.complete_action("a1", {"status": "success"})
    found = ledger.find_similar_in_flight("objects", "create_contact", payload)
    assert found is None


def test_ledger_hash_payload_deterministic(ledger):
    h1 = ledger._hash_payload({"b": 2, "a": 1})
    h2 = ledger._hash_payload({"a": 1, "b": 2})
    assert h1 == h2


def test_ledger_get_recent(ledger):
    ledger.start_action("a1", "objects", "c1", {})
    ledger.complete_action("a1", {"status": "success"})
    ledger.start_action("a2", "objects", "c2", {})
    recent = ledger.get_recent(limit=2)
    assert len(recent) == 2
    assert recent[0]["action_id"] == "a1"
    assert recent[1]["action_id"] == "a2"


def test_ledger_corrupt_line_ignored(ledger, tmp_path):
    log_file = tmp_path / "action_log.jsonl"
    log_file.write_text("not json\n")
    assert ledger.get_in_flight() == []
    assert ledger.get_recent() == []


def test_ledger_entry_missing_action_id_ignored(ledger):
    ledger._append({"status": "started", "agent": "objects"})
    assert ledger.get_in_flight() == []


def test_ledger_payload_not_stored(ledger, tmp_path):
    ledger.start_action("a1", "objects", "create_contact", {"email": "secret@example.com"})
    log_file = tmp_path / "action_log.jsonl"
    raw = log_file.read_text()
    assert "secret@example.com" not in raw
    assert "payload_hash" in raw


def test_ledger_mixed_valid_and_corrupt_lines(ledger, tmp_path):
    log_file = tmp_path / "action_log.jsonl"
    log_file.write_text(
        '{"action_id":"a1","status":"started","agent":"objects"}\n'
        'bad json line\n'
        '{"action_id":"a2","status":"started","agent":"objects"}\n'
    )
    in_flight = ledger.get_in_flight()
    assert len(in_flight) == 2
    assert {e["action_id"] for e in in_flight} == {"a1", "a2"}


def test_ledger_stale_entry_ignored(ledger):
    from datetime import datetime, timezone, timedelta

    # Append a started entry that is just inside the stale window
    fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=ActionLedger.STALE_SECONDS - 1)).isoformat()
    ledger._append({
        "timestamp": fresh_ts,
        "action_id": "fresh1",
        "status": "started",
        "agent": "objects",
        "action": "create_contact",
        "payload_hash": ledger._hash_payload({"email": "test@example.com"}),
    })

    ledger.start_action("new1", "objects", "create_contact", {"email": "test@example.com"})

    # The fresh entry should match first (both are valid)
    found = ledger.find_similar_in_flight("objects", "create_contact", {"email": "test@example.com"})
    assert found is not None
    assert found["action_id"] == "fresh1"


def test_ledger_stale_entry_blocked_when_too_old(ledger):
    from datetime import datetime, timezone, timedelta

    stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=ActionLedger.STALE_SECONDS + 1)).isoformat()
    ledger._append({
        "timestamp": stale_ts,
        "action_id": "stale1",
        "status": "started",
        "agent": "objects",
        "action": "create_contact",
        "payload_hash": ledger._hash_payload({"email": "test@example.com"}),
    })

    found = ledger.find_similar_in_flight("objects", "create_contact", {"email": "test@example.com"})
    assert found is None
