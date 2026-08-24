"""FreeWheel daypart windows can't wrap past midnight (start must be < end). An overnight
window like 9PM->5AM is auto-split at load time into the two windows FreeWheel needs, so a
live push no longer half-creates an IO that then 422s on "start time later than end time"."""

from __future__ import annotations

from promo_ops.plan_loader import _dayparts


def test_overnight_window_is_split_into_two():
    out = _dayparts([{"start_day": "MONDAY", "end_day": "SUNDAY",
                      "start_time": "09:00PM", "end_time": "05:00AM"}])
    assert out == [
        {"start_day": "MONDAY", "end_day": "SUNDAY", "start_time": "09:00PM", "end_time": "11:00PM"},
        {"start_day": "MONDAY", "end_day": "SUNDAY", "start_time": "12 MIDNIGHT", "end_time": "05:00AM"},
    ]


def test_daytime_window_is_unchanged():
    out = _dayparts([{"start_day": "MONDAY", "end_day": "FRIDAY",
                      "start_time": "06:00AM", "end_time": "11:00PM"}])
    assert out == [{"start_day": "MONDAY", "end_day": "FRIDAY",
                    "start_time": "06:00AM", "end_time": "11:00PM"}]


def test_every_split_window_has_start_before_end():
    # The whole point: no emitted window may have start >= end (FreeWheel rejects it).
    from promo_ops.plan_loader import _time_ordinal
    for start, end in [("09:00PM", "05:00AM"), ("11:00PM", "02:00AM"), ("01:00PM", "01:00AM")]:
        out = _dayparts([{"start_day": "MONDAY", "end_day": "MONDAY",
                          "start_time": start, "end_time": end}])
        assert out, (start, end)
        for w in out:
            assert _time_ordinal(w["start_time"]) < _time_ordinal(w["end_time"]), w


def test_empty_dayparts_stay_empty():
    assert _dayparts([]) == []
    assert _dayparts(None) == []
