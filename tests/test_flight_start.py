"""USA flight start is 3:00 AM ET (3 AM ET = 12 AM PT) so a campaign goes live West-to-East
on the selected date. Other markets default to midnight local. Driven by
regions.yaml `flight_start_time`."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.models import Flight


def _start(region):
    return FreeWheelClient._placement_schedule(
        region, Flight(start="2026-09-01", end="2026-09-30"))["start_time"]


def test_usa_starts_at_3am():
    assert _start("USA") == "2026-09-01T03:00"


def test_other_markets_default_to_midnight():
    for region in ("UK", "LATAM", "AU", "GSA"):
        assert _start(region) == "2026-09-01T00:00", region


def test_end_time_unchanged_end_of_day():
    sched = FreeWheelClient._placement_schedule("USA", Flight(start="2026-09-01", end="2026-09-30"))
    assert sched["end_time"] == "2026-09-30T23:59"


def test_explicit_time_in_flight_is_respected():
    # A caller-supplied T-time is never overridden.
    sched = FreeWheelClient._placement_schedule("USA", Flight(start="2026-09-01T09:30", end="2026-09-30"))
    assert sched["start_time"] == "2026-09-01T09:30"
