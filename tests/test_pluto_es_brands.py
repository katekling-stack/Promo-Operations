"""Pluto En Español — simple untargeted remnant (mirrors live reference IOs)."""

from __future__ import annotations

from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(title: str, campaign: str):
    plan = support_plan_from_dict({
        "promoted_title": title, "region": "USA",
        "campaign": {"name": campaign}, "durations": [15, 30],
    })
    return plan, OrderBuilder().build(plan)


def test_pluto_es_adult_matches_reference():
    plan, order = _order("Crímenes imperfectos", "Pluto TV - En Espanol - USA")
    assert plan.brand == "pluto_es_adult"
    names = [p.name for p in order.placements]
    assert names == [
        "Crímenes imperfectos - Stream Ahora - 15 - Spanish - USA",
        "Crímenes imperfectos - Stream Ahora - 30 - Spanish - USA",
    ]
    p15 = order.placements[0]
    p30 = order.placements[1]
    # House Pre-Roll on 15s only; mid+post on 30s. No relationship targeting.
    assert set(p15.ad_unit_ids) == {"71999", "72000", "72001"}
    assert set(p30.ad_unit_ids) == {"72000", "72001"}
    assert all(p.no_targeting for p in order.placements)
    assert all(p.geo_country_ids == ["165"] for p in order.placements)


def test_pluto_es_kids_is_plain_remnant_not_gated():
    # The En Español Kids brand runs plain remnant (no kids VG targeting), so it builds
    # even without a kids audience.
    plan, order = _order("El Reino Infantil", "Pluto TV - Kids - En Espanol - USA")
    assert plan.brand == "pluto_es_kids"
    assert order.placements[0].name == "El Reino Infantil - Stream Ahora - 15 - Kids"
    assert len(order.placements) == 2
