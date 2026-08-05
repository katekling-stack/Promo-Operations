"""Order-level frequency caps (a general rule on every IO's delivery.frequency_cap):
adult USA -> 1/30min AND 20/month; adult international -> 1/30min; kids -> 1/15min.
Verified against production USA adult IOs which carry [1/30min, 20/month]."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _io_caps(**plan):
    order = OrderBuilder().build(support_plan_from_dict(plan))
    body = FreeWheelClient.to_freewheel_plan(order)["insertion_order_body"]
    return order.frequency_caps, (body.get("delivery") or {}).get("frequency_cap")


def test_adult_usa_gets_30min_and_20_per_month():
    strs, fc = _io_caps(promoted_title="X", region="USA",
                        campaign={"name": "Paramount + - USA"}, durations=[30], genres=["Drama"])
    assert strs == ["1 per 30 min", "20 per month"]
    assert fc == [{"value": "1", "type": "IMPRESSION", "period": "30"},
                  {"value": "20", "type": "IMPRESSION", "period": "43200"}]   # 20/month = 43200 min


def test_adult_international_gets_only_30min():
    for region, campaign in [("LATAM", "Paramount + - LATAM"), ("GSA", "Paramount + - GSA"),
                             ("AU", "Paramount + - AU")]:
        strs, fc = _io_caps(promoted_title="X", region=region,
                            campaign={"name": campaign}, durations=[30], genres=["Drama"])
        assert strs == ["1 per 30 min"], region
        assert fc == [{"value": "1", "type": "IMPRESSION", "period": "30"}], region


def test_kids_gets_15min_everywhere():
    strs, fc = _io_caps(promoted_title="X", region="BR",
                        campaign={"name": "Paramount + - Kids - BR"}, durations=[30],
                        kids_audience=["older"])
    assert strs == ["1 per 15 min"]
    assert fc == [{"value": "1", "type": "IMPRESSION", "period": "15"}]


def test_month_period_encodes_to_43200():
    assert FreeWheelClient._fc_period_minutes("20 per month") == "43200"
    assert FreeWheelClient._freq_cap_entry("20 per month") == {
        "value": "20", "type": "IMPRESSION", "period": "43200"}


def test_no_caps_means_no_delivery_block():
    # An order with no resolved caps must not emit an (invalid) empty delivery block.
    from promo_ops.models import Order
    body = FreeWheelClient.to_freewheel_plan(Order(name="x", promoted_title="x",
                                                   brand="", region="USA"))["insertion_order_body"]
    assert "delivery" not in body
