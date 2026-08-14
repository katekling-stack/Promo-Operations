"""Sub-country geo overlay: a CM narrows a buy to specific states / Nielsen DMAs / cities
on top of the region's country targeting. Names resolve to FreeWheel geo IDs (region-scoped,
data/geo/*.csv) and land in geography_targeting.include.{state,dma,city}. Country base is kept."""

from __future__ import annotations

import pytest

from promo_ops.geo import GeoResolver
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(region="USA", campaign="Paramount + - USA", **geo):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region=region, campaign={"name": campaign},
        durations=[30], showlist=["FBI"], genres=["Drama"], **geo)))


def _geo_include(order):
    """Merge geography_targeting.include across all placements."""
    inc: dict = {}
    for p in order.placements:
        g = FreeWheelClient._placement_body(p).get("geography_targeting", {}).get("include", {})
        for k, v in g.items():
            inc.setdefault(k, set()).update(v if isinstance(v, list) else [v])
    return inc


# -- resolver ---------------------------------------------------------------------

def test_state_resolves_by_code_and_name_region_scoped():
    g = GeoResolver().load()
    us = GeoResolver.isos_for_countries(["United States"])
    assert g.resolve_states(us, ["CA"])[0].id == g.resolve_states(us, ["California"])[0].id
    assert g.resolve_states(us, ["CA"])[0].matched


def test_state_scope_rejects_out_of_region():
    g = GeoResolver().load()
    # A US state code should not resolve when the region's ISO set is Germany.
    de = GeoResolver.isos_for_countries(["Germany"])
    assert not g.resolve_states(de, ["California"])[0].matched


def test_dma_by_number_and_name():
    g = GeoResolver().load()
    by_num = g.resolve_dmas(["501"])[0]
    by_name = g.resolve_dmas(["New York, NY"])[0]
    assert by_num.matched and by_num.id == by_name.id


def test_city_requires_state_qualifier_and_resolves():
    g = GeoResolver().load()
    us = GeoResolver.isos_for_countries(["United States"])
    assert not g.resolve_cities(us, ["Springfield"])[0].matched     # ambiguous, no ST
    m = g.resolve_cities(us, ["New York, NY"])[0]
    assert m.matched and m.id.isdigit()


def test_raw_ids_pass_through():
    g = GeoResolver().load()
    assert g.resolve_states(["US"], ["12345"])[0].id == "12345"
    assert g.resolve_cities(["US"], ["99999"])[0].id == "99999"


# -- end to end through the placement body ----------------------------------------

def test_state_overlay_on_every_placement_keeps_country():
    order = _order(geo_states=["CA", "NY"])
    inc = _geo_include(order)
    assert inc.get("country") == {"165"}                 # US country base retained
    ca = GeoResolver().load().resolve_states(["US"], ["CA"])[0].id
    assert ca in inc.get("state", set())


def test_dma_overlay():
    inc = _geo_include(_order(geo_dmas=["501"]))
    assert inc.get("dma")


def test_city_overlay():
    inc = _geo_include(_order(geo_cities=["New York, NY"]))
    assert inc.get("city")


def test_no_overlay_is_country_only():
    inc = _geo_include(_order())
    assert set(inc) == {"country"}


def test_unresolvable_geo_raises():
    with pytest.raises(ValueError):
        _order(geo_states=["Nowhereland"])
