"""Tier 1 audience segments are REGION-ONLY: a show is targeted only through a segment that
carries the campaign's own region (its request-tool bucket; for AU also the AU Summit ones).
The standard GL-DDA-1P segment and other regions' buckets are NOT used (team policy), and the
tool alerts instead. This applies to INCLUDE targeting only -- self-exclusion must still see
every variant of the title."""

from __future__ import annotations

import csv

from promo_ops.audience_segments import AudienceSegmentResolver
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.targeting import TargetingEngine

ROWS = [
    ["show", "segment_name", "segment_id", "platform", "region", "source"],
    # Alpha: standard + AU bucket + AU Summit all exist
    ["", "GL-DDA-1P-SHOW_Alpha", "1", "DDA", "", "t"],
    ["", "APAC-DDA-1P-SERIES-Alpha", "2", "DDA", "", "t"],
    ["", "AU - DWH - PP - ID - Summit - Content - Alpha", "3", "DDA", "", "t"],
    # Beta: ONLY another region's bucket exists
    ["", "US-DDA-1P-SERIES-Beta", "4", "DDA", "", "t"],
    # Gamma: standard + US bucket + EU/UK bucket
    ["", "GL-DDA-1P-SHOW_Gamma", "5", "DDA", "", "t"],
    ["", "US-DDA-1P-SERIES-Gamma", "6", "DDA", "", "t"],
    ["", "EU/UK-DDA-1P-SERIES-Gamma", "7", "DDA", "", "t"],
    # Delta: standard only
    ["", "GL-DDA-1P-SHOW_Delta", "8", "DDA", "", "t"],
]


def _resolver(tmp_path):
    p = tmp_path / "segs.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(ROWS)
    return AudienceSegmentResolver(data_dir=tmp_path).load()


def _ids(match):
    return {r.segment_id for r in match.records}


def test_region_specific_wins_over_standard(tmp_path):
    r = _resolver(tmp_path)
    # AU: its own bucket + Summit are used; the standard GL segment is NOT added on top.
    assert _ids(r.resolve_exact("Alpha", "AU", prefer_region=True)) == {"2", "3"}
    # USA / UK each take their own bucket.
    assert _ids(r.resolve_exact("Gamma", "USA", prefer_region=True)) == {"6"}
    assert _ids(r.resolve_exact("Gamma", "UK", prefer_region=True)) == {"7"}


def test_no_fallback_to_the_standard_segment(tmp_path):
    r = _resolver(tmp_path)
    # Delta only has a standard GL segment; Gamma has none in AU's own bucket. Neither is used.
    assert not r.resolve_exact("Delta", "AU", prefer_region=True).matched
    assert not r.resolve_exact("Gamma", "AU", prefer_region=True).matched


def test_another_regions_bucket_is_not_used(tmp_path):
    r = _resolver(tmp_path)
    # Beta only exists in the US bucket: US campaigns use it, nobody else does.
    assert _ids(r.resolve_exact("Beta", "USA", prefer_region=True)) == {"4"}
    for region in ("AU", "UK", "FR"):
        assert not r.resolve_exact("Beta", region, prefer_region=True).matched


def test_default_is_unchanged_so_self_exclusion_sees_every_variant(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Alpha", "AU")) == {"1", "2", "3"}
    assert _ids(r.resolve_all_exact(["Gamma"], "USA")[0]) == {"5", "6", "7"}


def test_unknown_show_is_still_unresolved(tmp_path):
    r = _resolver(tmp_path)
    assert not r.resolve_exact("Nope", "AU", prefer_region=True).matched


def _dim(engine, plan_extra):
    plan = support_plan_from_dict({
        "promoted_title": "Zeta", "region": "AU", "campaign": {"name": "Paramount + - AU"},
        "durations": [30], "genres": ["Drama"], **plan_extra})
    return engine._build_dimension(
        plan, {"key": "audience_segments", "label": "Audience Segments",
               "source": "audience_segments"})


def test_tier1_targeting_is_region_only_and_alerts_on_the_rest(tmp_path):
    dim = _dim(TargetingEngine(resolver=_resolver(tmp_path)),
               {"showlist": ["Alpha", "Delta", "Beta", "Nope"]})
    assert {s["segment_id"] for s in dim.resolved} == {"2", "3"}      # Alpha's AU segments only
    notes = dim.notes
    assert "NOT targeted" in notes and "Delta [GL-DDA-1P]" in notes and "Beta [US-DDA-1P]" in notes
    assert "need their Tier 1 DDA audience item" in notes and "Nope" in notes
    assert "NO audience" not in notes          # Alpha still gives Tier 1 an audience


def test_tier1_with_nothing_regional_warns_it_would_run_platform_wide(tmp_path):
    dim = _dim(TargetingEngine(resolver=_resolver(tmp_path)), {"showlist": ["Delta", "Beta"]})
    assert not dim.resolved
    assert "NO audience targeting" in dim.notes and "whole platform" in dim.notes


def test_hand_picked_non_regional_segments_are_kept_but_flagged(tmp_path):
    dim = _dim(TargetingEngine(resolver=_resolver(tmp_path)),
               {"showlist": ["Alpha"], "audience_segments": ["GL-DDA-1P-SHOW_Delta"]})
    assert {s["segment_id"] for s in dim.resolved} == {"2", "3", "8"}   # the CM's pick is kept
    assert "hand-picked segment(s) aren't AU segments" in dim.notes and "GL-DDA-1P-SHOW_Delta" in dim.notes
