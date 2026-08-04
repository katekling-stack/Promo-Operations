"""LATAM — tiered (domestic-style, combined Pluto) with INTL+house units and a
geography REGION (1069) rather than per-country geo."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def test_pplus_latam_tiered_geo_region():
    plan = support_plan_from_dict({
        "promoted_title": "UFC: Fight Night", "region": "LATAM",
        "campaign": {"name": "Paramount + - LATAM"}, "content_type": "show",
        "content_id": "956519957", "season_or_messaging": "Now Streaming",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Drama"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_latam"
    # Geography REGION 1069 (not per-country) on every placement.
    for p in order.placements:
        body = FreeWheelClient._placement_body(p)
        assert body["geography_targeting"] == {"include": {"region": ["1069"]}}
    # Tiered 1-4, combined-Pluto main SGs; INTL pre-roll kept, house pre-roll drops at :30.
    tiers = {p.tier for p in order.placements if not p.guaranteed}
    assert tiers == {1, 2, 3, 4}
    t4 = next(p for p in order.placements if p.tier == 4 and p.duration == 15)
    inc = FreeWheelClient._placement_body(t4)["relationship_targeting"]["set"][0][
        "content_targeting"]["network_items"]["include"]
    subs = inc.get("set", [inc])
    assert {"929392", "932583", "932591", "932592"} in [set(s.get("site_group", [])) for s in subs]
    p15 = next(p for p in order.placements if p.tier == 1 and p.duration == 15)
    p30 = next(p for p in order.placements if p.tier == 1 and p.duration == 30)
    assert "69304" in p15.ad_unit_ids and "71999" in p15.ad_unit_ids
    assert "69304" in p30.ad_unit_ids and "71999" not in p30.ad_unit_ids
    # Basic Plan bumper (international convention).
    assert any("Bumper - Basic Plan" in p.name for p in order.placements)


def test_pplus_kids_latam_combined_pluto_intl_units():
    plan = support_plan_from_dict({
        "promoted_title": "Dora", "region": "LATAM",
        "campaign": {"name": "Paramount + - Kids - LATAM"}, "content_type": "show",
        "content_id": "1", "season_or_messaging": "Now Streaming",
        "durations": [15, 30], "kids_audience": ["older", "younger"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_kids_latam"
    rem = next(p for p in order.placements if p.duration == 15 and not p.guaranteed)
    # Combined Pluto+P+ main (no split, no infix), INTL + house units, geo region.
    assert "Dora - Now Streaming - 15 - Kids - LATAM - [ShowID:1]" == rem.name
    assert "69304" in rem.ad_unit_ids
    inc = FreeWheelClient._placement_body(rem)["relationship_targeting"]["set"][0][
        "content_targeting"]["network_items"]["include"]
    subs = inc.get("set", [inc])
    assert {"929392", "932583"} in [set(s.get("site_group", [])) for s in subs]


def test_nick_latam_pluto_line_no_samsung():
    plan = support_plan_from_dict({
        "promoted_title": "Casagrandes", "region": "LATAM",
        "campaign": {"name": "Nick - Kids - LATAM"}, "season_or_messaging": "Symphonies",
        "durations": [30], "kids_audience": ["older", "younger"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "nick_latam"
    p = order.placements[0]
    assert p.name == "Casagrandes - Symphonies - 30 (Pluto) - Kids - LATAM"
    # Nick runs on Pluto (929392) but is NOT a Pluto TV campaign -> no Samsung exclude.
    exc = FreeWheelClient._placement_body(p)["relationship_targeting"]["set"][0][
        "content_targeting"]["network_items"].get("exclude", {})
    assert not any(s in exc.get("site_group", [])
                   for s in ["1121578", "1164068", "1164069"])
