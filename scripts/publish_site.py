#!/usr/bin/env python3
"""Publish the project to the team's Skydance Pages site over SFTP.

    python3 scripts/publish_site.py            # upload what changed
    python3 scripts/publish_site.py --dry-run  # show what WOULD upload (works offline, no VPN)
    python3 scripts/publish_site.py --force    # re-upload everything

What goes where:
  site/        ->  the site root (home page, QA checklist, setup guide)
  everything   ->  /Promo-Operations/   (the project, so the campaign form etc. have a stable URL)

    python3 scripts/publish_site.py --app      # the hosted team app's own source site (see docs/WEBAPP.md)

The app site is a SECOND Pages site (its own deploy key and account) holding only what the app runs:
app.py + requirements.txt at the top, then src/, config/, data/, the form and the targeting lists.

Safety rules (all enforced in `collect`, and tested without a network):
  * secrets, keys, hidden files, logs and build junk are NEVER published
  * nothing is ever deleted or renamed on the site -- files are only added or overwritten
  * only files whose CONTENT changed since the last successful publish are uploaded
    (a local manifest remembers what's up there; delete it or use --force to re-upload all)

The site's server refuses rsync, so this drives the `sftp` command with a site-scoped deploy
key. It needs the company VPN; run from the 7am refresh it fails softly if the VPN is off.
Settings can be overridden with SKY_PAGES_USER / _KEY / _HOST / _PORT / _KNOWN_HOSTS.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

REPO = Path(__file__).resolve().parent.parent

HOST = os.environ.get("SKY_PAGES_HOST", "sftp.skydancepages.cloud")
PORT = os.environ.get("SKY_PAGES_PORT", "2022")
# The username is an account identifier, not a secret. KEY is only ever a PATH handed to sftp --
# this script never opens, reads or prints the key itself.
USER = os.environ.get("SKY_PAGES_USER",
                      "site-key-promo-ad-operations-automation-qa-tools-7561fb39c62c")
KEY = Path(os.environ.get("SKY_PAGES_KEY", "~/.ssh/skydance_pages_promo_ops")).expanduser()
KNOWN_HOSTS = Path(os.environ.get("SKY_PAGES_KNOWN_HOSTS", "~/.ssh/known_hosts_skydance")).expanduser()
MANIFEST = Path(os.environ.get("SKY_PAGES_MANIFEST",
                               "~/.cache/promo-ops/site_manifest.json")).expanduser()

APP_USER = os.environ.get("SKY_PAGES_APP_USER",
                          "site-key-promo-ops-app-source-24bc1d981b30")
APP_KEY = Path(os.environ.get("SKY_PAGES_APP_KEY", "~/.ssh/skydance_pages_promo_ops_app")).expanduser()
APP_MANIFEST = Path(os.environ.get("SKY_PAGES_APP_MANIFEST",
                                   "~/.cache/promo-ops/app_manifest.json")).expanduser()

PROJECT_REMOTE = "/Promo-Operations"
CHUNK = 40                                   # files per sftp session

# Never published, wherever they are in the tree.
SKIP_DIRS = {"logs", "__pycache__", "build", "dist", "node_modules"}
SKIP_PATTERNS = ("*.pyc", "*.pyo", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
                 "id_ecdsa*", "known_hosts*", "*.egg-info", "service-account*.json", ".env*")


def _skipped(rel: Path) -> bool:
    for part in rel.parts:
        if part.startswith("."):                       # hidden: .env, .git, .venv, .DS_Store ...
            return True
    if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel.parts[:-1]):
        return True
    name = rel.name
    return any(fnmatch.fnmatch(name, pat) for pat in SKIP_PATTERNS)


def _walk(base: Path, exclude_top: set[str] = frozenset()) -> Iterator[tuple[Path, Path]]:
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if rel.parts[0] in exclude_top or _skipped(rel):
            continue
        yield rel, path


def collect(repo: Path = REPO) -> list[tuple[str, Path]]:
    """[(remote path, local path)] for everything that may be published."""
    out: list[tuple[str, Path]] = []
    site = repo / "site"
    if site.is_dir():
        for rel, path in _walk(site):
            out.append(("/" + rel.as_posix(), path))
    for rel, path in _walk(repo, exclude_top={"site"}):
        out.append((f"{PROJECT_REMOTE}/{rel.as_posix()}", path))
    # file names sftp's quoting can't carry safely are skipped rather than risked
    return [(r, p) for r, p in out if '"' not in r and "\n" not in r and "\\" not in r]


def collect_app(repo: Path = REPO) -> list[tuple[str, Path]]:
    """[(remote path, local path)] for the hosted app's source site: exactly what it runs."""
    out: list[tuple[str, Path]] = []
    for name in ("app.py", "requirements.txt"):
        f = repo / "webapp" / name
        if f.is_file():
            out.append((f"/{name}", f))
    for top in ("src", "config", "data"):
        base = repo / top
        if base.is_dir():
            for rel, path in _walk(base):
                out.append((f"/{top}/{rel.as_posix()}", path))
    form = repo / "templates" / "campaign-plan" / "campaign-plan-form.html"
    if form.is_file():
        out.append(("/templates/campaign-plan/campaign-plan-form.html", form))
    lists = repo / "templates" / "targeting-options"
    if lists.is_dir():
        for path in sorted(lists.glob("*.csv")):
            out.append((f"/templates/targeting-options/{path.name}", path))
    return [(r, p) for r, p in out
            if not _skipped(Path(*r.strip("/").split("/"))) and '"' not in r and "\n" not in r and "\\" not in r]


class Target(NamedTuple):
    name: str
    user: str
    key: Path
    manifest: Path


def target(name: str) -> Target:
    if name == "app":
        return Target("app", APP_USER, APP_KEY, APP_MANIFEST)
    return Target("site", USER, KEY, MANIFEST)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def plan_uploads(files: list[tuple[str, Path]], manifest: dict, force: bool = False
                 ) -> list[tuple[str, Path]]:
    """The files whose content differs from what the manifest says is already on the site."""
    todo = []
    for remote, local in files:
        if force or manifest.get(remote) != _digest(local):
            todo.append((remote, local))
    return todo


def manifest_after(uploaded: Iterable[tuple[str, Path]], manifest: dict) -> dict:
    """The manifest once `uploaded` files have made it to the site."""
    new = dict(manifest)
    for remote, local in uploaded:
        new[remote] = _digest(local)
    return new


def chunked(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def sftp_batch(items: list[tuple[str, str]]) -> str:
    """An sftp batch file: create each parent folder (a leading '-' ignores 'already exists'),
    parents first, then put each file keeping its timestamp. No delete/rename/chmod, ever."""
    dirs: list[str] = []
    for remote, _ in items:
        parts = [p for p in remote.split("/")[1:-1] if p]
        for i in range(1, len(parts) + 1):
            d = "/" + "/".join(parts[:i])
            if d not in dirs:
                dirs.append(d)
    lines = [f'-mkdir "{d}"' for d in sorted(dirs, key=lambda d: (d.count("/"), d))]
    lines += [f'put -p "{local}" "{remote}"' for remote, local in items]
    return "\n".join(lines) + "\n"


def _sftp(batch: str, tgt: Target) -> subprocess.CompletedProcess:
    cmd = ["sftp", "-q", "-P", PORT, "-i", str(tgt.key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
           "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "ConnectTimeout=20", "-b", "-",
           f"{tgt.user}@{HOST}"]
    return subprocess.run(cmd, input=batch, capture_output=True, text=True, timeout=900)


def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_manifest(manifest: dict, path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="show what would upload; touch nothing")
    ap.add_argument("--force", action="store_true", help="re-upload every file")
    ap.add_argument("--app", action="store_true", help="publish the hosted app's source site instead")
    args = ap.parse_args(argv)

    tgt = target("app" if args.app else "site")
    files = collect_app() if args.app else collect()
    manifest = load_manifest(tgt.manifest)
    todo = plan_uploads(files, manifest, force=args.force)
    size = sum(p.stat().st_size for _, p in todo)
    print(f"site publish: {len(files)} publishable files, {len(todo)} changed "
          f"({size / 1e6:.1f} MB) -> Skydance Pages ({tgt.name} site)")
    if args.dry_run:
        for remote, _ in todo[:25]:
            print("  would upload", remote)
        if len(todo) > 25:
            print(f"  ... and {len(todo) - 25} more")
        print("(dry run -- nothing uploaded)")
        return 0
    if not todo:
        print("nothing changed -- site is up to date")
        return 0
    if "PENDING" in tgt.user:
        print("!! the app site's deploy-key account isn't set: export SKY_PAGES_APP_USER=<site-key-... name> "
              "(docs/WEBAPP.md)", file=sys.stderr)
        return 2
    if not tgt.key.exists():
        print(f"!! deploy key not found at {tgt.key} -- nothing published", file=sys.stderr)
        return 2

    failed = 0
    for chunk in chunked(todo, CHUNK):
        batch = sftp_batch([(remote, str(local)) for remote, local in chunk])
        try:
            res = _sftp(batch, tgt)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"!! sftp could not run: {exc}", file=sys.stderr)
            failed += len(chunk)
            break
        if res.returncode == 0:
            manifest = manifest_after(chunk, manifest)
            save_manifest(manifest, tgt.manifest)         # progress survives a later failure
        else:
            failed += len(chunk)
            tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or ["(no message)"]
            print(f"!! {len(chunk)} files not uploaded: {tail[0]}", file=sys.stderr)
            if "Could not resolve" in (res.stderr or "") or "timed out" in (res.stderr or ""):
                print("   (is the VPN on?)", file=sys.stderr)
                break
    done = len(todo) - failed
    print(f"published {done} of {len(todo)} files" + (f"; {failed} still pending" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
