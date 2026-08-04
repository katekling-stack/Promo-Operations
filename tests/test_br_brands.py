"""Brazil — same structures as LATAM (tiered P+ / Pluto, combined-Pluto kids, Nick
Pluto line) but geo targets country Brazil (21), not a region grouping."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _geo(p):
    return FreeWheelClient._placement_body(p).get("geography_targeting", {}).get("include", {})


def test_pplus_br_tiered_geo_country():
    plan = support_plan_from_dict({
        "promoted_title": "UFC: Fight Night", "region": "BR",
        "campaign": {"name": "Paramount + - BR"}, "content_type": "show",
        "content_id": "956519957", "season_or_messaging": "Now Streaming",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Drama"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_br"
    assert all(_geo(p) == {"country": ["21"]} for p in order.placements)   # Brazil
    assert {p.tier for p in order.placements if not p.guaranteed} == {1, 2, 3, 4}
    p15 = next(p for p in order.placements if p.tier == 1 and p.duration == 15)
    assert "69304" in p15.ad_unit_ids and "71999" in p15.ad_unit_ids


def test_br_kids_and_nick():
    kids = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Dora", "region": "BR",
        "campaign": {"name": "Paramount + - Kids - BR"}, "content_type": "show",
        "content_id": "1", "season_or_messaging": "Now Streaming",
        "durations": [15], "kids_audience": ["older", "younger"]}))
    rem = next(p for p in kids.placements if not p.guaranteed)
    assert rem.name == "Dora - Now Streaming - 15 - Kids - BR - [ShowID:1]"
    assert _geo(rem) == {"country": ["21"]}

    nick = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Spongebob", "region": "BR",
        "campaign": {"name": "Nick - Kids - BR"}, "season_or_messaging": "Craft It",
        "durations": [30], "kids_audience": ["older", "younger"]}))
    assert nick.placements[0].name == "Spongebob - Craft It - 30 (Pluto) - Kids - BR"
    # Nick is not a Pluto TV campaign -> no Samsung exclude.
    exc = FreeWheelClient._placement_body(nick.placements[0])["relationship_targeting"][
        "set"][0]["content_targeting"]["network_items"].get("exclude", {})
    assert not any(s in exc.get("site_group", []) for s in ["1121578", "1164068", "1164069"])
