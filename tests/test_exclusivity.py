"""Custom Exclusivity: when the IO carries a Brand, every placement excludes that Brand.
Scope ALL_AD_UNITS for below-paying lines (standard + tiered remnant),
TARGETED_AD_UNITS_ONLY for guaranteed lines (pre-roll / bumper / lockdown). Also replaces
FreeWheel's default so the kids-only 'Rating: G' industry exclude is never carried."""

from __future__ import annotations

from promo_ops.brands_resolver import BrandResolver
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _plan(**kw):
    base = dict(promoted_title="FBI", region="USA", campaign={"name": "Paramount + - USA"},
                durations=[15], showlist=["NCIS"], genres=["Drama"],
                product_overrides={"premium_preroll": True, "essential_bumper": True},
                flight={"start": "2026-09-01", "end": "2026-09-30"})
    base.update(kw)
    order = OrderBuilder().build(support_plan_from_dict(base))
    return order, FreeWheelClient.to_freewheel_plan(order)


def _brand():
    r = BrandResolver().load()
    name = next(b for b in r.brands_for("USA") if "Paramount" in b)
    return name, r.resolve("USA", name)


def test_scope_by_line_type_and_brand_excluded():
    name, bid = _brand()
    order, plan = _plan(io_brand=name)
    assert plan["insertion_order_body"]["brand_id"] == bid
    saw_remnant = saw_guar = False
    for p, body in zip(order.placements, plan["placement_bodies"]):
        ex = body.get("exclusivity")
        assert ex, f"missing exclusivity on {p.name}"
        assert ex["level_of_exclusivity"] == "CUSTOM"
        assert ex["custom_exclusivity_exemption"]["exclude"]["items"] == [
            {"id": int(bid), "type": "BRAND"}]
        if p.guaranteed:
            assert ex["scope_of_exclusivity"] == "TARGETED_AD_UNITS_ONLY"
            saw_guar = True
        else:
            assert ex["scope_of_exclusivity"] == "ALL_AD_UNITS"
            saw_remnant = True
    assert saw_remnant and saw_guar, "expected both remnant and guaranteed lines"


def test_no_brand_no_exclusivity():
    _, plan = _plan(io_brand=None)
    assert all("exclusivity" not in b for b in plan["placement_bodies"])
    assert "brand_id" not in plan["insertion_order_body"]
