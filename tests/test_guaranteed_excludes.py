"""Plan-placement exclude rules (kids + adults, all regions):
Bumper excludes SG Stream Type: Live (929395); Pre-Roll excludes VG Format: Clips
(73410101) — on EVERY set."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _excludes(placement):
    body = FreeWheelClient._placement_body(placement)
    return [s.get("content_targeting", {}).get("network_items", {}).get("exclude", {}) or {}
            for s in body["relationship_targeting"]["set"]]


def test_adult_guaranteed_excludes():
    plan = support_plan_from_dict({
        "promoted_title": "Frisco King", "region": "USA",
        "campaign": {"name": "Paramount + - USA"}, "content_type": "show", "content_id": "1",
        "durations": [30], "genres": ["Drama"],
        "formats": ["premium_preroll", "essential_bumper"],
    })
    order = OrderBuilder().build(plan)
    preroll = next(p for p in order.placements if "Pre-Roll" in p.name)
    bumper = next(p for p in order.placements if "Bumper" in p.name)
    # Pre-Roll: Clips VG on every set; Bumper: Stream Type Live SG on every set.
    assert all("73410101" in e.get("video_group", []) for e in _excludes(preroll))
    assert all("929395" in e.get("site_group", []) for e in _excludes(bumper))
    # And the inverse doesn't leak: bumper has no Clips VG exclude.
    assert all("73410101" not in e.get("video_group", []) for e in _excludes(bumper))


def test_kids_guaranteed_excludes():
    plan = support_plan_from_dict({
        "promoted_title": "Avatar", "region": "USA",
        "campaign": {"name": "Paramount + - Kids - USA"}, "content_type": "show",
        "content_id": "1", "durations": [30], "kids_audience": ["older"],
    })
    order = OrderBuilder().build(plan)
    preroll = next(p for p in order.placements if "Pre-Roll" in p.name)
    bumper = next(p for p in order.placements if "Bumper" in p.name)
    assert all("73410101" in e.get("video_group", []) for e in _excludes(preroll))
    assert all("929395" in e.get("site_group", []) for e in _excludes(bumper))


def test_clips_vg_only_on_premium_preroll_not_remnant():
    """VG Format: Clips (73410101) is a Premium Pre-Roll exclude ONLY — it must not
    ride on the remnant tier stack (regression: it leaked onto every Tier-3 Genre set)."""
    plan = support_plan_from_dict({
        "promoted_title": "Traitors Australia", "region": "AU",
        "campaign": {"name": "Paramount + - AU"}, "content_type": "show",
        "content_id": "1", "durations": [30], "showlist": ["NCIS"], "genres": ["Drama"],
    })
    order = OrderBuilder().build(plan)
    for p in order.placements:
        if p.guaranteed:
            continue
        for e in _excludes(p):
            assert "73410101" not in e.get("video_group", []), p.name
    # ... but the Premium Pre-Roll still carries it.
    preroll = next(p for p in order.placements if "Pre-Roll" in p.name)
    assert all("73410101" in e.get("video_group", []) for e in _excludes(preroll))
