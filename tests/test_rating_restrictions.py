"""Content-rating restrictions: a CM selects rating(s) to EXCLUDE; they resolve to the
market's "VG: Content Rating: {region}: {rating}" Video Groups and are excluded on every
placement in the order. Region-aware (USA ratings != GSA ratings). Raw VG ids pass through."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.ratings import RatingRestrictionResolver


def _excluded_vgs(order):
    vgs = set()
    for p in order.placements:
        if not p.tier:
            continue
        b = FreeWheelClient._placement_body(p)
        for s in b.get("relationship_targeting", {}).get("set", []):
            exc = (s.get("content_targeting") or {}).get("network_items", {}).get("exclude", {})
            vgs |= set(exc.get("video_group", []))
    return vgs


def _order(region, campaign, ratings):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region=region, campaign={"name": campaign},
        durations=[30], showlist=["FBI"], rating_restrictions=ratings)))


def test_resolver_top_level_and_resolve():
    r = RatingRestrictionResolver().load()
    us = r.ratings_for("US")
    assert "TV-MA" in us and "R" in us
    assert all(":" not in label for label in us)          # sub-variants hidden
    assert r.resolve("US", ["TV-MA", "TV-14"]) == ["877330305", "877330364"]


def test_us_tv_ma_excluded_on_every_placement():
    order = _order("USA", "Paramount + - USA", ["TV-MA"])
    assert "877330305" in _excluded_vgs(order)             # VG: Content Rating: US: TV-MA


def test_region_aware_resolution():
    # The SAME label resolves to the region's own VG; a US rating won't resolve under GSA.
    r = RatingRestrictionResolver().load()
    assert r.resolve("US", ["TV-MA"]) and not r.resolve("GSA", ["TV-MA"])
    assert r.resolve("GSA", ["18"])                        # GSA has its own "18"


def test_raw_vg_id_passes_through():
    r = RatingRestrictionResolver().load()
    assert r.resolve("USA", ["73408858"]) == ["73408858"]


def test_no_ratings_no_exclusion_change():
    order = _order("USA", "Paramount + - USA", [])
    assert "877330305" not in _excluded_vgs(order)
