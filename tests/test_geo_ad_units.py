"""Geo (country) and ad-unit name -> FW ID resolution."""

from promo_ops.ad_units import AdUnitResolver
from promo_ops.geo import CountryResolver
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import load_plan
from promo_ops.config import REPO_ROOT


def test_country_resolves_united_states_to_165():
    r = CountryResolver().load()
    m = r.resolve("United States")
    assert m.matched and m.id == "165"


def test_country_resolution_is_case_insensitive():
    r = CountryResolver().load()
    assert r.resolve("united states").id == "165"
    assert r.resolve("Canada").id == "27"
    assert r.resolve("Australia").id == "10"
    assert r.resolve("Brazil").id == "21"


def test_unknown_country_is_reported_not_guessed():
    r = CountryResolver().load()
    m = r.resolve("Wakanda")
    assert not m.matched and m.id is None


def test_ad_units_resolve_paramount_house_and_pause():
    r = AdUnitResolver().load()
    assert r.resolve("Paramount House Preroll").id == "71999"
    assert r.resolve("Paramount House Midroll").id == "72000"
    assert r.resolve("Paramount House Postroll").id == "72001"
    assert r.resolve("Pause_Ad").id == "63413"


def test_order_builder_populates_geo_and_ad_unit_ids():
    plan = load_plan(str(REPO_ROOT / "plans" / "frisco-king-usa.yaml"))
    order = OrderBuilder().build(plan)
    video = next(p for p in order.placements if p.format == "remnant_video")
    assert video.geo_country_names == ["United States"]
    assert video.geo_country_ids == ["165"]
    assert video.ad_unit_ids == ["71999", "72000", "72001"]
    pause = next(p for p in order.placements if p.format == "pause_ads")
    assert pause.ad_unit_ids == ["63413"]
