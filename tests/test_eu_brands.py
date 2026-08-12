"""EU markets (FR, IT, GSA, FI, DK, NO, SE, ES) — international P+/Pluto/Nick.
Tiered 2/3/4 (no Tier 1), combined Pluto, INTL pre-roll + house units (House Pre-Roll
drops at :30, INTL pre-roll retained), per-country geo (GSA = Germany+Switzerland+Austria)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _geo(p):
    return FreeWheelClient._placement_body(p).get("geography_targeting", {}).get("include", {})


def test_pplus_fr_house_units_with_global_tier1():
    plan = support_plan_from_dict({
        "promoted_title": "Star Trek", "region": "FR",
        "campaign": {"name": "Paramount + - FR"}, "content_type": "show", "content_id": "1",
        "season_or_messaging": "Now Streaming", "durations": [15, 30],
        "showlist": ["NCIS"], "genres": ["Drama"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_fr"
    assert all(_geo(p) == {"country": ["54"]} for p in order.placements)   # France
    assert {p.tier for p in order.placements if not p.guaranteed} == {1, 2, 3, 4}   # Tier 1 global
    p15 = next(p for p in order.placements if p.tier == 2 and p.duration == 15)
    p30 = next(p for p in order.placements if p.tier == 2 and p.duration == 30)
    # INTL pre-roll + House Pre/Mid/Post on short; :30 drops the House Pre-Roll only
    # (INTL pre-roll is retained). FR/GSA/IT now match the other P+ INTL markets.
    assert p15.ad_unit_ids == ["69304", "71999", "72000", "72001"]
    assert p30.ad_unit_ids == ["69304", "72000", "72001"]
    assert any("Pause Ad" in p.name for p in order.placements)
    assert any("Bumper - Basic Plan" in p.name for p in order.placements)


def test_gsa_multi_country_geo():
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "X", "region": "GSA", "campaign": {"name": "Paramount + - GSA"},
        "content_id": "1", "durations": [30], "showlist": ["NCIS"], "genres": ["Drama"]}))
    assert set(_geo(order.placements[0])["country"]) == {"41", "30", "9"}  # DE/CH/AT


def test_eu_pluto_kids_and_nick_and_double_space_it_routing():
    # Pluto TV Kids: flat kids on 929392, no infix; Nick: "(Pluto)" infix, no Samsung.
    pk = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Detective Conan", "region": "FR",
        "campaign": {"name": "Pluto TV - Kids - FR"}, "season_or_messaging": "Sur Pluto TV",
        "durations": [30], "kids_audience": ["older"]}))
    assert pk.placements[0].name == "Detective Conan - Sur Pluto TV - 30 - Kids - FR"

    nick = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Loud House", "region": "FR", "campaign": {"name": "Nick - Kids - FR"},
        "season_or_messaging": "Symphonies", "durations": [30], "kids_audience": ["older", "younger"]}))
    assert nick.placements[0].name == "Loud House - Symphonies - 30 (Pluto) - Kids - FR"
    exc = FreeWheelClient._placement_body(nick.placements[0])["relationship_targeting"][
        "set"][0]["content_targeting"]["network_items"].get("exclude", {})
    assert not any(s in exc.get("site_group", []) for s in ["1121578", "1164068", "1164069"])

    # The double-spaced "Paramount + - Kids  - IT" campaign still routes to its brand.
    it = support_plan_from_dict({
        "promoted_title": "X", "region": "IT", "campaign": {"name": "Paramount + - Kids  - IT"},
        "content_id": "1", "durations": [30], "kids_audience": ["older"]})
    assert it.brand == "paramount_plus_kids_it"


def test_nordics_pluto_only_geo():
    for region, campaign, cid in [("NO", "Pluto TV - NO", "122"), ("SE", "Pluto TV - SE", "140"),
                                  ("DK", "Pluto TV - DK", "42"), ("FI", "Pluto TV - FI", "51")]:
        order = OrderBuilder().build(support_plan_from_dict({
            "promoted_title": "X", "region": region, "campaign": {"name": campaign},
            "durations": [30], "pluto": {"channels": ["Comedy"]}}))
        assert all(_geo(p) == {"country": [cid]} for p in order.placements), region
