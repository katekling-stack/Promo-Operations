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
    resolver = AudienceSegmentResolver().load()
    match = resolver.resolve("Top Gear", region="USA")
    assert match.matched
    assert match.records[0].segment_id == "25455246"


def test_resolver_reports_unmatched():
    resolver = AudienceSegmentResolver().load()
    match = resolver.resolve("Some Nonexistent Show", region="USA")
    assert not match.matched
    assert match.records == []


# --- targeting engine ------------------------------------------------------- #

def test_tier1_gated_by_region():
    engine = TargetingEngine()
    plan = support_plan_from_dict({
        "promoted_title": "X", "region": "UK", "brand": "paramount_network",
        "formats": ["remnant_video"], "showlist": ["Top Gear"],
    })
    targeting = engine.build(plan, "remnant_video")
    tier_ids = [t.id for t in targeting.tiers]
    assert 1 not in tier_ids  # UK is not Tier-1 eligible
    assert 3 in tier_ids


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


def test_pause_ads_excludes_tier4():
    engine = TargetingEngine()
    plan = load_plan(FRISCO)
    targeting = engine.build(plan, "pause_ads")
    assert 4 not in [t.id for t in targeting.tiers]


# --- order builder ---------------------------------------------------------- #

def test_order_builder_per_tier_and_duration_naming():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    assert order.name == "Frisco King - USA"           # IO name
    assert order.campaign["name"] == "Paramount + - USA"  # existing parent campaign
    names = [p.name for p in order.placements]
    # remnant video: 4 tiers x 2 durations = 8; pause ads: 3 tiers; guaranteed: 2 -> 13
    assert len(order.placements) == 13
    assert "Frisco King - Season 1 - 30 - Tier 1 - USA" in names
    assert "Frisco King - Season 1 - 15 - Tier 4 - USA" in names


def test_guaranteed_placement_named_by_content_id():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    prem = next(p for p in order.placements if p.format == "premium_preroll")
    assert prem.name == "Frisco King [ShowID:]"        # blank id -> fill-in marker

    plan.content_type = "movie"; plan.content_id = "12345"
    order2 = OrderBuilder().build(plan)
    prem2 = next(p for p in order2.placements if p.format == "premium_preroll")
    assert prem2.name == "Frisco King [MovieID:12345]"


def test_placements_carry_priority_and_freq_cap():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    assert t1.priority_level == 1
    assert t1.frequency_cap == "1 per 30 min / 20 per month"


def test_order_carries_template_ref():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    assert order.template_ref["template_campaign_id"] == "86543608"
    assert order.network_id == "520311"


def test_promoted_show_excluded_from_every_placement():
    plan = load_plan(FRISCO)
    order = OrderBuilder().build(plan)
    for p in order.placements:
        assert "Frisco King" in p.exclusions


def test_manual_tier1_audience_segments_applied():
    plan = load_plan(FRISCO)
    targeting = TargetingEngine().build(plan, "remnant_video")
    tier1 = next(t for t in targeting.tiers if t.id == 1)
    seg_dim = next(d for d in tier1.dimensions if d.key == "audience_segments")
    names = [s["segment_name"] for s in seg_dim.resolved]
    assert "High Stakes Drama Fans" in names
    assert "Procedural Drama Fans" in names


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
    assert prem.arguments["genre"]  # genre-specific arg present
