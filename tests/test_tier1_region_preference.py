"""Tier 1 audience segments prefer the campaign's REGION-SPECIFIC segment for each show and
fall back to the standard (GL-DDA-1P) one only when there isn't one. Preference applies to
INCLUDE targeting only -- self-exclusion must still see every variant of the title."""

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


def test_falls_back_to_standard_when_no_region_specific(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Delta", "AU", prefer_region=True)) == {"8"}
    # AU has no Gamma segment of its own -> standard, not the US/EU buckets.
    assert _ids(r.resolve_exact("Gamma", "AU", prefer_region=True)) == {"5"}


def test_last_resort_is_another_regions_bucket(tmp_path):
    r = _resolver(tmp_path)
    # Beta only exists in the US bucket; an AU campaign can still reuse it rather than
    # reporting the show as unresolved.
    assert _ids(r.resolve_exact("Beta", "AU", prefer_region=True)) == {"4"}


def test_default_is_unchanged_so_self_exclusion_sees_every_variant(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Alpha", "AU")) == {"1", "2", "3"}
    assert _ids(r.resolve_all_exact(["Gamma"], "USA")[0]) == {"5", "6", "7"}


def test_unknown_show_is_still_unresolved(tmp_path):
    r = _resolver(tmp_path)
    assert not r.resolve_exact("Nope", "AU", prefer_region=True).matched


def test_tier1_targeting_uses_region_preference(tmp_path):
    engine = TargetingEngine(resolver=_resolver(tmp_path))
    plan = support_plan_from_dict({
        "promoted_title": "Zeta", "region": "AU", "campaign": {"name": "Paramount + - AU"},
        "durations": [30], "showlist": ["Alpha", "Delta", "Beta"], "genres": ["Drama"]})
    dim = engine._build_dimension(
        plan, {"key": "audience_segments", "label": "Audience Segments",
               "source": "audience_segments"})
    got = {s["segment_id"] for s in dim.resolved}
    assert got == {"2", "3", "8", "4"}      # Alpha->AU, Delta->standard, Beta->last resort
