"""Network 10 (AU) — the "Include Network 10" opt-in adds the (10 Streaming) tiered
lines. Distinct setup: Net10 Live pre-roll + Paramount House units, Ten Play main SGs,
"(10 Streaming)" infix on the tier label."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(include_network_10: bool):
    plan = support_plan_from_dict({
        "promoted_title": "Traitors Australia", "region": "AU",
        "campaign": {"name": "Paramount + - AU"}, "content_type": "show",
        "content_id": "956519957", "season_or_messaging": "Sell",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Sports"],
        "product_overrides": {"network_10": include_network_10},
    })
    return plan, OrderBuilder().build(plan)


def test_include_network_10_checkbox_gates_the_lines():
    _, off = _order(include_network_10=False)
    assert not any("(10 Streaming)" in p.name for p in off.placements)
    # On: 4 tiers x 2 durations = 8 (10 Streaming) lines.
    _, on = _order(include_network_10=True)
    assert sum("(10 Streaming)" in p.name for p in on.placements) == 8


def test_network_10_naming_and_geo():
    plan, order = _order(include_network_10=True)
    assert plan.brand == "paramount_plus_au"
    names = [p.name for p in order.placements]
    # tier always in parens; the (10 Streaming) marker rides after the tier
    assert "Traitors Australia - Sell - 15 (Tier 1) (10 Streaming) - AU" in names
    assert "Traitors Australia - Sell - 30 (Tier 4) (10 Streaming) - AU" in names
    net10 = [p for p in order.placements if "(10 Streaming)" in p.name]
    assert all(p.geo_country_ids == ["10"] for p in net10)   # Australia


def test_network_10_main_sgs_and_ad_units():
    _, order = _order(include_network_10=True)
    net10 = [p for p in order.placements if "(10 Streaming)" in p.name]

    # Ten Play (1238405) + CBS Local + VCBS main SGs on the tier-4 RON set.
    t4 = next(p for p in net10 if p.tier == 4 and p.duration == 15)
    body = FreeWheelClient._placement_body(t4)
    inc = body["relationship_targeting"]["set"][0]["content_targeting"]["network_items"]["include"]
    subs = inc.get("set", [inc])
    main = set(next((s.get("site_group") for s in subs if s.get("site_group")), []))
    assert main == {"932591", "932592", "1238405"}

    # Net10 Live pre-roll (70313) always on; Paramount House pre-roll drops at 30s.
    p15 = next(p for p in net10 if p.tier == 1 and p.duration == 15)
    p30 = next(p for p in net10 if p.tier == 1 and p.duration == 30)
    assert "70313" in p15.ad_unit_ids and "71999" in p15.ad_unit_ids
    assert "70313" in p30.ad_unit_ids and "71999" not in p30.ad_unit_ids


def test_rating_restrictions_apply_only_to_network_10():
    plan = support_plan_from_dict({
        "promoted_title": "Traitors Australia", "region": "AU",
        "campaign": {"name": "Paramount + - AU"}, "content_type": "show",
        "content_id": "956519957", "season_or_messaging": "Sell",
        "durations": [15], "showlist": ["NCIS"], "genres": ["Sports"],
        "product_overrides": {"network_10": True},
        "rating_restrictions": ["99001", "99002"],
    })
    order = OrderBuilder().build(plan)
    net10 = [p for p in order.placements if "(10 Streaming)" in p.name]
    other = [p for p in order.placements if "(10 Streaming)" not in p.name]

    # Rating VGs excluded on the 10 Streaming lines (in every relationship set) ...
    for p in net10:
        assert set(["99001", "99002"]).issubset(set(p.extra_exclude_video_groups))
        body = FreeWheelClient._placement_body(p)
        for s in body["relationship_targeting"]["set"]:
            exc = s["content_targeting"]["network_items"].get("exclude", {})
            assert set(["99001", "99002"]).issubset(set(exc.get("video_group", [])))
    # ... and NOT on the standard P+ AU lines.
    for p in other:
        assert "99001" not in p.extra_exclude_video_groups
