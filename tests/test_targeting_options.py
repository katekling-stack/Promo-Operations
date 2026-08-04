"""The targeting-options export produces clean, canonical lists from FreeWheel data."""

from __future__ import annotations

import importlib.util

from promo_ops.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "build_targeting_options", REPO_ROOT / "scripts" / "build_targeting_options.py")
opts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(opts)


def test_genres_include_franchise_and_daypart_and_drop_removed():
    g = opts.genres()
    values = {v for v, _ in g}
    types = {t for _, t in g}
    assert "Drama" in values and "Comedy" in values
    assert {"Genre", "Franchise", "Daypart"} <= types      # all three kinds present
    assert "Daypart: Daytime" in values and "Daypart: Sports" in values   # dayparts, prefixed
    # daypart values are prefixed so they never collide with same-named genres
    assert all(v.startswith("Daypart: ") for v, t in g if t == "Daypart")
    # removed values are gone
    for gone in ("Pluto TV: KIDS  CONTENT (COPPA)", "SERIES", "SPECIAL"):
        assert gone not in values, gone


def test_pluto_regions_exclude_no_pluto_markets():
    # AU and IE don't run Pluto -> excluded from the by-region lists.
    regions = opts._pluto_regions()
    assert "AU" not in regions and "IE" not in regions
    assert {"USA", "UK", "FR", "GSA", "LATAM"} <= regions


def test_audience_segments_match_known_structures():
    aud = opts.audience_segments()
    assert len(aud) > 500
    structs = {s for _, s in aud}
    assert structs <= {"GL-DDA-1P", "AU-DWH-Summit", "AAM-VCBS-Extension", "comScore"}
    assert any(s == "GL-DDA-1P" for _, s in aud)
    # every kept segment actually matches its structure (no free-text leakage)
    for name, _ in aud:
        assert opts._classify_segment(name) is not None, name


def test_build_writes_all_files(tmp_path, monkeypatch):
    monkeypatch.setattr(opts, "OUT", tmp_path)
    counts = opts.build()
    assert counts["genres"] > 50 and counts["franchise"] > 10 and counts["daypart"] >= 8
    assert counts["categories"] > 100
    for f in ("genres.csv", "pluto-categories-by-region.csv",
              "pluto-channels-by-region.csv", "audience-segments.csv", "REGION-MAP.md"):
        assert (tmp_path / f).exists()
    # by-region file must not contain the no-Pluto regions
    body = (tmp_path / "pluto-categories-by-region.csv").read_text()
    assert "\nAU," not in body and "\nIE," not in body
