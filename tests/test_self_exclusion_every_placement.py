"""The promoted title's own Video Series must be excluded on EVERY placement and EVERY
argument (relationship set) — including tiers that would otherwise be empty for a given
plan (no showlist / channels / genres / categories supplied)."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _series_ids(plan):
    return set(OrderBuilder()._self_exclusions(plan)[0])


def _every_placement_and_arg_excludes(plan_dict):
    plan = support_plan_from_dict(plan_dict)
    order = OrderBuilder().build(plan)
    ss = _series_ids(plan)
    assert ss, "test title must resolve to a Video Series"
    for p in order.placements:
        body = FreeWheelClient._placement_body(p)
        sets = body.get("relationship_targeting", {}).get("set", [])
        if sets:
            for s in sets:   # EVERY argument
                exc = s.get("content_targeting", {}).get("network_items", {}).get("exclude", {})
                assert ss & set(exc.get("series", [])), f"{p.name}: set {s.get('set_name')!r} missing series exclude"
        else:               # set-less line: exclude on the placement-level content, or a no-targeting sponsorship
            ct = body.get("content_targeting", {})
            exc = (ct.get("exclude") or {}).get("series", [])
            assert (ss & set(exc)) or getattr(p, "no_targeting", False), f"{p.name}: no series exclude"
    return order


@pytest.mark.parametrize("plan_dict, label", [
    ({"promoted_title": "NCIS", "region": "USA", "campaign": {"name": "Paramount + - USA"},
      "durations": [30], "genres": ["Drama"]}, "USA genres-only (empty Tier 2)"),
    ({"promoted_title": "NCIS", "region": "USA", "campaign": {"name": "Paramount + - USA"},
      "durations": [30]}, "USA title-only (empty Tier 2 + Tier 3)"),
    ({"promoted_title": "NCIS", "region": "LATAM", "campaign": {"name": "Paramount + - LATAM"},
      "durations": [30], "genres": ["Comedy"]}, "LATAM genres-only"),
    ({"promoted_title": "NCIS", "region": "BR", "campaign": {"name": "Paramount + - Kids - BR"},
      "durations": [30], "kids_audience": ["older"]}, "Kids BR"),
])
def test_series_excluded_on_every_placement_and_argument(plan_dict, label):
    _every_placement_and_arg_excludes(plan_dict)


def test_empty_tier2_and_tier3_still_produce_a_targeting_set():
    # A plan with no showlist/channels/genres/categories must still give Tier 2 and Tier 3
    # a platform-constrained set (not a bare, untargeted placement).
    plan = support_plan_from_dict({"promoted_title": "NCIS", "region": "USA",
                                   "campaign": {"name": "Paramount + - USA"}, "durations": [30]})
    order = OrderBuilder().build(plan)
    for p in order.placements:
        if "(Tier 2)" in p.name or "(Tier 3)" in p.name:
            body = FreeWheelClient._placement_body(p)
            assert body.get("relationship_targeting", {}).get("set"), f"{p.name} has no targeting set"
