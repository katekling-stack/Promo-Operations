"""Standard (non-tiered) build: one platform-wide placement per duration (+ pause) at the
config/standard.yaml priorities/caps, NO tier stack, still excluding title + audience."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(**kw):
    base = dict(promoted_title="NCIS", showlist=["FBI"], standard=True)
    base.update(kw)
    return OrderBuilder().build(support_plan_from_dict(base))


def _ovr(p):
    return FreeWheelClient._placement_body(p).get("override", {}).get("value")


def _excludes(p):
    b = FreeWheelClient._placement_body(p)
    series, aud = set(), set()
    for s in b.get("relationship_targeting", {}).get("set", []):
        ni = (s.get("content_targeting") or {}).get("network_items") or {}
        series |= set((ni.get("exclude") or {}).get("series", []))
        aud |= set((s.get("audience_targeting") or {}).get("exclude", {}).get("audience_item", []))
    return series, aud


def test_standard_is_non_tiered_one_per_duration():
    o = _order(region="USA", campaign={"name": "Pluto TV - USA"}, durations=[30, 15])
    assert len(o.placements) == 2                       # one per duration, no tier fan-out
    assert all(not p.targeting.tiers for p in o.placements)
    assert all("(Tier" not in p.name for p in o.placements)


def test_standard_adults_domestic_priorities():
    o = _order(region="USA", campaign={"name": "Pluto TV - USA"}, durations=[30, 15])
    by_dur = {p.duration: _ovr(p) for p in o.placements}
    assert by_dur[30] == -7 and by_dur[15] == -8       # sheet -7/-8 -> BELOW_PAYING_ADS -7/-8


def test_standard_still_excludes_title_and_audience():
    o = _order(region="USA", campaign={"name": "Pluto TV - USA"}, durations=[30])
    series, aud = _excludes(o.placements[0])
    assert series and aud, "standard placement must still exclude promoted series + audience"


def test_standard_international_pluto_priority():
    o = _order(region="UK", campaign={"name": "Pluto TV - UK"}, durations=[30])
    assert _ovr(o.placements[0]) == -6                  # intl_pluto :30 -> -6


def test_standard_pause_placement_priority():
    # Force pause on (universally optional) and confirm the pause standard priority (-7).
    o = _order(region="USA", campaign={"name": "Pluto TV - USA"}, durations=[30],
               product_overrides={"pause_ads": True})
    pause = [p for p in o.placements if p.format == "pause_ads"]
    assert pause, "expected a standard pause placement"
    assert _ovr(pause[0]) == -7                         # adults_domestic pause -> -7
