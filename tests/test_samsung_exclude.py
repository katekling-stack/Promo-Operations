"""Pluto TV brands exclude Samsung TV Plus SGs on every placement (region-scoped)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _content_exclude(campaign, region, **extra):
    plan = support_plan_from_dict({"promoted_title": "X", "region": region,
                                   "campaign": {"name": campaign}, "durations": [30],
                                   "genres": ["Drama"], **extra})
    order = OrderBuilder().build(plan)
    sgs = set()
    for p in order.placements:
        ct = FreeWheelClient._placement_body(p).get("content_targeting", {})
        sgs |= set((ct.get("exclude", {}) or {}).get("site_group", []))
    return sgs, order


def test_us_pluto_excludes_us_samsung():
    sgs, _ = _content_exclude("Pluto TV - USA", "USA")
    assert {"932411", "932412"} <= sgs


def test_intl_pluto_excludes_intl_samsung():
    sgs, order = _content_exclude("Pluto TV - French - CA", "CA",
                                  season_or_messaging="Sur Pluto TV")
    assert {"1121578", "1164068", "1164069"} <= sgs
    # even the plain-remnant French line (no relationship sets) carries it
    assert all(FreeWheelClient._placement_body(p).get("content_targeting")
               for p in order.placements)


def test_non_pluto_brand_has_no_samsung_exclude():
    sgs, _ = _content_exclude("Paramount + - USA", "USA")
    assert not sgs
