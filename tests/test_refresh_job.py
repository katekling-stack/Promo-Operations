"""The daily refresh as a Pages Job: sync FreeWheel in a scratch copy, rebuild the pickers and the
form, CHECK the result, and upload only the files that changed to the app's source site. If anything
looks wrong it uploads nothing, so the app keeps yesterday's data. All offline: the sync commands and
the HTTP upload are injected."""

from __future__ import annotations

from pathlib import Path

import pytest

from promo_ops import refresh_job as rj


def _rows(path: Path, n: int, header="a,b\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join(f"{i},x\n" for i in range(n)), encoding="utf-8")


def _tree(root: Path, audience=1500, series=120_000, segments=1500, form_bytes=2_000_000, brands=5000):
    _rows(root / "data/audience_segments/synced_audience_items.csv", audience)
    _rows(root / "data/series/synced_series.csv", series)
    _rows(root / "templates/targeting-options/audience-segments.csv", segments)
    _rows(root / "data/brands/synced_brands.csv", brands)
    form = root / "templates/campaign-plan/campaign-plan-form.html"
    form.parent.mkdir(parents=True, exist_ok=True)
    form.write_bytes(b"x" * form_bytes)
    (root / "src/promo_ops").mkdir(parents=True, exist_ok=True)
    (root / "src/promo_ops/code.py").write_text("print(1)", encoding="utf-8")
    return root


# --- what counts as "data to publish" -------------------------------------------------------------- #

def test_only_data_lists_and_the_form_are_tracked(tmp_path):
    _tree(tmp_path)
    (tmp_path / "data/.secret").write_text("x")
    (tmp_path / "data/__pycache__").mkdir()
    (tmp_path / "data/__pycache__/a.pyc").write_text("x")
    (tmp_path / ".env").write_text("SECRET=1")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/x.log").write_text("x")
    got = set(rj.snapshot(tmp_path))
    assert got == {"data/audience_segments/synced_audience_items.csv", "data/series/synced_series.csv",
                   "data/brands/synced_brands.csv",
                   "templates/targeting-options/audience-segments.csv",
                   "templates/campaign-plan/campaign-plan-form.html"}


def test_changes_are_found_by_content_not_by_time(tmp_path):
    _tree(tmp_path)
    before = rj.snapshot(tmp_path)
    (tmp_path / "data/series/synced_series.csv").touch()
    assert rj.changed(before, rj.snapshot(tmp_path)) == []
    _rows(tmp_path / "data/series/synced_series.csv", 130_000)
    assert rj.changed(before, rj.snapshot(tmp_path)) == ["data/series/synced_series.csv"]
    new = tmp_path / "data/geo/new.csv"
    _rows(new, 3)
    assert "data/geo/new.csv" in rj.changed(before, rj.snapshot(tmp_path))


# --- the health check ------------------------------------------------------------------------------- #

def test_a_healthy_refresh_has_no_problems(tmp_path):
    assert rj.health_problems(_tree(tmp_path)) == []


@pytest.mark.parametrize("kw,word", [({"audience": 0}, "audience"), ({"series": 5000}, "series"),
                                     ({"segments": 20}, "segment"), ({"form_bytes": 1000}, "form"),
                                     ({"brands": 50}, "brand")])
def test_a_degraded_refresh_is_caught(tmp_path, kw, word):
    problems = rj.health_problems(_tree(tmp_path, **kw))
    assert problems and word in " ".join(problems).lower()


def test_a_missing_file_is_a_problem(tmp_path):
    _tree(tmp_path)
    (tmp_path / "data/series/synced_series.csv").unlink()
    assert any("series" in p.lower() for p in rj.health_problems(tmp_path))


# --- the upload -------------------------------------------------------------------------------------- #

class FakePut:
    def __init__(self, fail_on=None, status=200):
        self.calls, self.fail_on, self.status = [], fail_on, status

    def __call__(self, url, headers, path):
        self.calls.append((url, dict(headers), Path(path).name, Path(path).stat().st_size))
        if self.fail_on and self.fail_on in url:
            return 401
        return self.status


def test_upload_uses_the_site_files_api_with_the_platform_token(tmp_path):
    _tree(tmp_path)
    token = tmp_path / "token"
    token.write_text("abc.def\n")
    put = FakePut()
    res = rj.upload(tmp_path, ["templates/targeting-options/audience-segments.csv"], put=put,
                    base="https://skydancepages.cloud", site="promo-ops-app-source", token_file=token)
    url, headers, name, size = put.calls[0]
    assert url == "https://skydancepages.cloud/api/sites/promo-ops-app-source/files/templates/targeting-options/audience-segments.csv"
    assert headers["Authorization"] == "Bearer abc.def" and name == "audience-segments.csv" and size > 0
    assert res == {"uploaded": ["templates/targeting-options/audience-segments.csv"], "failed": []}


def test_a_refused_upload_stops_the_run_and_is_reported(tmp_path):
    _tree(tmp_path)
    token = tmp_path / "token"
    token.write_text("t")
    put = FakePut(fail_on="synced_series")
    files = ["data/audience_segments/synced_audience_items.csv", "data/series/synced_series.csv",
             "templates/campaign-plan/campaign-plan-form.html"]
    res = rj.upload(tmp_path, files, put=put, base="https://x", site="s", token_file=token)
    assert res["uploaded"] == files[:1] and res["failed"] == files[1:]      # stops at the first refusal
    assert len(put.calls) == 2


def test_a_missing_token_is_a_clear_error(tmp_path):
    _tree(tmp_path)
    with pytest.raises(RuntimeError, match="token"):
        rj.upload(tmp_path, ["data/series/synced_series.csv"], put=FakePut(), base="https://x", site="s",
                  token_file=tmp_path / "nope")


# --- the whole run ----------------------------------------------------------------------------------- #

def _runner(mutate=None, rc_by_step=None):
    calls = []

    def run(cmd, cwd, env):
        calls.append((list(cmd), Path(cwd), dict(env)))
        step = " ".join(cmd)
        if mutate and "sync-all" in step:
            mutate(Path(cwd))
        return (rc_by_step or {}).get(next((k for k in (rc_by_step or {}) if k in step), ""), 0)
    run.calls = calls
    return run


def _job(tmp_path, runner, put=None, dry_run=False, source_kw=None):
    source = _tree(tmp_path / "source", **(source_kw or {}))
    token = tmp_path / "token"
    token.write_text("t")
    code = rj.run(source=source, workdir=tmp_path / "work", runner=runner, put=put or FakePut(),
                  dry_run=dry_run, base="https://p", site="app-src", token_file=token, log=lambda *_: None)
    return code, source


def test_a_normal_run_uploads_only_what_changed(tmp_path):
    put = FakePut()
    code, _ = _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/series/synced_series.csv", 125_000)), put)
    assert code == 0
    assert [c[2] for c in put.calls] == ["synced_series.csv"]


def test_nothing_changed_means_nothing_uploaded(tmp_path):
    put = FakePut()
    code, _ = _job(tmp_path, _runner(), put)
    assert code == 0 and put.calls == []


def test_the_steps_run_in_the_scratch_copy_in_order(tmp_path):
    r = _runner()
    _job(tmp_path, r)
    cmds = [" ".join(c[0]) for c in r.calls]
    assert "sync-all" in cmds[0] and "sync_brands.py" in cmds[1]
    assert "build_targeting_options.py" in cmds[2] and "build_plan_form.py" in cmds[3]
    assert all(c[1] == tmp_path / "work" for c in r.calls)
    assert all(str(tmp_path / "work" / "src") in c[2]["PYTHONPATH"] for c in r.calls)


def test_the_source_folder_is_never_modified(tmp_path):
    source = _tree(tmp_path / "source")
    before = rj.snapshot(source)
    _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/series/synced_series.csv", 125_000)))
    assert rj.snapshot(source) == before


def test_a_sync_that_kept_old_data_still_goes_on_and_uploads_what_did_refresh(tmp_path):
    put = FakePut()
    code, _ = _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/series/synced_series.csv", 125_000),
                                     rc_by_step={"sync-all": 1}), put)
    assert code == 0 and [c[2] for c in put.calls] == ["synced_series.csv"]


def test_a_degraded_result_uploads_nothing_and_fails_the_run(tmp_path):
    put = FakePut()
    code, _ = _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/audience_segments/synced_audience_items.csv", 0)), put)
    assert code == 1 and put.calls == []


def test_a_failed_build_step_uploads_nothing(tmp_path):
    put = FakePut()
    code, _ = _job(tmp_path, _runner(rc_by_step={"build_plan_form": 2}), put)
    assert code == 1 and put.calls == []


def test_a_dry_run_uploads_nothing(tmp_path):
    put = FakePut()
    code, _ = _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/series/synced_series.csv", 125_000)), put, dry_run=True)
    assert code == 0 and put.calls == []


def test_a_refused_upload_fails_the_run(tmp_path):
    put = FakePut(fail_on="synced_series")
    code, _ = _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/series/synced_series.csv", 125_000)), put)
    assert code == 1


def test_the_brand_sync_failing_does_not_stop_the_refresh(tmp_path):
    # e.g. the MRM credentials aren't set on the Job: Brands keep their previous list, the rest goes on
    put = FakePut()
    code, _ = _job(tmp_path, _runner(mutate=lambda w: _rows(w / "data/series/synced_series.csv", 125_000),
                                     rc_by_step={"sync_brands": 1}), put)
    assert code == 0 and [c[2] for c in put.calls] == ["synced_series.csv"]
