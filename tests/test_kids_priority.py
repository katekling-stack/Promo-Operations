"""Kids remnant priority by duration (GLOBAL): :30+ -> -1, :15 -> -2, shorter creatives
(:5/:6/:10/:20) -> -3. Replaces the old flat kids priority of -1. Non-kids brands are
unaffected (they keep the tier stack)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _by_duration(campaign, region, durations, **kw):
    base = dict(promoted_title="X", region=region, campaign={"name": campaign},
                durations=durations, kids_audience=["older"])
    base.update(kw)
    o = OrderBuilder().build(support_plan_from_dict(base))
    out = {}
    for p in o.placements:
        if p.format != "pause_ads" and p.duration is not None:
            out[p.duration] = FreeWheelClient._placement_body(p).get("override", {}).get("value")
    return out


def test_kids_priority_30_and_above_is_minus_1():
    d = _by_duration("Pluto TV - Kids - USA", "USA", [30, 45, 60])
    assert d[30] == -1 and d[45] == -1 and d[60] == -1, d


def test_kids_priority_15_is_minus_2():
    d = _by_duration("Pluto TV - Kids - USA", "USA", [15])
    assert d[15] == -2, d


def test_kids_priority_short_creatives_are_minus_3():
    d = _by_duration("Pluto TV - Kids - USA", "USA", [5, 6, 10, 20])
    for dur in (5, 6, 10, 20):
        assert d[dur] == -3, (dur, d)


def test_kids_priority_is_global_across_kids_brands():
    for campaign, region in [("Nickelodeon - Kids - USA", "USA"), ("Paramount + - Kids - USA", "USA"),
                             ("Pluto TV - Kids - UK", "UK")]:
        d = _by_duration(campaign, region, [30, 15])
        assert d.get(30) == -1 and d.get(15) == -2, (campaign, d)


def test_non_kids_unaffected():
    # A non-kids adult brand keeps the tier stack (not the flat kids priority).
    o = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="X", region="USA", campaign={"name": "Paramount + - USA"},
        durations=[15], showlist=["FBI"])))
    assert sorted({p.tier for p in o.placements if not p.guaranteed}) == [1, 2, 3, 4]
