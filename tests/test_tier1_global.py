"""Tier 1 is included GLOBALLY for adult orders (update 2026-08-05): every region builds
tiers 1-4, and the new Tier 1 mirrors the region's tiers 2-4 site groups with audience
segments layered in."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _tiers_and_sgs(region, campaign):
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "NCIS", "region": region, "campaign": {"name": campaign},
        "durations": [30], "genres": ["Drama"]}))
    tiers, sgs = set(), {}
    for p in order.placements:
        if "(Tier " in p.name and " - 30 " in p.name:
            t = p.name.split("(Tier ")[1][0]
            tiers.add(t)
            body = FreeWheelClient._placement_body(p)
            got = set()
            for s in body.get("relationship_targeting", {}).get("set", []):
                inc = s.get("content_targeting", {}).get("network_items", {}).get("include", {})
                for sub in (inc.get("set") or [inc]):
                    if sub.get("site_group"):
                        got |= set(sub["site_group"])
            sgs[t] = got
    return tiers, sgs


@pytest.mark.parametrize("region, campaign", [
    ("GSA", "Paramount + - GSA"), ("UK", "Paramount + - UK"), ("IT", "Paramount + - IT"),
])
def test_previously_ineligible_regions_now_build_tier1(region, campaign):
    tiers, sgs = _tiers_and_sgs(region, campaign)
    assert {"1", "2", "3", "4"} <= tiers, f"{region} missing tiers: {tiers}"
    # New Tier 1 uses the same site groups as the region's tiers 2-4.
    assert sgs["1"] and sgs["1"] == sgs["3"], f"{region} Tier 1 SGs {sgs['1']} != Tier 3 {sgs['3']}"
