"""Kids audience (Older/Younger) resolution + the 'no kids -> no kids IOs' gate."""

from __future__ import annotations

import pytest

from promo_ops.config import kids_video_groups
from promo_ops.order_builder import OrderBuilder
from promo_ops.models import SupportPlan
from promo_ops.plan_loader import support_plan_from_dict, validate_plan


def test_kids_video_group_resolution():
    older = kids_video_groups(["older"])
    younger = kids_video_groups(["younger"])
    both = kids_video_groups(["older", "younger"])
    # base (86471529) is always included when any audience is selected
    assert set(older) == {"73408862", "86471529"}
    assert set(younger) == {"73408864", "86471529"}
    assert set(both) == {"73408862", "73408864", "86471529"}


def test_no_audience_resolves_empty():
    assert kids_video_groups([]) == []
    assert kids_video_groups(None) == []


def test_kids_audience_parsed_from_targeting_input():
    # It arrives via the Salesforce/sheet targeting, as a list.
    plan = support_plan_from_dict({
        "promoted_title": "Kamp Koral", "region": "USA",
        "campaign": {"name": "Paramount + - USA"},
        "kids_audience": ["older"],
    })
    assert plan.kids_audience == ["older"]


def test_unknown_audience_value_is_flagged():
    plan = support_plan_from_dict({
        "promoted_title": "T", "region": "USA",
        "campaign": {"name": "Paramount + - USA"},
        "kids_audience": ["toddler"],
    })
    assert any("Kids Audience" in p for p in validate_plan(plan))


def test_kids_brand_with_no_audience_builds_nothing(monkeypatch):
    # A brand flagged kids builds no placements unless an audience is selected.
    builder = OrderBuilder()
    monkeypatch.setitem(builder._brands["brands"], "paramount_plus_domestic",
                        {**builder._brands["brands"]["paramount_plus_domestic"], "kids": True})
    plan = SupportPlan(promoted_title="T", region="USA",
                       brand="paramount_plus_domestic",
                       formats=["remnant_video"], kids_audience=[])
    order = builder.build(plan)
    assert order.placements == []

    plan.kids_audience = ["older"]
    order2 = builder.build(plan)
    assert len(order2.placements) > 0
