"""Tests for the targeting engine, audience resolver, and order builder."""

from __future__ import annotations

from promo_ops.audience_segments import AudienceSegmentResolver, normalize_title
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import load_plan, support_plan_from_dict
from promo_ops.targeting import TargetingEngine

FRISCO = "plans/frisco-king-usa.yaml"


# --- audience resolver ------------------------------------------------------ #

def test_normalize_title_strips_punctuation():
    assert normalize_title("NCIS: Origins") == "ncis origins"
    assert normalize_title("Dog The Bounty Hunter") == "dog the bounty hunter"


def test_resolver_matches_seed_show():
    # DDA-only: Tulsa King resolves to its GL-DDA-1P- audience item.
    resolver = AudienceSegmentResolver().load()
    match = resolver.resolve("Tulsa King", region="USA")
    assert match.matched
    assert match.records[0].segment_id == "1437993"
    assert match.records[0].segment_name.upper().startswith("GL-DDA-1P")


def test_resolver_reports_unmatched():
    resolver = AudienceSegmentResolver().load()
    match = resolver.resolve("Some Nonexistent Show", region="USA")
    assert not match.matched
    assert match.records == []


# --- targeting engine ------------------------------------------------------- #

def test_tier1_global_for_all_regions():
    # Update 2026-08-05: Tier 1 is included GLOBALLY for adult orders — every region
    # (incl. UK, previously ineligible) now builds tiers 1-4.
    engine = TargetingEngine()
    plan = support_plan_from_dict({
        "promoted_title": "X", "region": "UK", "brand": "paramount_network",
        "formats": ["remnant_video"], "showlist": ["Top Gear"],
    })
    targeting = engine.build(plan, "remnant_video")
    tier_ids = [t.id for t in targeting.tiers]
    assert 1 in tier_ids and 3 in tier_ids


def test_tier1_present_for_usa():
    engine = TargetingEngine()
    plan = load_plan(FRISCO)
    targeting = engine.build(plan, "remnant_video")
    assert 1 in [t.id for t in targeting.tiers]


def test_audience_segments_dimension_always_present_in_tier1():
    engine = TargetingEngine()
    plan = load_plan(FRISCO)
    targeting = engine.build(plan, "remnant_video")
    tier1 = next(t for t in targeting.tiers if t.id == 1)
    keys = [d.key for d in tier1.dimensions]
    assert "audience_segments" in keys


def test_pause_ads_include_all_four_tiers():
    # Pause Ads run Tiers 1-4 (mirrors Dutton Ranch).
    engine = TargetingEngine()
    plan = load_plan(FRISCO)
    targeting = engine.build(plan, "pause_ads")
    assert [t.id for t in targeting.tiers] == [1, 2, 3, 4]


# --- order builder ---------------------------------------------------------- #

def test_order_builder_per_tier_and_duration_naming():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    assert order.name == "Frisco King - USA"           # IO name
    assert order.campaign["name"] == "Paramount + - USA"  # existing parent campaign
    names = [p.name for p in order.placements]
    # remnant video: 4 tiers x 2 durations = 8; pause ads: 4 tiers; guaranteed: 2 -> 14
    assert len(order.placements) == 14
    # Paramount+ stamps the [ShowID:] tag on every placement (blank id here -> CM fills).
    assert "Frisco King - Season 1 - 30 (Tier 1) - USA - [ShowID:]" in names
    assert "Frisco King - Season 1 - Pause Ad (Tier 4) - USA - [ShowID:]" in names
    assert "Frisco King - Season 1 - 15 (Tier 4) - USA - [ShowID:]" in names


def test_guaranteed_placement_named_by_content_id():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    prem = next(p for p in order.placements if p.format == "premium_preroll")
    assert prem.name == "Paramount + - Pre-Roll - Premium Plan - Frisco King - USA - [ShowID:]"

    plan.content_type = "movie"; plan.content_id = "12345"
    order2 = OrderBuilder().build(plan)
    ess2 = next(p for p in order2.placements if p.format == "essential_bumper")
    assert ess2.name == "Paramount + - Bumper - Essential Plan - Frisco King - USA - [MovieID:12345]"


def test_priority_by_tier_and_duration():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)

    def pr(fmt, tier, dur):
        return next(p.priority_level for p in order.placements
                    if p.format == fmt and p.tier == tier and p.duration == dur)

    assert pr("remnant_video", 1, 30) == 1    # tier1 :30 -> base 1 + 0
    assert pr("remnant_video", 1, 15) == 2    # tier1 :15 -> base 1 + 1
    assert pr("remnant_video", 2, 15) == 5    # tier2 :15 -> base 4 + 1
    assert pr("remnant_video", 3, 30) == 7    # tier3 :30 -> base 7 + 0
    t4 = next(p for p in order.placements if p.format == "remnant_video" and p.tier == 4)
    assert t4.priority_level == 10
    assert t4.frequency_cap == "1 per hr"

    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    assert t1.frequency_cap == "1 per 30 min"

    prem = next(p for p in order.placements if p.format == "premium_preroll")
    assert prem.priority_level == "SPONSORSHIP"
    assert prem.frequency_cap == "1 per week"      # Premium Plan pre-rolls: 1/week (global)


def test_order_carries_template_ref():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    assert order.template_ref["campaign_id"] == "86543608"
    assert order.template_ref["advertiser_id"] == "1000520"
    assert order.template_ref["template_io_id"] == "92725144"
    assert order.network_id == "520311"


def test_promoted_show_excluded_from_every_placement():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    for p in order.placements:
        assert "Frisco King" in p.exclusions


def test_tier1_audience_is_dda_only_no_aam():
    # AAM segments are sunset: Tier 1 must resolve ONLY DDA (GL-DDA-1P-) items.
    plan = load_plan(FRISCO)
    targeting = TargetingEngine().build(plan, "remnant_video")
    tier1 = next(t for t in targeting.tiers if t.id == 1)
    seg_dim = next(d for d in tier1.dimensions if d.key == "audience_segments")
    names = [s["segment_name"] for s in seg_dim.resolved]
    assert names, "expected DDA segments resolved from the showlist"
    assert all(n.upper().startswith("GL-DDA-1P") for n in names)
    # the sunset AAM grouping IDs must never appear
    ids = [s.get("segment_id") for s in seg_dim.resolved]
    assert "25995747" not in ids and "25995761" not in ids


def test_genres_resolve_to_standard_attribute_ids():
    plan = load_plan(FRISCO)
    targeting = TargetingEngine().build(plan, "remnant_video")
    tier3 = next(t for t in targeting.tiers if t.id == 3)
    genre = next(d for d in tier3.dimensions if d.key == "genre")
    ids = {r["name"]: r["id"] for r in genre.resolved}
    assert ids.get("Drama") == "28"
    assert ids.get("Western") == "49"
    assert ids.get("Action & Adventure") == "35"
    # all 8 Frisco King genres resolve
    assert len(genre.resolved) == len(plan.genres)


def test_franchise_video_group_resolves_as_genre():
    # A Franchise VG ("VG: Franchise: Star Trek"), offered in the Genre picker under its BARE
    # name, must resolve to its VG id. Regression: franchises silently dropped because the
    # resolver only handled Genre / Sub / Daypart / Brand prefixes.
    from promo_ops.video_groups import GenreVideoGroupResolver
    assert GenreVideoGroupResolver().load().ids_for(["Star Trek"]) == ["414452175"]


def test_showlist_resolves_to_video_series_ids():
    # Select-all against the Video Series (asset-group) namespace: a show resolves to
    # every matching series (large IDs), mirroring the team's UI workflow.
    plan = load_plan(FRISCO)
    t2 = next(t for t in TargetingEngine().build(plan, "remnant_video").tiers if t.id == 2)
    showdim = next(d for d in t2.dimensions if d.key == "content_affinity_showlist")
    by_show: dict[str, list] = {}
    for r in showdim.resolved:
        by_show.setdefault(r["show"], []).append(r["id"])
    assert by_show.get("Landman")                     # resolves to >=1 series
    assert "1147080004" in by_show["Landman"]         # the FW Video Series id (matches Dutton)
    assert all(i.isdigit() and len(i) > 6 for i in by_show["Landman"])   # asset-group namespace
    # NCIS: New York not premiered yet -> no series -> flagged
    assert "NCIS: New York" in (showdim.notes or "")


def test_tier1_dda_audience_item_resolves():
    plan = load_plan(FRISCO)
    t1 = next(t for t in TargetingEngine().build(plan, "remnant_video").tiers if t.id == 1)
    seg = next(d for d in t1.dimensions if d.key == "audience_segments")
    names = {s["segment_name"]: s.get("segment_id") for s in seg.resolved}
    assert names.get("GL-DDA-1P-SHOW_Tulsa_King") == "1437993"


def test_pluto_channel_and_category_resolve_to_site_groups():
    plan = load_plan(FRISCO)
    eng = TargetingEngine()
    # Tier 2: Pluto channel keywords -> US Channels site groups (keyword select-all),
    # each resolved record carries a real FW site_group id.
    t2 = next(t for t in eng.build(plan, "remnant_video").tiers if t.id == 2)
    ch = next(d for d in t2.dimensions if d.key == "pluto_channel_list")
    gunsmoke = [r for r in ch.resolved if r.get("keyword") == "Gunsmoke" and r.get("id")]
    assert gunsmoke
    assert all(r["segment_name"].startswith("SG: PlutoTV Channels: US:") for r in gunsmoke)
    # Tier 3: domestic promo categories -> ": US" suffixed site groups with ids.
    t3 = next(t for t in eng.build(plan, "remnant_video").tiers if t.id == 3)
    cat = next(d for d in t3.dimensions if d.key == "pluto_category")
    tc = [r for r in cat.resolved if r.get("keyword") == "True Crime" and r.get("id")]
    assert tc and tc[0]["segment_name"] == "SG: PlutoTV Promo Category: True Crime: US"

    # International uses "PlutoTV Category" (no "Promo") with the region code suffix.
    intl = support_plan_from_dict({
        "promoted_title": "X", "region": "UK", "formats": ["remnant_video"],
        "pluto": {"categories": ["Sci-Fi"]},
    })
    t3i = next(t for t in eng.build(intl, "remnant_video").tiers if t.id == 3)
    cati = next(d for d in t3i.dimensions if d.key == "pluto_category")
    assert "SG: PlutoTV Category: Sci-Fi: UK" in [r["segment_name"] for r in cati.resolved if r.get("id")]


def test_recommended_show_feeds_tier1_carousel():
    plan = load_plan(FRISCO)
    targeting = TargetingEngine().build(plan, "remnant_video")
    tier1 = next(t for t in targeting.tiers if t.id == 1)
    carousel = next(d for d in tier1.dimensions if d.key == "home_carousel_recommendation")
    assert carousel.values == ["Frisco King"]


def test_guaranteed_placements_built_from_args():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    prem = next(p for p in order.placements if p.format == "premium_preroll")
    assert prem.guaranteed
    assert prem.nests_in == "existing_guaranteed_order"
    assert prem.arguments["recommended_show"] == "Frisco King"
    # P+ adult Plan lines now carry Tier 1 targeting (audience segments) instead of a genre arg.
    assert "genre" not in prem.arguments
    assert prem.tier == 1 and prem.targeting_ids.get("dda")
