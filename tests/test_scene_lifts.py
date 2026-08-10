"""Scene Lifts (Pluto UK/CA/USA): AI -> Tier 3 only; standard -> Tiers 1-3. Placements
append into the existing 'Scene Lifts - {Region}' IO (no new IO); promoted title + audience
still excluded."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict, validate_plan


def _order(scene_lift, region="USA", campaign="Pluto TV - USA"):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region=region, campaign={"name": campaign},
        durations=[30], showlist=["FBI"], genres=["Drama"],
        pluto={"channels": ["Pluto TV Crime"]}, scene_lift=scene_lift)))


def _tiers(order):
    ids = set()
    for p in order.placements:
        for t in p.targeting.tiers:
            ids.add(t.id)
    return ids


def test_ai_scene_lift_is_tier_3_only():
    order = _order("ai")
    assert _tiers(order) == {3}, _tiers(order)
    assert order.scene_lift_io_id == "94434865"          # Adults USA IO (not the full one)


def test_standard_scene_lift_is_tiers_1_2_3():
    order = _order("standard")
    assert _tiers(order) == {1, 2, 3}, _tiers(order)


def test_scene_lift_appends_to_existing_io_not_new():
    plan = FreeWheelClient.to_freewheel_plan(_order("ai"))
    assert plan.get("append_to_existing_io") == "94434865"


def test_scene_lift_rejected_for_unsupported_campaign():
    # Non-Pluto / non-UK-CA-USA campaign can't be a Scene Lift.
    plan = support_plan_from_dict(dict(
        promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
        durations=[30], scene_lift="ai"))
    probs = validate_plan(plan)
    assert any("Scene Lift" in p for p in probs), probs


def test_uk_scene_lift_routes_to_uk_io():
    order = _order("standard", region="UK", campaign="Pluto TV - UK")
    assert order.scene_lift_io_id == "95035745"
    assert _tiers(order) == {1, 2, 3}


def test_scene_lift_is_video_only_no_pause():
    # Even if pause is on, a Scene Lift builds video only.
    order = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region="USA", campaign={"name": "Pluto TV - USA"},
        durations=[30], showlist=["FBI"], scene_lift="standard",
        product_overrides={"pause_ads": True})))
    assert all(p.format != "pause_ads" for p in order.placements)
