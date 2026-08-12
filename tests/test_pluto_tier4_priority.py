"""Pluto TV Tier 4 priority: :15 and :30-and-above run HOTTER at 8 (override -8); shorter
creatives (:5/:6/:10/:20) stay at 10 (override -10). Non-Pluto campaigns keep flat 10.
Verified against live 'Pluto TV - {Region}' IOs."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _tier4_by_duration(campaign, region):
    o = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region=region, campaign={"name": campaign},
        durations=[30, 45, 15, 20, 10, 5, 6], pluto={"channels": ["Comedy"]},
        showlist=["FBI"])))
    out = {}
    for p in o.placements:
        if p.tier == 4 and p.duration is not None:
            out[p.duration] = FreeWheelClient._placement_body(p).get("override", {}).get("value")
    return out


def test_pluto_tier4_hotter_for_15_and_30_plus():
    for campaign, region in [("Pluto TV - USA", "USA"), ("Pluto TV - UK", "UK")]:
        t4 = _tier4_by_duration(campaign, region)
        assert t4[15] == -8, (campaign, t4)
        assert t4[30] == -8 and t4[45] == -8, (campaign, t4)


def test_pluto_tier4_short_creatives_stay_10():
    t4 = _tier4_by_duration("Pluto TV - USA", "USA")
    for dur in (5, 6, 10, 20):
        assert t4[dur] == -10, (dur, t4)


def test_non_pluto_tier4_stays_flat_10():
    t4 = _tier4_by_duration("Paramount + - USA", "USA")
    assert t4 and all(v == -10 for v in t4.values()), t4
