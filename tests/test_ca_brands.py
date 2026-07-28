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


def test_ca_pluto_english_is_tiered_pluto_only():
    plan, order = _order("Pluto TV - English - CA")
    assert plan.brand == "pluto_ca_en"
    names = [p.name for p in order.placements]
    # English = tiered (parenthetical), Pluto-only, geo Canada
    assert "Scary Movie - AI Scene Lift - 15 (Tier 4) - CA" in names
    assert all(p.geo_country_ids == ["27"] for p in order.placements)
    t4 = next(p for p in order.placements if p.tier == 4)
    body = FreeWheelClient._placement_body(t4)
    main = set(body["relationship_targeting"]["set"][0]["content_targeting"]
               ["network_items"]["include"]["site_group"])
    assert main == {"929392"}                          # Pluto only
    # non-US brand: no US Pluto DNR exclude
    for p in order.placements:
        assert "951172" not in (p.extra_exclude_site_groups or [])


def test_ca_pplus_english_is_tiered_and_combined():
    plan = support_plan_from_dict({
        "promoted_title": "Avatar Aang", "region": "CA",
        "campaign": {"name": "Paramount + - English - CA"}, "content_type": "movie",
        "content_id": "ALVE01", "season_or_messaging": "Now Streaming",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Drama"],
        "pluto": {"channels": ["Westerns"]},
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_ca"
    names = [p.name for p in order.placements]
    # Fully tiered (parenthetical), combined main SGs (Pluto included), geo Canada
    assert "Avatar Aang - Now Streaming - 15 (Tier 1) - CA" in names
    assert "Avatar Aang - Now Streaming - 30 (Tier 4) - CA" in names
    assert "Paramount + - Bumper - Basic Plan - Avatar Aang - CA - [MovieID:ALVE01]" in names
    assert all(p.geo_country_ids == ["27"] for p in order.placements)

    t4_15 = next(p for p in order.placements
                 if p.name == "Avatar Aang - Now Streaming - 15 (Tier 4) - CA")
    body = FreeWheelClient._placement_body(t4_15)
    main = set(body["relationship_targeting"]["set"][0]["content_targeting"]
               ["network_items"]["include"]["site_group"])
    assert main == {"929392", "932583", "932591", "932592"}      # combined incl Pluto
    assert set(t4_15.ad_unit_ids) == {"69304", "71999", "72000", "72001"}  # INTL + house


def test_ca_pplus_kids_not_tiered_combined():
    plan = support_plan_from_dict({
        "promoted_title": "Avatar Aang: The Last Airbender", "region": "CA",
        "campaign": {"name": "Paramount + - Kids - English - CA"}, "content_type": "movie",
        "content_id": "ALVE01", "season_or_messaging": "Now Streaming",
        "durations": [15, 30], "kids_audience": ["older"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_kids_ca"
    names = [p.name for p in order.placements]
    # not tiered, no "(P+/Pluto)" infix, Essential Plan bumper
    assert "Avatar Aang: The Last Airbender - Now Streaming - 15 - Kids - CA" in names
    assert not any("Tier" in n or "(P+/Pluto)" in n for n in names)
    assert any("Bumper - Essential Plan" in n for n in names)
    assert all(p.geo_country_ids == ["27"] for p in order.placements)
    # combined kids targeting: [Pluto, P+] AND (older VG + base + kids SG)
    remnant = next(p for p in order.placements if not p.guaranteed)
    body = FreeWheelClient._placement_body(remnant)
    subs = body["relationship_targeting"]["set"][0]["content_targeting"]["network_items"]["include"]["set"]
    main = set(next(s["site_group"] for s in subs if s.get("site_group") and not s.get("video_group")))
    assert main == {"929392", "932583"}


def test_ca_pplus_kids_gated_by_audience():
    plan = support_plan_from_dict({
        "promoted_title": "X", "region": "CA",
        "campaign": {"name": "Paramount + - Kids - English - CA"}, "kids_audience": [],
    })
    assert OrderBuilder().build(plan).placements == []
