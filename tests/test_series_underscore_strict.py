"""Underscored Video Series ("dutton_ranch") belong to the 10 Streaming catalog. When a CM picks
a title for INCLUDE targeting, each pick resolves to exactly the series spelled that way:
"Dutton Ranch" must not drag in "dutton_ranch", and a distinctly selected "dutton_ranch" must
not drag in "Dutton Ranch". Self-exclusion keeps folding both spellings together so the
promoted title is blocked everywhere."""

from __future__ import annotations

import csv

from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.series import SeriesResolver
from promo_ops.targeting import TargetingEngine

ROWS = [
    ["id", "name", "status"],
    ["1", "Dutton Ranch", "ACTIVE"],
    ["2", "dutton_ranch", "ACTIVE"],
    ["3", "Rabbit Hole", "ACTIVE"],
    ["4", "rabbit_hole", "ACTIVE"],
    ["5", "Landman", "ACTIVE"],
]


def _resolver(tmp_path):
    with (tmp_path / "series.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(ROWS)
    return SeriesResolver(data_dir=tmp_path).load()


def _ids(match):
    return {s["id"] for s in match.series}


def test_spaced_title_does_not_pull_in_the_underscored_series(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Dutton Ranch", strict_underscores=True)) == {"1"}


def test_distinctly_selected_underscored_title_gets_only_that_series(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("dutton_ranch", strict_underscores=True)) == {"2"}


def test_default_still_folds_both_so_self_exclusion_catches_every_spelling(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Dutton Ranch")) == {"1", "2"}
    assert _ids(r.resolve_exact("dutton_ranch")) == {"1", "2"}


def test_titles_without_an_underscored_twin_are_unaffected(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Landman", strict_underscores=True)) == {"5"}
    assert not r.resolve_exact("Nope", strict_underscores=True).matched


def _dim(engine, showlist):
    plan = support_plan_from_dict({
        "promoted_title": "Zeta", "region": "AU", "campaign": {"name": "Paramount + - AU"},
        "durations": [30], "showlist": showlist, "genres": ["Drama"]})
    return engine._build_dimension(
        plan, {"key": "content_affinity_showlist", "label": "Affinity Shows",
               "source": "showlist"})


def test_tier2_targeting_uses_strict_matching(tmp_path):
    engine = TargetingEngine(series_resolver=_resolver(tmp_path))
    assert {r["id"] for r in _dim(engine, ["Dutton Ranch"]).resolved} == {"1"}
    # Picking both spellings on purpose targets both.
    assert {r["id"] for r in _dim(engine, ["Dutton Ranch", "dutton_ranch"]).resolved} == {"1", "2"}
    # Picking only the underscored one targets only that.
    assert {r["id"] for r in _dim(engine, ["rabbit_hole"]).resolved} == {"4"}
