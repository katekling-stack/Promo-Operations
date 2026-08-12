"""Daypart (time-of-day) restrictions. Empty = 24/7 (no daypart_targeting). A window emits
daypart_targeting {time_zone, part:[{start_day,end_day,start_time,end_time}]} in the market's
time zone, on every placement."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _plan(**kw):
    base = dict(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                durations=[30], showlist=["FBI"], flight={"start": "2026-09-01", "end": "2026-09-30"})
    base.update(kw)
    return FreeWheelClient.to_freewheel_plan(OrderBuilder().build(support_plan_from_dict(base)))


def test_default_is_24x7_no_daypart():
    plan = _plan()
    assert all("daypart_targeting" not in b for b in plan["placement_bodies"])


def test_window_emits_daypart_on_every_placement():
    plan = _plan(durations=[30, 15], dayparts=[
        {"start_day": "MONDAY", "end_day": "FRIDAY", "start_time": "06:00PM", "end_time": "11:00PM"}])
    assert plan["placement_bodies"], "expected placements"
    for b in plan["placement_bodies"]:
        dp = b.get("daypart_targeting")
        assert dp and dp["part"] == [{"start_day": "MONDAY", "end_day": "FRIDAY",
                                      "start_time": "06:00PM", "end_time": "11:00PM"}]
        assert dp["time_zone"] == "(GMT-05:00) America - New York"   # USA market TZ


def test_daypart_uses_market_timezone():
    plan = _plan(region="UK", campaign={"name": "Paramount + - UK"}, dayparts=[
        {"start_day": "SATURDAY", "end_day": "SUNDAY", "start_time": "12:00PM", "end_time": "06:00PM"}])
    assert plan["placement_bodies"][0]["daypart_targeting"]["time_zone"] == "(GMT+00:00) Europe - London"


def test_malformed_daypart_window_dropped():
    # Missing end_time -> the window is dropped (never a partial); falls back to 24/7.
    plan = _plan(dayparts=[{"start_day": "MONDAY", "end_day": "FRIDAY", "start_time": "06:00PM"}])
    assert all("daypart_targeting" not in b for b in plan["placement_bodies"])


def test_multiple_windows_kept():
    plan = _plan(dayparts=[
        {"start_day": "MONDAY", "end_day": "FRIDAY", "start_time": "06:00PM", "end_time": "11:00PM"},
        {"start_day": "SATURDAY", "end_day": "SATURDAY", "start_time": "10:00AM", "end_time": "02:00PM"}])
    assert len(plan["placement_bodies"][0]["daypart_targeting"]["part"]) == 2
