"""ADULT self-exclusion also excludes the promoted title's own audience segment (DDA) on
every set — combined with the series self-exclusion. Kids do no audience targeting, so kids
placements carry none."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(**plan):
    return OrderBuilder().build(support_plan_from_dict(plan))


def test_adult_excludes_promoted_audience_segment_on_every_set():
    order = _order(promoted_title="Tulsa King", region="USA",
                   campaign={"name": "Paramount + - USA"}, durations=[30], genres=["Drama"])
    seg = set(order.promoted_audience_items)
    assert seg, "Tulsa King should resolve to a DDA segment"
    for p in order.placements:
        for s in FreeWheelClient._placement_body(p).get("relationship_targeting", {}).get("set", []):
            exc = set(s.get("audience_targeting", {}).get("exclude", {}).get("audience_item", []))
            assert seg & exc, f"{p.name}/{s.get('set_name')} missing audience exclude"


def test_audience_exclude_merges_with_tier1_dda_include():
    # Tier 1 targets DDA (include) AND excludes the promoted segment — both nodes present.
    order = _order(promoted_title="Tulsa King", region="USA", campaign={"name": "Paramount + - USA"},
                   durations=[30], showlist=["NCIS"])
    t1 = [p for p in order.placements if "(Tier 1)" in p.name and "Pause" not in p.name][0]
    at = FreeWheelClient._placement_body(t1)["relationship_targeting"]["set"][0]["audience_targeting"]
    assert at["include"]["audience_item"]                       # NCIS DDA include
    assert set(order.promoted_audience_items) & set(at["exclude"]["audience_item"])


def test_kids_have_no_audience_targeting():
    order = _order(promoted_title="Tulsa King", region="BR",
                   campaign={"name": "Paramount + - Kids - BR"}, durations=[30],
                   kids_audience=["older"])
    assert order.promoted_audience_items == []
    for p in order.placements:
        for s in FreeWheelClient._placement_body(p).get("relationship_targeting", {}).get("set", []):
            assert "audience_targeting" not in s, f"{p.name} should have no audience targeting"


def test_unresolved_title_has_no_audience_items():
    order = _order(promoted_title="Zzxq Nonexistent Title", region="USA",
                   campaign={"name": "Paramount + - USA"}, durations=[30])
    assert order.promoted_audience_items == []
