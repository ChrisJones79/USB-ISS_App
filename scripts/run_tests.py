#!/usr/bin/env python3
"""Run pytest and write raw logs to docs/iterations/NN/logs/ (CLAUDE.md, Workflow)."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata as md
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def unique_paths(logdir: Path, tag: str, kind: str, stamp: str) -> tuple[Path, Path]:
    """Return (.txt, .xml) paths that do not exist; adds -2, -3... on collision."""
    n = 1
    while True:
        suffix = "" if n == 1 else f"-{n}"
        base = f"{tag}-{kind}-{stamp}{suffix}"
        txt, xml = logdir / f"{base}.txt", logdir / f"{base}.xml"
        if not txt.exists() and not xml.exists():
            return txt, xml
        n += 1


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


LOG_PATH = re.compile(r"^docs/iterations/[^/]+/logs/")


def dirty_lines() -> list[str]:
    """`git status --porcelain` lines, minus files under docs/iterations/*/logs/."""
    # not git(): its strip() would eat the leading space of the first status line
    r = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                       cwd=ROOT, capture_output=True, text=True)
    return filter_porcelain(r.stdout.splitlines())


def filter_porcelain(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not LOG_PATH.match(ln[3:].split(" -> ")[-1].strip('"'))]


def pkg_version(name: str) -> str:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return "not installed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", required=True, help="iteration number NN")
    ap.add_argument("--hw", action="store_true")
    ap.add_argument("--tag", choices=["build", "review"], default="build")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = ap.parse_args()

    port = None
    if args.hw:
        from usb_iss_app.transport import find_port

        port = find_port(args.env_file)
        if not port:
            print("error: --hw requires USB_ISS_PORT (environment or .env); none set.", file=sys.stderr)
            return 2

    logdir = ROOT / "docs" / "iterations" / args.iter / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    start = dt.datetime.now(dt.timezone.utc)
    txt, xml = unique_paths(logdir, args.tag, "hw" if args.hw else "mock", start.strftime("%Y%m%d-%H%M%S"))

    cmd = [sys.executable, "-m", "pytest", "-v", "-rA", f"--junitxml={xml}"]
    if args.hw:
        cmd.append("--hw")
    env = dict(os.environ)
    if port:
        env["USB_ISS_PORT"] = port

    dirty = dirty_lines()
    header = [
        f"command: {' '.join(sys.argv)}",
        f"pytest command: {' '.join(cmd)}",
        f"git commit: {git('rev-parse', 'HEAD')}{' (dirty)' if dirty else ' (clean)'}",
        f"python: {platform.python_version()}",
        f"pytest: {pkg_version('pytest')}",
        f"pyserial: {pkg_version('pyserial')}",
        f"usb-iss-app: {pkg_version('usb-iss-app')}",
    ]
    if dirty:
        header.append("git status --porcelain:")
        header += [f"  {ln}" for ln in dirty]
    if args.hw:
        header.append(f"port: {port}")
    header.append(f"start (UTC): {start.isoformat()}")

    with open(txt, "x") as f:
        f.write("\n".join(header) + "\n" + "=" * 70 + "\n")
        f.flush()
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert p.stdout
        for line in p.stdout:
            f.write(line)
            sys.stdout.write(line)
        rc = p.wait()
        f.write("=" * 70 + f"\nexit code: {rc}\n")
    print(f"log: {txt}\njunit: {xml}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
