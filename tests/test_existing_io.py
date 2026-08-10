"""Add-to-existing-IO: when existing_io_id is set, placements are created INTO that IO
(no new IO) — e.g. adding a new season's lines to the IO that already exists."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def test_existing_io_appends_not_creates_new():
    plan = support_plan_from_dict(dict(
        promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
        durations=[30], showlist=["FBI"], season_or_messaging="Season 2",
        existing_io_id="96043219"))
    order = OrderBuilder().build(plan)
    assert order.existing_io_id == "96043219"
    fw = FreeWheelClient.to_freewheel_plan(order)
    assert fw.get("append_to_existing_io") == "96043219"


def test_no_existing_io_builds_a_new_io():
    plan = support_plan_from_dict(dict(
        promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
        durations=[30], showlist=["FBI"]))
    fw = FreeWheelClient.to_freewheel_plan(OrderBuilder().build(plan))
    assert "append_to_existing_io" not in fw
    assert fw.get("insertion_order_body")            # a real IO body to create
