"""A sync that finishes WITHOUT raising but returns far less than before (FreeWheel degraded, partial
pages, an empty answer) must not replace a good snapshot. Oct 13 and Oct 28 both lost the audience
list this way: header-only files, then every plan came back with no segment ids.
Rules: a new file that is header-only never replaces a non-trivial one; a big file that shrinks to
under half its size is refused too. Normal growth/small drift is fine."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import DegradedSyncError, _atomic_csv_open


def _write(path, n, header="id,name\n"):
    with _atomic_csv_open(path) as fh:
        fh.write(header)
        for i in range(n):
            fh.write(f"{i},row{i}\n")


def test_a_header_only_result_never_replaces_a_real_snapshot(tmp_path):
    f = tmp_path / "items.csv"
    _write(f, 500)
    with pytest.raises(DegradedSyncError, match="items.csv"):
        _write(f, 0)
    assert len(f.read_text().splitlines()) == 501                 # untouched
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]    # no litter


def test_a_big_file_that_halves_is_refused(tmp_path):
    f = tmp_path / "series.csv"
    _write(f, 1000)
    with pytest.raises(DegradedSyncError):
        _write(f, 400)
    assert len(f.read_text().splitlines()) == 1001


def test_normal_growth_and_small_drift_are_fine(tmp_path):
    f = tmp_path / "x.csv"
    _write(f, 1000)
    _write(f, 1200)
    _write(f, 1100)
    assert len(f.read_text().splitlines()) == 1101


def test_first_ever_sync_and_tiny_files_are_never_blocked(tmp_path):
    f = tmp_path / "new.csv"
    _write(f, 0)                                                   # nothing there yet: allowed
    small = tmp_path / "small.csv"
    _write(small, 50)
    _write(small, 5)                                               # tiny lists can legitimately shrink
    assert len(small.read_text().splitlines()) == 6


def test_the_error_names_how_to_recover(tmp_path):
    f = tmp_path / "items.csv"
    _write(f, 500)
    with pytest.raises(DegradedSyncError) as e:
        _write(f, 10)
    assert "kept the previous" in str(e.value) and "500" in str(e.value)


def test_sync_all_runs_every_step_and_reports_the_ones_that_kept_old_data(monkeypatch, capsys):
    from promo_ops import cli
    from promo_ops.integrations import freewheel as fwmod
    ran = []

    class Fake:
        def sync_series(self):
            ran.append("series"); raise DegradedSyncError("synced_series.csv: kept the previous file")

        def sync_audience_items(self):
            ran.append("audience"); return "ok"

        def sync_standard_attributes(self):
            ran.append("attributes"); return ["ok"]
    monkeypatch.setattr(fwmod, "FreeWheelClient", Fake)
    rc = cli.main(["sync-all"])
    out = capsys.readouterr()
    assert ran == ["series", "audience", "attributes"]             # a bad step doesn't skip the rest
    assert rc == 1 and "KEPT the previous data" in out.err and "series" in out.err
