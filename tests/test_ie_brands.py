"""Ireland (country 73) — no Pluto. P+ IE mirrors the UK P+ tiered model (tiers 2/3/4,
no Tier 1) but with NO Pluto anywhere: pause main SGs drop 929392, and P+ Kids IE runs
the P+ line only (no Pluto breakout line)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _main_sgs(p, idx=0):
    body = FreeWheelClient._placement_body(p)
    inc = body["relationship_targeting"]["set"][idx]["content_targeting"]["network_items"]["include"]
    subs = inc.get("set", [inc])
    return [set(s["site_group"]) for s in subs if s.get("site_group")]


def test_pplus_ie_adult_no_tier1_no_pluto_pause():
    plan = support_plan_from_dict({
        "promoted_title": "Walker", "region": "IE",
        "campaign": {"name": "Paramount + - IE"}, "content_type": "show",
        "content_id": "634500157", "season_or_messaging": "Season 1-4",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Drama"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_ie"
    assert all(p.geo_country_ids == ["73"] for p in order.placements)   # Ireland
    # No Tier 1 (UK/IE are not tier1-eligible); remnant is tiers 2/3/4.
    tiers = {p.tier for p in order.placements if not p.guaranteed and "Pause" not in p.name}
    assert tiers == {2, 3, 4}
    # Remnant main SGs = P+/CBS Local/VCBS, no Pluto.
    t4 = next(p for p in order.placements if p.tier == 4 and "Pause" not in p.name)
    assert {"932583", "932591", "932592"} in _main_sgs(t4)
    # Pause Ad main SGs drop Pluto (929392): [932583,932592] AND the pause platform SGs.
    pause = next(p for p in order.placements if "Pause Ad (Tier 4)" in p.name)
    subsets = _main_sgs(pause)
    assert {"932583", "932592"} in subsets
    assert not any("929392" in s for s in subsets)
    assert {"929447", "929449"} in subsets
    # Basic Plan bumper (UK/IE convention), Premium Pre-Roll present.
    names = [p.name for p in order.placements]
    assert any("Bumper - Basic Plan - Walker - IE" in n for n in names)
    assert any("Pre-Roll - Premium Plan - Walker - IE" in n for n in names)


def test_pplus_kids_ie_pplus_line_only_no_pluto():
    plan = support_plan_from_dict({
        "promoted_title": "Spongebob", "region": "IE",
        "campaign": {"name": "Paramount + - Kids - IE"}, "content_type": "show",
        "content_id": "61456636", "durations": [15, 30], "kids_audience": ["older"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_kids_ie"
    names = [p.name for p in order.placements]
    # P+ line only — no "(Pluto)" breakout line anywhere.
    assert not any("(Pluto)" in n for n in names)
    assert "Spongebob - Now Streaming - 15 - Kids - IE - [ShowID:61456636]" in names
    # Kids remnant: COPPA + P+ SG (932583), Ireland geo, INTL+house units.
    rem = next(p for p in order.placements if p.duration == 15 and not p.guaranteed)
    assert rem.geo_country_ids == ["73"]
    assert "69304" in rem.ad_unit_ids
    subs = _main_sgs(rem)
    assert {"932583"} in subs and {"932400"} in subs
    # older-only excludes Nick Jr (younger VG) — global kids symmetry still applies.
    body = FreeWheelClient._placement_body(rem)
    exc = body["relationship_targeting"]["set"][0]["content_targeting"]["network_items"].get("exclude", {})
    assert "73408864" in exc.get("video_group", [])
