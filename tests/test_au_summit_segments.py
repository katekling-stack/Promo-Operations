"""AU Summit title segments are named "AU - DWH - {PP|10} - ID - Summit - Content - {Title}
watchers APAC". Title matching must understand that shape (it never ends with the bare title).

Tier 1 INCLUDE targeting: (10 Streaming) lines prefer the "AU - DWH - 10 - ..." segment for a
title, then fall back to the normal region-first order; every other AU line uses APAC-DDA-1P /
AU PP Summit first and never the Network 10 ("10") segments. EXCLUSION (self-exclusion) keeps
covering every variant of the title."""

from __future__ import annotations

import csv

from promo_ops.audience_segments import AudienceSegmentResolver
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.targeting import TargetingEngine

ROWS = [
    ["show", "segment_name", "segment_id", "platform", "region", "source"],
    ["", "AU - DWH - PP - ID - Summit - Content - Alpha watchers APAC", "11", "DDA", "", "t"],
    ["", "AU - DWH - 10 - ID - Summit - Content - Alpha watchers APAC", "12", "DDA", "", "t"],
    ["", "APAC-DDA-1P-SERIES-Alpha", "13", "DDA", "", "t"],
    ["", "GL-DDA-1P-SHOW_Alpha", "14", "DDA", "", "t"],
    # a DIFFERENT show whose name merely contains "Alpha"
    ["", "AU - DWH - PP - ID - Summit - Content - Alpha Beta watchers APAC", "15", "DDA", "", "t"],
    # Network 10-only title
    ["", "AU - DWH - 10 - ID - Summit - Content - Gogglebox watchers APAC", "21", "DDA", "", "t"],
    # P+-only title with a standard segment too
    ["", "AU - DWH - PP - ID - Summit - Content - Landman watchers APAC", "31", "DDA", "", "t"],
    ["", "GL-DDA-1P-SHOW_Landman", "32", "DDA", "", "t"],
    # deactivated segments are never targeted
    ["", "AU - DWH - 10 - ID - Summit - Content - Bachelor watchers APAC deactivated at X", "41", "DDA", "", "t"],
]


def _resolver(tmp_path):
    with (tmp_path / "segs.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(ROWS)
    return AudienceSegmentResolver(data_dir=tmp_path).load()


def _ids(match):
    return {r.segment_id for r in match.records}


def test_title_matching_understands_the_watchers_suffix(tmp_path):
    r = _resolver(tmp_path)
    got = _ids(r.resolve_exact("Alpha", "AU"))
    assert {"11", "12"} <= got               # both Summit sources found by title
    assert "15" not in got                   # "Alpha Beta" is a different show
    assert _ids(r.resolve_exact("Gogglebox", "AU")) == {"21"}
    assert not r.resolve_exact("Bachelor", "AU").matched          # deactivated


def test_exclusion_default_still_covers_every_variant(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Alpha", "AU")) == {"11", "12", "13", "14"}


def test_main_au_lines_prefer_apac_and_pp_and_never_use_the_10_segments(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Alpha", "AU", prefer_region=True)) == {"11", "13"}
    # a Network 10-only title has nothing usable on a main P+ line
    assert not r.resolve_exact("Gogglebox", "AU", prefer_region=True).matched


def test_10_streaming_lines_prefer_the_10_segment(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Alpha", "AU", prefer_region=True, streaming10=True)) == {"12"}
    assert _ids(r.resolve_exact("Gogglebox", "AU", prefer_region=True, streaming10=True)) == {"21"}


def test_10_streaming_falls_back_to_the_normal_order_when_no_10_segment(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Landman", "AU", prefer_region=True, streaming10=True)) == {"31"}


def test_summit_never_leaks_to_other_regions(tmp_path):
    r = _resolver(tmp_path)
    assert _ids(r.resolve_exact("Alpha", "USA", prefer_region=True)) == {"14"}   # standard only
    assert not r.resolve_exact("Gogglebox", "USA", prefer_region=True).matched


def _tier1_ids(engine, fmt):
    plan = support_plan_from_dict({
        "promoted_title": "Zeta", "region": "AU", "campaign": {"name": "Paramount + - AU"},
        "durations": [30], "showlist": ["Alpha"], "genres": ["Drama"]})
    tl = engine.build(plan, fmt)
    t1 = next(t for t in tl.tiers if t.id == 1)
    dim = next(d for d in t1.dimensions if d.key == "audience_segments")
    return {s["segment_id"] for s in dim.resolved}


def test_engine_gives_10_streaming_lines_their_own_segments(tmp_path):
    engine = TargetingEngine(resolver=_resolver(tmp_path))
    assert _tier1_ids(engine, "network_10_remnant") == {"12"}
    assert _tier1_ids(engine, "remnant_video") == {"11", "13"}
