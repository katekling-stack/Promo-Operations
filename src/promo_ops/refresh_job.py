"""The daily data refresh, as a Skydance Pages Job (see docs/WEBAPP.md).

Runs the same routine the Mac's 7am job does -- sync FreeWheel, rebuild the pickers and the form --
but in a SCRATCH COPY, checks the result, and uploads only the files that changed to the app's source
site, where the app picks them up and rebuilds. If anything looks wrong it uploads nothing, so the app
keeps yesterday's data.

    python jobs/refresh.py              # what the Job runs
    python jobs/refresh.py --dry-run    # do everything except upload
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import quote

# What gets published: the synced data lists, the derived pickers, and the rebuilt form.
DATA_DIR = "data"
EXTRA_GLOBS = ("templates/targeting-options/*.csv", "templates/campaign-plan/campaign-plan-form.html")

# A refresh below these is treated as degraded (FreeWheel answered with partial data) and not published.
MIN_AUDIENCE_ROWS = 1000
MIN_SERIES_ROWS = 100_000
MIN_SEGMENT_ROWS = 1000
MIN_FORM_BYTES = 1_000_000

AUDIENCE_FILE = "data/audience_segments/synced_audience_items.csv"
SERIES_FILE = "data/series/synced_series.csv"
SEGMENTS_FILE = "templates/targeting-options/audience-segments.csv"
FORM_FILE = "templates/campaign-plan/campaign-plan-form.html"

DEFAULT_BASE = "https://skydancepages.cloud"
DEFAULT_SITE = "promo-ops-app-source"
DEFAULT_TOKEN_FILE = "/var/run/secrets/pages/token"


def _skipped(rel: Path) -> bool:
    return any(p.startswith(".") or p == "__pycache__" for p in rel.parts)


def _tracked(root: Path) -> list[Path]:
    root = Path(root)
    out: list[Path] = []
    base = root / DATA_DIR
    if base.is_dir():
        out += [p for p in sorted(base.rglob("*")) if p.is_file()]
    for pat in EXTRA_GLOBS:
        out += [p for p in sorted(root.glob(pat)) if p.is_file()]
    return [p for p in out if not _skipped(p.relative_to(root))]


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """{relative path: content hash} for everything the refresh publishes."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): _digest(p) for p in _tracked(root)}


def changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Files that are new or whose CONTENT differs (touching a file doesn't count)."""
    return sorted(rel for rel, h in after.items() if before.get(rel) != h)


def _rows(path: Path) -> Optional[int]:
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except OSError:
        return None


def health_problems(root: Path) -> list[str]:
    """Reasons NOT to publish this refresh (empty list = healthy)."""
    root = Path(root)
    problems: list[str] = []
    for rel, minimum, label in ((AUDIENCE_FILE, MIN_AUDIENCE_ROWS, "audience list"),
                                (SERIES_FILE, MIN_SERIES_ROWS, "series list"),
                                (SEGMENTS_FILE, MIN_SEGMENT_ROWS, "segment picker list")):
        n = _rows(root / rel)
        if n is None:
            problems.append(f"The {label} is missing ({rel}).")
        elif n < minimum:
            problems.append(f"The {label} has only {n} rows (expected at least {minimum}); looks degraded.")
    form = root / FORM_FILE
    if not form.is_file() or form.stat().st_size < MIN_FORM_BYTES:
        problems.append(f"The rebuilt form is missing or far too small ({FORM_FILE}).")
    return problems


def default_put(url: str, headers: dict, path: Path) -> int:
    """PUT one file; returns the HTTP status (retries connection errors / 5xx a few times)."""
    import requests
    status = 0
    for attempt in range(3):
        try:
            with Path(path).open("rb") as fh:
                resp = requests.put(url, data=fh, headers=headers, timeout=900)
            status = resp.status_code
            if status < 500:
                return status
        except requests.RequestException:
            status = 0
        time.sleep(2 * (attempt + 1))
    return status


def upload(root: Path, files: Iterable[str], *, put: Callable = default_put, base: str = DEFAULT_BASE,
           site: str = DEFAULT_SITE, token_file: Path | str = DEFAULT_TOKEN_FILE) -> dict:
    """Upload each file to the source site; stop at the first refusal. Returns {uploaded, failed}."""
    try:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    except OSError:
        raise RuntimeError(f"No Pages token at {token_file}. In the portal, open the Job's Identity tab and "
                           "mount its identity under 'Acting on Pages' (docs/WEBAPP.md).")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
    files = list(files)
    done: list[str] = []
    for i, rel in enumerate(files):
        url = f"{base.rstrip('/')}/api/sites/{site}/files/{quote(rel, safe='/')}"
        status = put(url, headers, Path(root) / rel)
        if not (200 <= int(status) < 300):
            return {"uploaded": done, "failed": files[i:]}
        done.append(rel)
    return {"uploaded": done, "failed": []}


def default_runner(cmd, cwd, env) -> int:
    return subprocess.run(cmd, cwd=str(cwd), env=env).returncode


STEPS = (
    ("sync FreeWheel (series, audience items, attributes)", lambda: [sys.executable, "-m", "promo_ops.cli", "sync-all"], False),
    ("rebuild the picker lists", lambda: [sys.executable, "scripts/build_targeting_options.py"], True),
    ("rebuild the campaign form", lambda: [sys.executable, "scripts/build_plan_form.py"], True),
)


def run(*, source: Path, workdir: Path, runner: Callable = default_runner, put: Callable = default_put,
        dry_run: bool = False, base: str = DEFAULT_BASE, site: str = DEFAULT_SITE,
        token_file: Path | str = DEFAULT_TOKEN_FILE, log: Callable = print) -> int:
    """One refresh. Returns 0 on success (including "nothing changed"), 1 when nothing was published
    because something looked wrong or an upload was refused."""
    source, workdir = Path(source), Path(workdir)
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(source, workdir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git*"))
    before = snapshot(workdir)

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(workdir / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    for label, make_cmd, must_succeed in STEPS:
        log(f"-- {label}…")
        rc = runner(make_cmd(), workdir, env)
        if rc != 0 and must_succeed:
            log(f"!! '{label}' failed (exit {rc}); nothing was published.")
            return 1
        if rc != 0:
            log(f"!! '{label}' kept some previous data (exit {rc}); carrying on with what did refresh.")

    problems = health_problems(workdir)
    if problems:
        log("!! The refresh looks degraded, so NOTHING was published (the app keeps its current data):")
        for p in problems:
            log(f"   - {p}")
        return 1

    todo = changed(before, snapshot(workdir))
    log(f"{len(todo)} file(s) changed" + (": " + ", ".join(todo) if todo else "; the app's data is already current."))
    if not todo or dry_run:
        if dry_run and todo:
            log("(dry run: nothing uploaded)")
        return 0
    try:
        res = upload(workdir, todo, put=put, base=base, site=site, token_file=token_file)
    except RuntimeError as exc:
        log(f"!! {exc}")
        return 1
    if res["failed"]:
        log(f"!! Upload stopped: {len(res['uploaded'])} file(s) went up, these were refused: {', '.join(res['failed'])}")
        return 1
    log(f"Published {len(res['uploaded'])} file(s) to {site}. The app rebuilds on its own.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="do everything except upload")
    ap.add_argument("--source", default=str(Path(__file__).resolve().parents[2]), help="the project folder to refresh a copy of")
    ap.add_argument("--workdir", default="/tmp/promo-refresh", help="scratch folder (recreated each run)")
    args = ap.parse_args(argv)
    return run(source=Path(args.source), workdir=Path(args.workdir), dry_run=args.dry_run,
               base=os.environ.get("PAGES_API_BASE", DEFAULT_BASE), site=os.environ.get("PAGES_SITE", DEFAULT_SITE),
               token_file=os.environ.get("PAGES_TOKEN_FILE", DEFAULT_TOKEN_FILE))


if __name__ == "__main__":
    raise SystemExit(main())
