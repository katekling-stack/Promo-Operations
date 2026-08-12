"""Per-format guaranteed caps (Premium 1/week, Essential+Basic Bumper 1/2hrs, global),
placement flighting in the target market's time zone, and Pluto's always-on Tier 3 genre."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(**plan):
    plan.setdefault("durations", [30])
    return OrderBuilder().build(support_plan_from_dict(plan))


def _cap(placement):
    return (FreeWheelClient._placement_body(placement).get("delivery") or {}).get("frequency_cap")


def test_premium_preroll_capped_one_per_week():
    order = _order(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                   genres=["Drama"])
    prem = next(p for p in order.placements if p.format == "premium_preroll")
    assert _cap(prem) == {"value": "1", "type": "IMPRESSION", "period": "10080"}   # 1 week


def test_essential_bumper_capped_one_per_two_hours():
    order = _order(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                   genres=["Drama"])
    ess = next(p for p in order.placements if p.format == "essential_bumper")
    assert _cap(ess) == {"value": "1", "type": "IMPRESSION", "period": "120"}       # 2 hours


def test_basic_plan_bumper_uk_also_one_per_two_hours():
    # UK/IE "Basic Plan" bumper is the essential_bumper template renamed -> same 2h cap.
    order = _order(promoted_title="NCIS", region="UK", campaign={"name": "Paramount + - UK"},
                   genres=["Drama"])
    basic = next((p for p in order.placements if p.format == "essential_bumper"), None)
    assert basic is not None and "Basic Plan" in basic.name
    assert _cap(basic) == {"value": "1", "type": "IMPRESSION", "period": "120"}


def test_placement_schedule_uses_target_market_timezone():
    cases = {
        "USA": "(GMT-05:00) America - New York",
        "AU": "(GMT+10:00) Australia - Melbourne",
        "UK": "(GMT+00:00) Europe - London",
        "GSA": "(GMT+01:00) Europe - Amsterdam",
        "LATAM": "(GMT-03:00) America - Buenos Aires, Argentina",
    }
    campaign = {"USA": "Paramount + - USA", "AU": "Paramount + - AU", "UK": "Paramount + - UK",
                "GSA": "Paramount + - GSA", "LATAM": "Paramount + - LATAM"}
    for region, tz in cases.items():
        order = _order(promoted_title="NCIS", region=region, campaign={"name": campaign[region]},
                       genres=["Drama"], flight={"start": "2026-08-10", "end": "2026-09-10"})
        body = FreeWheelClient.to_freewheel_plan(order)["placement_bodies"][0]
        sch = body["schedule"]
        assert sch["time_zone"] == tz, region
        # USA starts at 3 AM ET (West-to-East go-live); other markets at midnight local.
        expected_start = "2026-08-10T03:00" if region == "USA" else "2026-08-10T00:00"
        assert sch["start_time"] == expected_start and sch["end_time"] == "2026-09-10T23:59", region


def test_no_schedule_when_no_flight():
    order = _order(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                   genres=["Drama"])
    body = FreeWheelClient.to_freewheel_plan(order)["placement_bodies"][0]
    assert "schedule" not in body           # no flight -> CM sets it, never a partial


def test_pluto_tier3_always_has_a_genre_argument():
    # Pluto with categories but NO genres still gets a Genre set in Tier 3 (global rule).
    order = _order(promoted_title="NCIS", region="USA", campaign={"name": "Pluto TV - USA"},
                   pluto={"categories": ["Comedy"], "channels": ["Comedy"]})
    t3 = next(p for p in order.placements if "(Tier 3)" in p.name)
    names = [s["set_name"] for s in FreeWheelClient._placement_body(t3)["relationship_targeting"]["set"]]
    assert "Genre" in names and "Pluto Categories" in names


def test_pplus_tier3_without_genre_is_unchanged():
    # Non-Pluto (P+) with categories but no genres: no forced Genre set (Pluto-only rule).
    order = _order(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                   pluto={"categories": ["Comedy"]})
    t3 = next(p for p in order.placements if "(Tier 3)" in p.name and "Pause" not in p.name)
    names = [s["set_name"] for s in FreeWheelClient._placement_body(t3)["relationship_targeting"]["set"]]
    assert "Pluto Categories" in names and "Genre" not in names
