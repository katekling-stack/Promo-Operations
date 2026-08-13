"""IO-level Brand: a CM picks a Brand from the advertiser's synced list; it resolves to the
FreeWheel brand_id and is stamped on the Insertion Order. Region-aware; raw brand_id passes
through. Synced from FreeWheel -> data/brands/synced_brands.csv."""

from __future__ import annotations

from promo_ops.brands_resolver import BrandResolver
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _io_body(region, campaign, io_brand=None):
    order = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="FBI", region=region, campaign={"name": campaign},
        durations=[15], showlist=["NCIS"], genres=["Drama"], io_brand=io_brand,
        flight={"start": "2026-09-01", "end": "2026-09-30"})))
    return FreeWheelClient.to_freewheel_plan(order)["insertion_order_body"]


def test_resolver_loads_regions():
    r = BrandResolver().load()
    assert {"SE", "NO", "DK", "USA"} <= set(r.regions())
    assert r.brands_for("SE"), "SE should have synced brands"


def test_pick_resolves_to_brand_id_on_io():
    r = BrandResolver().load()
    # pick a real SE brand name and confirm the IO carries its brand_id
    name = next(b for b in r.brands_for("SE") if "Viaplay (Promo)" in b)
    bid = r.resolve("SE", name)
    assert bid and bid.isdigit()
    assert _io_body("SE", "Partner - SE", io_brand=name).get("brand_id") == bid


def test_no_pick_leaves_brand_unset():
    assert "brand_id" not in _io_body("SE", "Partner - SE", io_brand=None)


def test_raw_brand_id_passes_through():
    assert BrandResolver().load().resolve("SE", "999999") == "999999"


def test_region_scoped_names():
    # A name is resolved within its region; an unknown name -> None (not cross-region).
    r = BrandResolver().load()
    assert r.resolve("SE", "definitely not a brand name") is None
