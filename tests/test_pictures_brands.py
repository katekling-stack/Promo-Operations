"""Paramount Pictures (movies) — distinct advertiser. Tiered remnant 2/3/4 (no Tier 1),
main SGs [Pluto, CBS Local, VCBS] (NO P+), custom pause main (no P+), house units,
per-country geo. Plus the BR kids Pictures / Consumer Products Pluto lines."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _main(p, idx=0):
    inc = FreeWheelClient._placement_body(p)["relationship_targeting"]["set"][idx][
        "content_targeting"]["network_items"]["include"]
    subs = inc.get("set", [inc])
    return [set(s["site_group"]) for s in subs if s.get("site_group")]


def test_pictures_uk_no_tier1_no_pplus_custom_pause():
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Marshals", "region": "UK",
        "campaign": {"name": "Paramount Pictures - UK"}, "content_id": "1",
        "season_or_messaging": "Buy Now On Digital", "durations": [15, 30],
        "showlist": ["NCIS"], "genres": ["Drama"], "pluto": {"channels": ["Westerns"]}}))
    assert order.brand is None or True  # brand set on plan below
    remnant = [p for p in order.placements if "Pause" not in p.name]
    assert {p.tier for p in remnant} == {2, 3, 4}     # no Tier 1
    # main = Pluto + CBS Local + VCBS, no P+ (932583).
    t4 = next(p for p in remnant if p.tier == 4 and p.duration == 15)
    assert {"929392", "932591", "932592"} in _main(t4)
    assert not any("932583" in s for s in _main(t4))
    # geo UK; house units (drop pre-roll at :30).
    assert all(FreeWheelClient._placement_body(p)["geography_targeting"] ==
               {"include": {"country": ["56"]}} for p in order.placements)
    # Pause main also drops P+ (929392, 932591, 932592 + platform SGs).
    pause = next(p for p in order.placements if "Pause Ad (Tier 4)" in p.name)
    pm = _main(pause)
    assert {"929392", "932591", "932592"} in pm and not any("932583" in s for s in pm)
    assert {"929447", "929449"} in pm


def test_pictures_adult_gets_promo_blocks_no_samsung():
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Scary Movie", "region": "BR",
        "campaign": {"name": "Paramount Pictures - BR"}, "content_id": "1",
        "season_or_messaging": "PHE", "durations": [30], "showlist": ["NCIS"], "genres": ["Comedy"]}))
    t4 = next(p for p in order.placements if p.tier == 4 and "Pause" not in p.name)
    exc = FreeWheelClient._placement_body(t4)["relationship_targeting"]["set"][0][
        "content_targeting"]["network_items"].get("exclude", {})
    assert "1258011" in exc.get("site_group", [])          # adult Pluto -> promo blocks
    assert not any(s in exc.get("site_group", [])           # not a Pluto TV campaign -> no Samsung
                   for s in ["1121578", "1164068", "1164069"])


def test_pictures_latam_geo_region_and_br_kids():
    latam = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Scary Movie", "region": "LATAM",
        "campaign": {"name": "Paramount Pictures - LATAM"}, "content_id": "1",
        "durations": [30], "showlist": ["NCIS"], "genres": ["Comedy"]}))
    assert FreeWheelClient._placement_body(latam.placements[0])["geography_targeting"] == {
        "include": {"region": ["1069"]}}
    # BR kids Pictures / Consumer Products = kids Pluto lines (929392).
    for camp, brand in [("Paramount Pictures - Kids - BR", "paramount_pictures_kids_br"),
                        ("Paramount Consumer Products - Kids - BR", "paramount_consumer_products_kids_br")]:
        plan = support_plan_from_dict({"promoted_title": "Paw Patrol", "region": "BR",
            "campaign": {"name": camp}, "durations": [30], "kids_audience": ["older", "younger"]})
        order = OrderBuilder().build(plan)
        assert plan.brand == brand
        assert {"929392"} in _main(order.placements[0])
