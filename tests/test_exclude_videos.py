"""Movie-video exclusions: individual FreeWheel Video (asset) IDs excluded on every
placement via content_targeting exclude `video` (movies are single assets, not series)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _video_excludes(body):
    """Every `video` exclude across a placement body — from each relationship set's
    content_targeting.network_items.exclude and the set-less placement-level exclude."""
    vids = set()

    def grab(ct):
        if not ct:
            return
        vids.update((ct.get("exclude") or {}).get("video", []))            # set-less form
        ni = ct.get("network_items") or {}
        vids.update((ni.get("exclude") or {}).get("video", []))            # in-set form

    grab(body.get("content_targeting"))
    for s in body.get("relationship_targeting", {}).get("set", []):
        grab(s.get("content_targeting"))
    return vids


def test_movie_video_ids_excluded_on_every_placement():
    plan = support_plan_from_dict(dict(
        promoted_title="The Man In The White Van", region="USA",
        campaign={"name": "Paramount + - USA"}, durations=[30], showlist=["FBI"],
        genres=["Horror"], content_type="movie", content_id="956479957",
        exclude_videos=["111222333", "444555666"],
    ))
    order = OrderBuilder().build(plan)
    assert order.placements, "expected placements built"
    for p in order.placements:
        vids = _video_excludes(FreeWheelClient._placement_body(p))
        assert {"111222333", "444555666"} <= vids, f"{p.name}: video excludes = {vids}"


def test_no_video_excludes_when_none_given():
    plan = support_plan_from_dict(dict(
        promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
        durations=[30], showlist=["FBI"],
    ))
    order = OrderBuilder().build(plan)
    for p in order.placements:
        assert _video_excludes(FreeWheelClient._placement_body(p)) == set()
