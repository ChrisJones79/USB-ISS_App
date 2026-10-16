import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_tests  # noqa: E402


def test_unique_path_never_overwrites(tmp_path):
    a = run_tests.unique_paths(tmp_path, "build", "mock", "20260101-000000")
    for p in a:
        p.write_text("x")
    b = run_tests.unique_paths(tmp_path, "build", "mock", "20260101-000000")
    assert set(a).isdisjoint(b)
    assert all(not p.exists() for p in b)
    assert [p.suffix for p in b] == [".txt", ".xml"]


def test_hw_without_port_refuses(tmp_path):
    env = {"PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_tests.py"), "--iter", "99", "--hw",
         "--env-file", str(tmp_path / "none")],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert r.returncode != 0
    assert "USB_ISS_PORT" in r.stderr
    assert not (ROOT / "docs" / "iterations" / "99").exists()
