"""Pluto En Español — remnant with brand-constant relationship sets (from live IOs)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(title: str, campaign: str):
    plan = support_plan_from_dict({
        "promoted_title": title, "region": "USA",
        "campaign": {"name": campaign}, "durations": [15, 30],
    })
    return plan, OrderBuilder().build(plan)


def _set_names(placement):
    body = FreeWheelClient._placement_body(placement)
    return [s.get("set_name") for s in body.get("relationship_targeting", {}).get("set", [])]


def test_pluto_es_adult_names_and_ad_units():
    plan, order = _order("Crímenes imperfectos", "Pluto TV - En Espanol - USA")
    assert plan.brand == "pluto_es_adult"
    assert [p.name for p in order.placements] == [
        "Crímenes imperfectos - Stream Ahora - 15 - Spanish - USA",
        "Crímenes imperfectos - Stream Ahora - 30 - Spanish - USA",
    ]
    assert set(order.placements[0].ad_unit_ids) == {"71999", "72000", "72001"}
    assert set(order.placements[1].ad_unit_ids) == {"72000", "72001"}
    assert all(p.geo_country_ids == ["165"] for p in order.placements)


def test_pluto_es_adult_relationship_sets():
    _, order = _order("Crímenes imperfectos", "Pluto TV - En Espanol - USA")
    p = order.placements[0]
    assert _set_names(p) == ["Targeting VOD", "En Espanol"]
    body = FreeWheelClient._placement_body(p)
    vod = body["relationship_targeting"]["set"][0]
    ni = vod["content_targeting"]["network_items"]
    subs = ni["include"]["set"]
    assert {"75279406"} == set(subs[0]["video_group"])
    assert {"1120870", "1253848"} == set(subs[1]["site_group"])
    assert set(ni["exclude"]["site_group"]) == {"932270", "932411", "932412"}


def test_pluto_es_kids_has_three_sets():
    _, order = _order("El Reino Infantil", "Pluto TV - Kids - En Espanol - USA")
    p = order.placements[0]
    assert _set_names(p) == ["Set One", "Set Two", "Kids Channels"]
    body = FreeWheelClient._placement_body(p)
    # Set Two carries both age VGs + base with the Kids content SG.
    set_two = body["relationship_targeting"]["set"][1]["content_targeting"]["network_items"]["include"]["set"]
    # the kids subset pairs the age VGs with the Kids content SG 932400
    kids_sub = next(s for s in set_two
                    if s.get("video_group") and "932400" in (s.get("site_group") or []))
    assert set(kids_sub["video_group"]) == {"73408862", "73408864", "86471529"}
