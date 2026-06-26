"""T1: main() argv shim, --working-dir/--portal flag stripping, portal_id kwarg."""
from __future__ import annotations

import sys

import pytest

from hubspot_agent import cli
from hubspot_agent.cli import _strip_global_flags, hubspot_command


def test_strip_flags_space_form():
    rem, wd, pid = _strip_global_flags(
        ["tool", "objects", "search", "--working-dir", "/x", "--portal", "123"]
    )
    assert rem == ["tool", "objects", "search"]
    assert wd == "/x"
    assert pid == "123"


def test_strip_flags_equals_form():
    rem, wd, pid = _strip_global_flags(["--working-dir=/x", "--portal=123", "status"])
    assert rem == ["status"]
    assert wd == "/x"
    assert pid == "123"


def test_strip_flags_preserves_portal_inside_input_json():
    # The JSON value is a single argv token; `--portal` inside it must NOT be stripped.
    rem, wd, pid = _strip_global_flags(
        ["tool", "objects", "create", "--input", '{"name":"--portal"}']
    )
    assert rem == ["tool", "objects", "create", "--input", '{"name":"--portal"}']
    assert wd is None
    assert pid is None


def test_strip_flags_preserves_working_dir_inside_input_json():
    rem, wd, pid = _strip_global_flags(
        ["tool", "objects", "create", "--input", '{"path":"--working-dir"}']
    )
    assert rem == ["tool", "objects", "create", "--input", '{"path":"--working-dir"}']
    assert wd is None
    assert pid is None


def test_main_passes_portal_and_working_dir(monkeypatch):
    captured: dict = {}

    def fake(request, working_dir, *, portal_id=None):
        captured.update(request=request, working_dir=working_dir, portal_id=portal_id)
        return "OK"

    monkeypatch.setattr(cli, "hubspot_command", fake)
    monkeypatch.setattr(
        sys, "argv", ["hubspot", "--portal", "123", "find", "contacts", "--working-dir", "/tmp"]
    )
    cli.main()
    assert captured == {"request": "find contacts", "working_dir": "/tmp", "portal_id": "123"}


def test_main_invalid_portal_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hubspot", "--portal", "abc", "find contacts"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "Invalid portal_id" in capsys.readouterr().err


def test_main_defaults_working_dir(monkeypatch):
    captured: dict = {}

    def fake(request, working_dir, *, portal_id=None):
        captured.update(request=request, working_dir=working_dir, portal_id=portal_id)
        return "OK"

    monkeypatch.setattr(cli, "hubspot_command", fake)
    monkeypatch.setattr(sys, "argv", ["hubspot", "status"])
    cli.main()
    assert captured == {"request": "status", "working_dir": ".", "portal_id": None}


def test_portal_id_kwarg_overrides_detect_default_portal(monkeypatch, tmp_path):
    calls = {"n": 0}

    def boom(working_dir):
        calls["n"] += 1
        return None

    monkeypatch.setattr(cli, "detect_default_portal", boom)
    monkeypatch.setattr(cli, "load_portal_config", lambda pid: None)
    result = hubspot_command("find contacts", working_dir=str(tmp_path), portal_id="1234567")
    assert calls["n"] == 0
    assert "1234567" in result


def test_portal_id_none_uses_detect_default_portal(monkeypatch, tmp_path):
    # FR-2: byte-for-byte identical when portal_id is absent.
    monkeypatch.setattr(cli, "detect_default_portal", lambda working_dir: "999")
    monkeypatch.setattr(cli, "load_portal_config", lambda pid: None)
    result = hubspot_command("find contacts", working_dir=str(tmp_path))
    assert "999" in result