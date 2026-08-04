"""The targeting-options export produces clean, non-empty canonical lists."""

from __future__ import annotations

import importlib.util

from promo_ops.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "build_targeting_options", REPO_ROOT / "scripts" / "build_targeting_options.py")
opts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(opts)


def test_genres_are_canonical_and_deduped():
    g = opts.genres()
    assert len(g) > 50
    assert g == sorted(set(g))                    # sorted + unique
    assert "Drama" in g and "Comedy" in g


def test_every_region_maps_to_markets_with_data():
    pluto = opts._pluto()
    for region, markets in opts.REGION_TO_PLUTO_MARKETS.items():
        cats = {c for m in markets for c in pluto.get(m, {}).get("categories", [])}
        assert cats, f"{region} -> {markets} has no categories"


def test_build_writes_all_files(tmp_path, monkeypatch):
    monkeypatch.setattr(opts, "OUT", tmp_path)
    counts = opts.build()
    assert counts["genres"] > 50 and counts["categories"] > 100
    assert (tmp_path / "genres.csv").exists()
    assert (tmp_path / "pluto-categories.csv").exists()
    assert (tmp_path / "pluto-channels.csv").exists()
    assert (tmp_path / "REGION-MAP.md").read_text().count("|") > 15   # table rows
