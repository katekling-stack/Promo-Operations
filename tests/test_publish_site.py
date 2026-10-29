"""Publishing to the team's Skydance Pages site (SFTP; the server refuses rsync).

The selection rules are the safety net: secrets, hidden files and logs never leave the machine,
nothing is ever deleted on the site, and only files whose content changed are uploaded. All of
that is decided by pure functions, so it's tested here with no network."""

from __future__ import annotations

import importlib.util

import pytest

from promo_ops.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location("publish_site", REPO_ROOT / "scripts" / "publish_site.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


def _tree(root, files):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def test_mapping_puts_site_pages_at_the_root_and_the_project_under_its_own_folder(tmp_path):
    _tree(tmp_path, {"site/index.html": "home", "site/qa.html": "qa", "docs/a.md": "a",
                     "templates/campaign-plan/campaign-plan-form.html": "form"})
    got = {r for r, _ in ps.collect(tmp_path)}
    assert {"/index.html", "/qa.html"} <= got
    assert {"/Promo-Operations/docs/a.md",
            "/Promo-Operations/templates/campaign-plan/campaign-plan-form.html"} <= got
    # site/ is published at the root only, never duplicated inside the project mirror
    assert not any(r.startswith("/Promo-Operations/site/") for r in got)


@pytest.mark.parametrize("rel", [
    ".env", ".env.local", ".git/config", ".pytest_cache/x", "logs/refresh.log",
    "src/__pycache__/m.cpython-314.pyc", "src/m.pyc", "keys/server.pem", "keys/id_ed25519",
    "keys/id_rsa", "ssh/known_hosts", "creds/private.key", ".DS_Store", "docs/.hidden.md",
    "build/out.txt", "dist/out.txt", ".venv/bin/python", "pkg.egg-info/PKG-INFO",
])
def test_secrets_hidden_files_logs_and_build_junk_never_publish(tmp_path, rel):
    _tree(tmp_path, {rel: "x", "docs/ok.md": "ok"})
    got = {r for r, _ in ps.collect(tmp_path)}
    assert "/Promo-Operations/docs/ok.md" in got
    assert f"/Promo-Operations/{rel}" not in got, rel


def test_awkward_file_names_are_skipped_not_passed_to_sftp(tmp_path):
    _tree(tmp_path, {'docs/we"ird.md': "x", "docs/fine name.md": "y"})
    got = {r for r, _ in ps.collect(tmp_path)}
    assert "/Promo-Operations/docs/fine name.md" in got           # spaces are fine (quoted)
    assert not any('"' in r for r in got)


def test_first_run_uploads_everything_and_later_runs_only_what_changed(tmp_path):
    root = _tree(tmp_path / "repo", {"site/index.html": "home", "docs/a.md": "a", "docs/b.md": "b"})
    files = ps.collect(root)
    manifest = {}
    todo = ps.plan_uploads(files, manifest)
    assert len(todo) == 3                                         # nothing known yet -> all

    manifest = ps.manifest_after(files, manifest)                 # pretend they all uploaded
    assert ps.plan_uploads(ps.collect(root), manifest) == []      # unchanged -> nothing to do

    (root / "docs/b.md").write_text("b changed", encoding="utf-8")
    (root / "docs/new.md").write_text("new", encoding="utf-8")
    todo = {r for r, _ in ps.plan_uploads(ps.collect(root), manifest)}
    assert todo == {"/Promo-Operations/docs/b.md", "/Promo-Operations/docs/new.md"}


def test_force_uploads_everything_again(tmp_path):
    root = _tree(tmp_path / "repo", {"docs/a.md": "a"})
    files = ps.collect(root)
    manifest = ps.manifest_after(files, {})
    assert ps.plan_uploads(files, manifest) == []
    assert len(ps.plan_uploads(files, manifest, force=True)) == 1


def test_a_failed_upload_stays_pending_for_the_next_run(tmp_path):
    root = _tree(tmp_path / "repo", {"docs/a.md": "a", "docs/b.md": "b"})
    files = ps.collect(root)
    ok = [f for f in files if f[0].endswith("a.md")]              # only a.md made it
    manifest = ps.manifest_after(ok, {})
    todo = {r for r, _ in ps.plan_uploads(files, manifest)}
    assert todo == {"/Promo-Operations/docs/b.md"}


def test_sftp_batch_creates_parent_folders_first_and_never_deletes():
    batch = ps.sftp_batch([("/Promo-Operations/docs/a.md", "/loc/docs/a.md"),
                           ("/index.html", "/loc/site/index.html")])
    lines = batch.splitlines()
    assert "-mkdir \"/Promo-Operations\"" in lines
    assert lines.index('-mkdir "/Promo-Operations"') < lines.index('-mkdir "/Promo-Operations/docs"')
    assert 'put -p "/loc/docs/a.md" "/Promo-Operations/docs/a.md"' in lines
    assert 'put -p "/loc/site/index.html" "/index.html"' in lines
    assert not any(l.lstrip("-").split()[0] in ("rm", "rmdir", "rename", "chmod", "chown") for l in lines)
    assert '-mkdir "/"' not in lines


def test_chunking_keeps_each_sftp_session_small():
    items = [(f"/Promo-Operations/f{i}.md", f"/loc/f{i}.md") for i in range(95)]
    chunks = list(ps.chunked(items, 40))
    assert [len(c) for c in chunks] == [40, 40, 15]


def test_the_private_key_contents_are_never_read_by_the_script():
    # only the key's PATH is handed to sftp (and named in an error message); its contents are
    # never opened, read or printed by this script
    import re
    src = (REPO_ROOT / "scripts" / "publish_site.py").read_text(encoding="utf-8")
    assert not re.search(r"KEY\.(read|open|write)|open\(\s*KEY|read_(bytes|text)\(\s*KEY", src)


# --- the hosted app's own source site ---------------------------------------------------------- #

def test_app_bundle_has_exactly_what_the_app_runs_and_nothing_else(tmp_path):
    _tree(tmp_path, {
        "webapp/app.py": "x", "webapp/requirements.txt": "PyYAML",
        "jobs/refresh.py": "j", "scripts/build_targeting_options.py": "b", "scripts/build_plan_form.py": "f", "scripts/sync_brands.py": "sb",
        "src/promo_ops/webapp.py": "w", "src/promo_ops/__init__.py": "",
        "config/brands.yaml": "b", "data/series/a.csv": "s",
        "templates/campaign-plan/campaign-plan-form.html": "form",
        "templates/targeting-options/shows.csv": "x", "templates/targeting-options/targeting-catalog.html": "big",
        "templates/batch/notes.md": "n",
        "tests/test_x.py": "t", "docs/a.md": "d", "site/index.html": "h", "scripts/x.py": "s",
        "plans/p.yaml": "p", "examples/e.json": "e", "logs/refresh.log": "l", ".env": "SECRET=1",
        "refresh.sh": "r", "update.sh": "u", "README.md": "r", "pyproject.toml": "p",
    })
    got = {r for r, _ in ps.collect_app(tmp_path)}
    assert got == {"/app.py", "/requirements.txt", "/jobs/refresh.py", "/scripts/build_targeting_options.py",
                   "/scripts/build_plan_form.py", "/scripts/sync_brands.py", "/src/promo_ops/webapp.py", "/src/promo_ops/__init__.py",
                   "/config/brands.yaml", "/data/series/a.csv",
                   "/templates/campaign-plan/campaign-plan-form.html",
                   "/templates/targeting-options/shows.csv"}


@pytest.mark.parametrize("rel", ["config/.env", "data/.secret", "config/id_ed25519", "data/x.pem",
                                 "src/promo_ops/__pycache__/a.pyc", "data/known_hosts"])
def test_app_bundle_never_carries_secrets_or_junk(tmp_path, rel):
    _tree(tmp_path, {"webapp/app.py": "x", rel: "nope"})
    assert not any(rel.split("/")[-1] in r for r, _ in ps.collect_app(tmp_path))


def test_app_target_uses_its_own_account_key_and_manifest():
    t = ps.target("app")
    assert t.manifest != ps.target("site").manifest and t.key != ps.target("site").key
    assert t.user != ps.target("site").user


# --- retrying a dropped connection -------------------------------------------------------------------- #

class _Res:
    def __init__(self, rc, err=""):
        self.returncode, self.stderr, self.stdout = rc, err, ""


def test_a_dropped_connection_is_retried_and_then_succeeds(monkeypatch):
    results = [_Res(255, "Connection closed"), _Res(255, "Connection closed"), _Res(0)]
    calls = []
    monkeypatch.setattr(ps, "_sftp", lambda batch, tgt: calls.append(batch) or results.pop(0))
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    res = ps._sftp_retrying("batch", ps.target("site"))
    assert res.returncode == 0 and len(calls) == 3


def test_it_gives_up_after_three_tries(monkeypatch):
    calls = []
    monkeypatch.setattr(ps, "_sftp", lambda b, t: calls.append(1) or _Res(255, "Connection closed"))
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    assert ps._sftp_retrying("b", ps.target("site")).returncode == 255 and len(calls) == 3


@pytest.mark.parametrize("err", ["ssh: Could not resolve hostname x", "Permission denied (publickey)"])
def test_vpn_and_key_problems_are_not_retried(monkeypatch, err):
    calls = []
    monkeypatch.setattr(ps, "_sftp", lambda b, t: calls.append(1) or _Res(255, err))
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    assert ps._sftp_retrying("b", ps.target("site")).returncode == 255 and len(calls) == 1


def test_uploads_are_split_by_size_so_a_big_batch_does_not_ride_one_session(tmp_path):
    files = []
    for i in range(6):
        f = tmp_path / f"f{i}.bin"
        f.write_bytes(b"x" * 4_000_000)
        files.append((f"/d/f{i}.bin", f))
    chunks = list(ps.chunked_by_size(files, max_files=40, max_bytes=10_000_000))
    assert [len(c) for c in chunks] == [2, 2, 2]
    one_big = tmp_path / "big.bin"
    one_big.write_bytes(b"x" * 30_000_000)
    assert [len(c) for c in ps.chunked_by_size([("/big.bin", one_big)], 40, 10_000_000)] == [1]
