"""T15: hooks/install.sh venv-provisioning contract (FR-15).

Exercises the SessionStart hook's hash-gate and ``venv.path`` contract without
hitting the network: a fake ``python3``/``uv`` on PATH stands up a venv-shaped
directory so the rebuild branch runs deterministically in CI.
"""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "hooks" / "install.sh"
PYPROJECT = ROOT / "pyproject.toml"


def _pyproject_sha() -> str:
    return hashlib.sha256(PYPROJECT.read_bytes()).hexdigest()


def _make_fake_bin(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Fake python3: `python3 -m venv <dir>` stands up a venv-shaped dir.
    py = bin_dir / "python3"
    py.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
        '  venvdir="$3"; mkdir -p "$venvdir/bin"\n'
        '  cp "$0" "$venvdir/bin/python"; chmod +x "$venvdir/bin/python"\n'
        '  : > "$venvdir/bin/pip"; chmod +x "$venvdir/bin/pip"\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    py.chmod(py.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Fake uv that always fails so the hook falls through to python3 -m venv.
    uv = bin_dir / "uv"
    uv.write_text("#!/bin/sh\nexit 1\n")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(data: Path, fake_bin: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_DATA": str(data),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "HOME": str(data),
    }
    env.pop("UV", None)
    return subprocess.run(["/bin/sh", str(INSTALL)], env=env, capture_output=True, text=True)


def _seed_venv(data: Path) -> Path:
    venv = data / "venv"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python"
    py.write_bytes(b"")
    py.chmod(0o755)
    (data / "venv.path").write_text(str(venv) + "\n")
    (data / ".pyproject.sha").write_text(_pyproject_sha() + "\n")
    return venv


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


@pytest.fixture(autouse=True)
def _need_hasher():
    if not any(_which(p) for p in ("sha256sum", "shasum")):
        pytest.skip("no sha256sum/shasum on PATH")
    yield


def test_install_hook_fast_path_no_rebuild(tmp_path):
    data = tmp_path
    venv = _seed_venv(data)
    fake_bin = tmp_path / "fakebin"
    _make_fake_bin(fake_bin)

    r = _run(data, fake_bin)
    assert r.returncode == 0, r.stderr
    # No rebuild: venv.path and hash unchanged.
    assert (data / "venv.path").read_text().strip() == str(venv)
    assert (data / ".pyproject.sha").read_text().strip() == _pyproject_sha()


def test_install_hook_rebuild_writes_venv_path(tmp_path):
    data = tmp_path
    fake_bin = tmp_path / "fakebin"
    _make_fake_bin(fake_bin)

    r = _run(data, fake_bin)
    assert r.returncode == 0, r.stderr
    assert (data / "venv.path").read_text().strip() == str(data / "venv")
    assert (data / "venv" / "bin" / "python").exists()
    assert (data / ".pyproject.sha").read_text().strip() == _pyproject_sha()


def test_install_hook_hash_drift_triggers_rebuild(tmp_path):
    data = tmp_path
    _seed_venv(data)
    (data / ".pyproject.sha").write_text("stalehash\n")  # drift → rebuild
    fake_bin = tmp_path / "fakebin"
    _make_fake_bin(fake_bin)

    r = _run(data, fake_bin)
    assert r.returncode == 0, r.stderr
    assert (data / ".pyproject.sha").read_text().strip() == _pyproject_sha()


def test_install_hook_missing_python_fails_gracefully(tmp_path):
    data = tmp_path
    # Core utils stay on PATH; fake python3 + uv that both fail sit first, so
    # the hook can't build a venv and must fail gracefully (exit 0, no block).
    fail_bin = tmp_path / "failbin"
    fail_bin.mkdir()
    for name in ("python3", "python", "uv"):
        f = fail_bin / name
        f.write_text("#!/bin/sh\nexit 1\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    env = {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_DATA": str(data),
        "PATH": f"{fail_bin}:{os.environ.get('PATH', '')}",
        "HOME": str(data),
    }
    env.pop("UV", None)
    r = subprocess.run(["/bin/sh", str(INSTALL)], env=env, capture_output=True, text=True)
    assert r.returncode == 0
    assert "could not provision" in r.stderr
    assert not (data / "venv.path").exists()
    assert not (data / ".pyproject.sha").exists()