"""Nick / Nick Jr (AU) — Kids O&O. Standard kids remnant on the Paramount+ SG;
the Include Network 10 opt-in adds the (10 Streaming) Kids remnant (Ten Play SG) +
the 10 Streaming After Mid-Roll Bumper. Kids VG symmetry + priority/cap mirror live."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(campaign="Nick - Kids - AU", network_10=False, kids=("older", "younger")):
    raw = {
        "promoted_title": "Spongebob Squarepants", "region": "AU",
        "campaign": {"name": campaign}, "season_or_messaging": "Generic",
        "durations": [15, 30], "kids_audience": list(kids),
    }
    if network_10:
        raw["product_overrides"] = {"network_10": True}
    plan = support_plan_from_dict(raw)
    return plan, OrderBuilder().build(plan)


def _kids_set(p):
    body = FreeWheelClient._placement_body(p)
    s = body["relationship_targeting"]["set"][0]
    inc = s["content_targeting"]["network_items"]["include"]
    subs = inc.get("set", [inc])
    sgs = set().union(*[set(x.get("site_group", [])) for x in subs])
    vgs = set().union(*[set(x.get("video_group", [])) for x in subs])
    exc = s["content_targeting"]["network_items"].get("exclude", {})
    return sgs, vgs, set(exc.get("video_group", []))


def test_nick_au_standard_kids_remnant():
    plan, order = _order()
    assert plan.brand == "nick_au"
    # Only the standard kids remnant (no Network 10): 2 durations.
    assert len(order.placements) == 2
    names = [p.name for p in order.placements]
    assert "Spongebob Squarepants - Generic - Kids - 15 - AU" in names
    p15 = next(p for p in order.placements if p.duration == 15)
    p30 = next(p for p in order.placements if p.duration == 30)
    # Paramount House units only; pre-roll drops at 30s. Geo AU.
    assert p15.ad_unit_ids == ["71999", "72000", "72001"]
    assert p30.ad_unit_ids == ["72000", "72001"]
    assert all(p.geo_country_ids == ["10"] for p in order.placements)
    # Kids remnant runs at the duration-based kids priority (:15 -> -2, :30 -> -1) + kids cap.
    body = FreeWheelClient._placement_body(p15)
    assert body["override"] == {"mode": "BELOW_PAYING_ADS", "value": -2}
    assert FreeWheelClient._placement_body(p30)["override"] == {"mode": "BELOW_PAYING_ADS", "value": -1}
    assert body["delivery"]["frequency_cap"]["period"] == "15"
    # Kids VGs + COPPA AND the Paramount+ SG (932583); AU has no Pluto.
    sgs, vgs, _ = _kids_set(p15)
    assert sgs == {"932400", "932583"}
    assert vgs == {"73408862", "73408864", "86471529"}


def test_nick_au_network_10_opt_in():
    plan, order = _order(network_10=True)
    names = [p.name for p in order.placements]
    # Standard (2) + 10 Streaming remnant (2) + After Mid-Roll Bumper (1) = 5.
    assert len(order.placements) == 5
    assert "Spongebob Squarepants - Generic - Kids - 15 (10 Streaming) - AU" in names
    assert ("Spongebob Squarepants - 10 Streaming After Mid-Roll Bumper - Kids - AU"
            in names)
    # 10 Streaming remnant: Net10 pre-roll + house; Ten Play SG (1238405).
    net = next(p for p in order.placements
               if "(10 Streaming)" in p.name and p.duration == 15)
    assert "70313" in net.ad_unit_ids
    sgs, _, _ = _kids_set(net)
    assert sgs == {"932400", "1238405"}
    # Bumper is guaranteed, HIGHEST, Net10 bumper unit.
    bump = next(p for p in order.placements if "Bumper" in p.name)
    assert bump.guaranteed and bump.ad_unit_ids == ["70049"]
    assert FreeWheelClient._placement_body(bump)["override"] == {"precedence_level": "HIGHEST"}


def test_nick_au_kids_vg_symmetry():
    # Older-only excludes Nick Jr (younger); younger-only excludes Nick (older).
    _, older = _order(kids=("older",))
    _, vgs, exc = _kids_set(older.placements[0])
    assert "73408862" in vgs and "73408864" not in vgs
    assert exc == {"73408864"}

    _, younger = _order(kids=("younger",))
    _, vgs, exc = _kids_set(younger.placements[0])
    assert "73408864" in vgs and "73408862" not in vgs
    assert exc == {"73408862"}


def test_nick_jr_au_routes_to_its_own_campaign():
    plan, _ = _order(campaign="Nick Jr. - Kids - AU")
    assert plan.brand == "nick_jr_au"
