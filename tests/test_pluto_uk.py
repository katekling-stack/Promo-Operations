"""Pluto TV UK — standard tiered remnant (Pluto-only), standard genres, region UK."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order():
    plan = support_plan_from_dict({
        "promoted_title": "MacGyver", "region": "UK",
        "campaign": {"name": "Pluto TV - UK"}, "durations": [15, 30],
        "genres": ["Drama", "Action & Adventure"],
        "pluto": {"channels": ["Westerns"], "categories": ["Movies - Action"]},
    })
    return plan, OrderBuilder().build(plan)


def test_pluto_uk_brand_and_geo():
    plan, order = _order()
    assert plan.brand == "pluto_tv_uk"
    assert order.placements, "expected tiered placements"
    assert all(p.geo_country_ids == ["56"] for p in order.placements)          # UK
    # House pre/mid/post on short creatives; :30+ drops the House Pre-Roll (mid+post only).
    for p in order.placements:
        if p.duration and p.duration >= 30:
            assert set(p.ad_unit_ids) == {"72000", "72001"}, p.name            # mid + post
        else:
            assert set(p.ad_unit_ids) == {"71999", "72000", "72001"}, p.name   # pre + mid + post


def test_pluto_uk_is_pluto_only_tiered():
    _, order = _order()
    tiers = sorted({p.tier for p in order.placements})
    assert set(tiers) == {1, 2, 3, 4}        # Tier 1 global (update 2026-08-05), incl. Pluto
    # Tier 3 genre set uses the standard genre resolver (main SG = Pluto 929392 only)
    t3 = next(p for p in order.placements if p.tier == 3)
    body = FreeWheelClient._placement_body(t3)
    genre = next(s for s in body["relationship_targeting"]["set"] if s["set_name"] == "Genre")
    subs = genre["content_targeting"]["network_items"]["include"]["set"]
    site_sub = next(s for s in subs if s.get("site_group"))
    assert set(site_sub["site_group"]) == {"929392"}
    assert any(s.get("video_group") for s in subs)   # standard genre VGs present
