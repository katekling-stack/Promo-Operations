"""Pluto TV brands exclude Samsung TV Plus SGs on every placement (region-scoped).
Tiered lines carry it in the relationship-set excludes (the API drops a placement-level
content_targeting when sets are present); set-less flat lines use content_targeting."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _samsung_on_every_placement(campaign, region, expected, **extra):
    plan = support_plan_from_dict({"promoted_title": "X", "region": region,
                                   "campaign": {"name": campaign}, "durations": [30],
                                   "genres": ["Drama"], **extra})
    order = OrderBuilder().build(plan)
    assert order.placements
    for p in order.placements:
        body = FreeWheelClient._placement_body(p)
        found = set((body.get("content_targeting", {}) or {}).get("exclude", {}).get("site_group", []))
        for s in body.get("relationship_targeting", {}).get("set", []):
            found |= set(s.get("content_targeting", {}).get("network_items", {})
                         .get("exclude", {}).get("site_group", []))
        assert expected <= found, f"{p.name}: missing {expected - found}"


def test_us_pluto_excludes_us_samsung():
    _samsung_on_every_placement("Pluto TV - USA", "USA", {"932411", "932412"})


def test_intl_pluto_excludes_intl_samsung_incl_flat():
    _samsung_on_every_placement("Pluto TV - French - CA", "CA",
                                {"1121578", "1164068", "1164069"},
                                season_or_messaging="Sur Pluto TV")


def test_non_pluto_brand_has_no_samsung_exclude():
    plan = support_plan_from_dict({"promoted_title": "X", "region": "USA",
                                   "campaign": {"name": "Paramount + - USA"},
                                   "durations": [30], "genres": ["Drama"]})
    order = OrderBuilder().build(plan)
    for p in order.placements:
        assert not (FreeWheelClient._placement_body(p).get("content_targeting"))
        assert "1121578" not in (p.extra_exclude_site_groups or [])
