#!/usr/bin/env python3
"""Ship your changes in one command:   ./ship.sh

    1. refuses if you have unsaved (uncommitted) code changes
    2. runs the whole test suite (a few minutes)
    3. pushes to GitHub: the team repo (main) and your backup branch
    4. publishes the app (the QA page, the form, the data)

It stops at the first problem and never publishes something that failed its tests or didn't get
pushed. Options:  --skip-tests (not recommended)   --dry-run (show the plan, change nothing)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent

# Folders/files whose uncommitted changes mean "unsaved work". Regenerated data (the daily sync, the
# rebuilt form and picker lists, logs) is expected to be modified and is deliberately not committed.
CODE_PREFIXES = ("src/", "tests/", "scripts/", "config/", "docs/", "jobs/", "webapp/", "site/",
                 "README", "pyproject.toml", "update.sh", "refresh.sh", "ship.sh", ".claude/")


def _run(cmd) -> tuple[int, str]:
    p = subprocess.run(list(map(str, cmd)), cwd=REPO, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _stream(cmd) -> int:
    return subprocess.run(list(map(str, cmd)), cwd=REPO).returncode


def unsaved_code(status: str) -> list[str]:
    out = []
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ")[-1]
        if path.startswith(CODE_PREFIXES):
            out.append(path)
    return out


def ship(*, run: Callable = _run, log: Callable = print, skip_tests: bool = False, dry_run: bool = False,
         stream: Callable | None = None) -> int:
    stream = stream or run
    rc, status = run(["git", "status", "--porcelain"])
    if rc != 0:
        log("!! couldn't read git status; is this the Promo-Operations folder?")
        return 1
    dirty = unsaved_code(status)
    if dirty:
        log("!! You have unsaved code changes, so nothing was shipped. Tell Claude to commit them, or commit them yourself:")
        for p in dirty[:15]:
            log(f"   - {p}")
        return 1

    rc, remotes = run(["git", "remote"])
    remotes = remotes.split()
    steps = []
    if not skip_tests:
        steps.append(("run the tests", [sys.executable, "-m", "pytest", "tests", "-q", "--ignore=tests/test_template_workbook.py"]))
    steps.append(("push to the team repo (main)", ["git", "push", "origin", "HEAD:main"]))
    if "personal" in remotes:
        steps.append(("push your backup branch", ["git", "push", "personal", "HEAD"]))
    steps.append(("publish the app", [sys.executable, "scripts/publish_site.py", "--app"]))

    if dry_run:
        log("Dry run: this is what would happen, in order:")
        for i, (label, cmd) in enumerate(steps, 1):
            log(f"  {i}. {label}   ({' '.join(map(str, cmd))})")
        return 0

    for i, (label, cmd) in enumerate(steps, 1):
        log(f"\n[{i}/{len(steps)}] {label}…")
        rc = stream(cmd) if stream is not run else run(cmd)[0]
        if rc != 0:
            log(f"\n!! Stopped: '{label}' did not succeed (exit {rc}). Nothing after it was done.")
            if "publish" in label:
                log("   (Publishing needs the VPN. Everything before it already succeeded; just re-run ./ship.sh.)")
            return 1
    log("\n✅ Shipped: tests passed, GitHub is up to date, and the app is publishing.")
    log("   The app rebuilds itself in about a minute; reload its page with Cmd+Shift+R.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return ship(skip_tests=args.skip_tests, dry_run=args.dry_run, stream=_stream)


if __name__ == "__main__":
    raise SystemExit(main())
