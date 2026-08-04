"""Planner-specified excludes keep a series/channel off EVERY placement."""

from __future__ import annotations

from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.order_builder import OrderBuilder


def _order(**over):
    raw = {"promoted_title": "Frisco King", "region": "USA",
           "campaign": {"name": "Paramount + - USA"}, "durations": [30],
           "showlist": ["Yellowstone"], "genres": ["Drama"], **over}
    return OrderBuilder().build(support_plan_from_dict(raw))


def test_exclude_series_applies_to_every_placement():
    order = _order(exclude_series=["NCIS"])
    assert order.placements
    # NCIS resolves to at least one real series id, present on EVERY placement.
    for p in order.placements:
        assert any(sid for sid in p.exclude_series), p.name


def test_exclude_channels_add_site_group_to_every_placement():
    base = _order()
    with_excl = _order(exclude_channels=["Westerns"])
    base_sgs = set(base.placements[0].extra_exclude_site_groups)
    added = set(with_excl.placements[0].extra_exclude_site_groups) - base_sgs
    assert added, "excluded channel added no site group"
    for p in with_excl.placements:
        assert added <= set(p.extra_exclude_site_groups), p.name


def test_no_excludes_is_a_no_op():
    order = _order()
    # Frisco King isn't a real series -> self-exclusion empty, no extra excludes.
    assert all(p.exclude_series == [] for p in order.placements)


def test_excludes_round_trip_through_plan_dict():
    plan = support_plan_from_dict({
        "promoted_title": "T", "region": "USA", "campaign": {"name": "Paramount + - USA"},
        "exclude_series": ["NCIS", "Yellowstone"], "exclude_channels": ["CBS Drama"]})
    assert plan.exclude_series == ["NCIS", "Yellowstone"]
    assert plan.exclude_channels == ["CBS Drama"]
