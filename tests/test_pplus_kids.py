"""Paramount+ Kids — Kids targeting shape + Older/Younger + the no-audience gate."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

CAMPAIGN = "Paramount + - Kids - USA"


def _build(audience, **extra):
    plan = support_plan_from_dict({
        "promoted_title": "Avatar: The Last Airbender", "region": "USA",
        "campaign": {"name": CAMPAIGN}, "content_type": "show",
        "content_id": "61456660", "season_or_messaging": "Evergreen",
        "durations": [15, 30], "kids_audience": audience, **extra,
    })
    return plan, OrderBuilder().build(plan)


def _kids_set(placement):
    body = FreeWheelClient._placement_body(placement)
    sets = body.get("relationship_targeting", {}).get("set", [])
    inc = sets[0]["content_targeting"]["network_items"]["include"]
    subs = inc["set"] if "set" in inc else [inc]
    vgs = next((s.get("video_group") for s in subs if s.get("video_group")), [])
    # the "main" subset is the one with only site_group (no video_group)
    main = next((s.get("site_group") for s in subs if s.get("video_group") is None), None)
    return set(vgs or []), set(main or [])


def test_no_kids_audience_builds_nothing():
    _, order = _build([])
    assert order.placements == []


def test_older_kids_full_shape():
    plan, order = _build(["older"])
    assert plan.brand == "paramount_plus_kids"
    assert len(order.placements) == 4
    names = [p.name for p in order.placements]
    assert "Avatar: The Last Airbender - Evergreen - 15 - Kids - USA - [ShowID:61456660]" in names
    assert ("Paramount + - Pre-Roll - Premium Plan - Avatar: The Last Airbender - Kids "
            "- USA - [ShowID:61456660]") in names
    assert ("Paramount + - Bumper - Essential Plan - Avatar: The Last Airbender - Kids "
            "- USA - [ShowID:61456660]") in names

    remnant = next(p for p in order.placements if not p.guaranteed and p.duration == 15)
    vgs, main = _kids_set(remnant)
    assert vgs == {"73408862", "86471529"}          # Older + base
    assert main == {"929392", "932583"}             # Pluto + P+
    assert set(remnant.ad_unit_ids) == {"71999", "72000", "72001"}

    preroll = next(p for p in order.placements if p.guaranteed and "Pre-Roll" in p.name)
    vgs_g, main_g = _kids_set(preroll)
    assert vgs_g == {"73408862", "86471529"}
    assert main_g == {"932583"}                     # guaranteed = P+ only
    assert set(preroll.ad_unit_ids) == {"61120", "67610"}


def test_younger_uses_younger_video_group():
    _, order = _build(["younger"])
    remnant = next(p for p in order.placements if not p.guaranteed)
    vgs, _ = _kids_set(remnant)
    assert vgs == {"73408864", "86471529"}          # Younger + base


def test_both_ages_include_all_video_groups():
    _, order = _build(["older", "younger"])
    remnant = next(p for p in order.placements if not p.guaranteed)
    vgs, _ = _kids_set(remnant)
    assert vgs == {"73408862", "73408864", "86471529"}


def test_pplus_kids_uk_combined_remnant_and_basic_plan():
    # Pluto is folded into the STANDARD kids remnant (P+ + Pluto UK site groups on ONE line),
    # not a separate "(Pluto)" breakout — so there's one remnant per duration, no "(Pluto)".
    plan = support_plan_from_dict({
        "promoted_title": "Kamp Koral", "region": "UK",
        "campaign": {"name": "Paramount + - Kids - UK"}, "content_type": "show",
        "content_id": "61457250", "season_or_messaging": "Streaming Now",
        "durations": [15, 30], "kids_audience": ["older"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_kids_uk"
    assert len(order.placements) == 4                   # 2 remnant + Pre-Roll + Bumper
    assert all(p.geo_country_ids == ["56"] for p in order.placements)   # UK
    names = [p.name for p in order.placements]
    assert not any("(Pluto)" in n for n in names)       # no breakout line

    remnant15 = next(p for p in order.placements
                     if p.name == "Kamp Koral - Streaming Now - 15 - Kids - UK - [ShowID:61457250]")
    # Keeps the P+ UK house ad units (INTL pre-roll 69304 + house pre-roll on 15s)
    assert set(remnant15.ad_unit_ids) == {"69304", "71999", "72000", "72001"}
    _, main = _kids_set(remnant15)
    assert main == {"932583", "1109067", "1120870"}     # P+ + Pluto UK kids SGs on ONE line

    assert any("Bumper - Basic Plan" in p.name for p in order.placements)


def _remnant_exclude_vgs(audience):
    _, order = _build(audience)
    remnant = next(p for p in order.placements if not p.guaranteed)
    exc = (FreeWheelClient._placement_body(remnant)["relationship_targeting"]["set"][0]
           ["content_targeting"]["network_items"].get("exclude", {}))
    return set(exc.get("video_group", []))


def test_single_age_excludes_the_other_cable_kids_vg():
    # Older-only excludes Nick Jr (73408864); younger-only excludes Nick (73408862).
    assert "73408864" in _remnant_exclude_vgs(["older"])
    assert "73408862" not in _remnant_exclude_vgs(["older"])
    assert "73408862" in _remnant_exclude_vgs(["younger"])
    assert "73408864" not in _remnant_exclude_vgs(["younger"])
    # Both ages -> include Nick + Nick Jr + COPPA, no age exclusion.
    both = _remnant_exclude_vgs(["older", "younger"])
    assert "73408862" not in both and "73408864" not in both


def test_us_pluto_dnr_scope():
    # DNR 951172 on every US brand EXCEPT Pluto TV - USA.
    def dnr(campaign, **extra):
        plan = support_plan_from_dict({"promoted_title": "X", "region": "USA",
                                       "campaign": {"name": campaign}, "durations": [30],
                                       "genres": ["Drama"], **extra})
        return any("951172" in (p.extra_exclude_site_groups or [])
                   for p in OrderBuilder().build(plan).placements)
    assert dnr("CBS Sports - USA") is True
    assert dnr("Paramount + - Kids - USA", kids_audience=["older"]) is True
    assert dnr("Pluto TV - USA") is False
