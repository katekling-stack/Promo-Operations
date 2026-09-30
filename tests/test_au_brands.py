"""Australia — no Pluto: P+ AU is tiered, main SGs exclude Pluto (929392), geo 10."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def test_pplus_au_tiered_no_pluto():
    plan = support_plan_from_dict({
        "promoted_title": "UFC", "region": "AU",
        "campaign": {"name": "Paramount + - AU"}, "content_type": "show",
        "content_id": "956519957", "season_or_messaging": "Fight Night",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Sports"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_au"
    assert all(p.geo_country_ids == ["10"] for p in order.placements)      # Australia
    assert any("- 15 (Tier 1) - AU" in p.name for p in order.placements)   # tiered, parens
    assert any("Bumper - Basic Plan" in p.name for p in order.placements)
    # main SGs have NO Pluto (929392); AU has no Pluto and no Samsung exclude
    t4 = next(p for p in order.placements if p.tier == 4)
    body = FreeWheelClient._placement_body(t4)
    main = set(body["relationship_targeting"]["set"][0]["content_targeting"]
               ["network_items"]["include"]["site_group"])
    assert main == {"932583", "932591", "932592"}
    assert "929392" not in main
    assert not any(FreeWheelClient._placement_body(p).get("content_targeting")
                   for p in order.placements)   # no Samsung/content exclude (non-Pluto)
    # INTL pre-roll kept, house pre-roll drops at 30s
    p15 = next(p for p in order.placements if p.tier == 1 and p.duration == 15)
    p30 = next(p for p in order.placements if p.tier == 1 and p.duration == 30)
    assert "69304" in p15.ad_unit_ids and "71999" in p15.ad_unit_ids
    assert "69304" in p30.ad_unit_ids and "71999" not in p30.ad_unit_ids


def _tier4_setnames(order, fmt="remnant_video"):
    for p in order.placements:
        if p.tier == 4 and p.format == fmt:
            rt = FreeWheelClient._placement_body(p).get("relationship_targeting") or {}
            return p, [s.get("set_name") for s in rt.get("set", [])]
    return None, []


def test_pplus_au_tier4_carries_ufc_guarantee_set():
    # Paramount + - AU Tier 4 adult lines always include the UFC guarantee argument:
    # SG ParamountPlus (932583) AND VG Franchise: UFC (1625229912), with NO excludes so it
    # delivers regardless of the line's other restrictions.
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "UFC 300", "region": "AU",
        "campaign": {"name": "Paramount + - AU"}, "content_type": "show",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Sports"]}))
    p4, names = _tier4_setnames(order)
    assert "Franchise: UFC" in names, names
    ufc = next(s for s in FreeWheelClient._placement_body(p4)["relationship_targeting"]["set"]
               if s.get("set_name") == "Franchise: UFC")
    inc = ufc["content_targeting"]["network_items"]["include"]
    subs = {tuple(sorted(d.keys() - {"relation_in_set"}))[0]: d for d in inc["set"]}
    assert subs["site_group"]["site_group"] == ["932583"]
    assert subs["video_group"]["video_group"] == ["1625229912"]
    assert "exclude" not in ufc["content_targeting"]["network_items"]   # delivers regardless
    # Only on Tier 4 — not Tiers 1-3.
    for p in order.placements:
        if p.tier and p.tier != 4:
            rt = FreeWheelClient._placement_body(p).get("relationship_targeting") or {}
            assert "Franchise: UFC" not in [s.get("set_name") for s in rt.get("set", [])]


def test_ufc_set_not_on_network_10_or_other_brands():
    # UFC set targets P+ inventory -> only P+ lines, not the Network 10 breakout.
    au = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "UFC 300", "region": "AU", "campaign": {"name": "Paramount + - AU"},
        "content_type": "show", "durations": [30], "showlist": ["NCIS"], "genres": ["Sports"],
        "product_overrides": {"network_10": True}}))
    _, n10_names = _tier4_setnames(au, fmt="network_10_remnant")
    assert "Franchise: UFC" not in n10_names
    # A different brand never gets it.
    uk = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "UFC 300", "region": "UK", "campaign": {"name": "Paramount + - UK"},
        "content_type": "show", "durations": [30], "showlist": ["NCIS"], "genres": ["Sports"]}))
    assert not any("Franchise: UFC" in [s.get("set_name") for s in
                   (FreeWheelClient._placement_body(p).get("relationship_targeting") or {}).get("set", [])]
                   for p in uk.placements)
