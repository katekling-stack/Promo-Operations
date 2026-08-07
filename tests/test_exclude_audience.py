"""Audience-segment exclusions: an existing DDA segment (picked by name) is excluded on
every adult placement's audience_targeting.exclude, in every relationship set."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.audience_segments import AudienceSegmentResolver


def _seg_name_and_id():
    """A real segment name + id from the synced data, to exclude by name."""
    r = AudienceSegmentResolver().load()
    rec = next(x for x in r._records if x.segment_id)
    return rec.segment_name, rec.segment_id


def _audience_excludes(body):
    ids = set()
    for s in body.get("relationship_targeting", {}).get("set", []):
        at = s.get("audience_targeting") or {}
        ids.update((at.get("exclude") or {}).get("audience_item", []))
    return ids


def test_named_audience_segment_excluded_on_every_set():
    name, seg_id = _seg_name_and_id()
    plan = support_plan_from_dict(dict(
        promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
        durations=[30], showlist=["FBI"], exclude_audience_segments=[name]))
    order = OrderBuilder().build(plan)
    saw = False
    for p in order.placements:
        sets = FreeWheelClient._placement_body(p).get("relationship_targeting", {}).get("set", [])
        if any(s.get("audience_targeting") for s in sets):
            assert seg_id in _audience_excludes(FreeWheelClient._placement_body(p)), p.name
            saw = True
    assert saw, "expected at least one placement with audience targeting"
