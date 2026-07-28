"""Canada — Pluto, not tiered (Genre + Categories only), language-routed, geo CA."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(campaign: str):
    plan = support_plan_from_dict({
        "promoted_title": "Scary Movie", "region": "CA",
        "campaign": {"name": campaign}, "season_or_messaging": "AI Scene Lift",
        "durations": [15, 30], "genres": ["Comedy", "Crime"],
        "pluto": {"categories": ["Movies - Action"]},
    })
    return plan, OrderBuilder().build(plan)


def test_ca_pluto_english_not_tiered():
    plan, order = _order("Pluto TV - English - CA")
    assert plan.brand == "pluto_ca_en"
    names = [p.name for p in order.placements]
    # NOT tiered: no "(Tier N)" in the name, one placement per duration
    assert names == ["Scary Movie - AI Scene Lift - 15 - CA",
                     "Scary Movie - AI Scene Lift - 30 - CA"]
    assert not any("Tier" in n for n in names)
    assert all(p.geo_country_ids == ["27"] for p in order.placements)     # Canada
    # Pluto-only Genre set (main SG 929392), standard genre VGs
    body = FreeWheelClient._placement_body(order.placements[0])
    genre = next(s for s in body["relationship_targeting"]["set"] if s["set_name"] == "Genre")
    subs = genre["content_targeting"]["network_items"]["include"]["set"]
    assert set(next(s["site_group"] for s in subs if s.get("site_group"))) == {"929392"}
    # House Pre-Roll on 15s, dropped on 30s
    assert set(order.placements[0].ad_unit_ids) == {"71999", "72000", "72001"}
    assert set(order.placements[1].ad_unit_ids) == {"72000", "72001"}
