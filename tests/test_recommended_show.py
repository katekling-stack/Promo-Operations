"""Recommended Show argument:
  * P+ (and other non-Pluto adult): key "recommended_show" (singular), applied GLOBALLY.
  * Pluto TV: key "recommended_shows" (plural), applied DOMESTICALLY only (not rolled out
    internationally). Verified against live Pluto (recommended_shows=) and P+ placements."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _rec_show_kv(order):
    """Every custom_targeting key_value on the Recommended Show sets across the order."""
    kvs = []
    for p in order.placements:
        for s in FreeWheelClient._placement_body(p).get("relationship_targeting", {}).get("set", []):
            if s.get("set_name") == "Recommended Show":
                kvs.append(s["custom_targeting"]["include"]["key_value"])
    return kvs


def _order(**plan):
    return OrderBuilder().build(support_plan_from_dict(plan))


def test_pplus_uses_singular_recommended_show_globally():
    for region, campaign in [("USA", "Paramount + - USA"), ("LATAM", "Paramount + - LATAM"),
                             ("GSA", "Paramount + - GSA")]:
        order = _order(promoted_title="NCIS", region=region, campaign={"name": campaign},
                       durations=[30], showlist=["FBI"], recommended_show_id="956479957")
        kvs = _rec_show_kv(order)
        assert kvs, f"{region}: expected a Recommended Show set"
        assert all(kv.startswith("recommended_show=") for kv in kvs), f"{region}: {kvs}"


def test_pluto_uses_plural_recommended_shows_domestic_only():
    # Domestic Pluto: plural key present.
    dom = _order(promoted_title="NCIS", region="USA", campaign={"name": "Pluto TV - USA"},
                 durations=[30], pluto={"channels": ["Comedy"]}, recommended_show_id="abc123")
    kvs = _rec_show_kv(dom)
    assert kvs and all(kv.startswith("recommended_shows=") for kv in kvs), kvs
    # International Pluto: NO Recommended Show set at all (feature not rolled out globally).
    intl = _order(promoted_title="NCIS", region="LATAM", campaign={"name": "Pluto TV - LATAM"},
                  durations=[30], pluto={"channels": ["Comedy"]}, recommended_show_id="abc123")
    assert _rec_show_kv(intl) == []


def test_movie_gets_no_recommended_show_argument():
    """A Movie's id rides only in the placement name ([MovieID:…]) — never in the
    Recommended Show custom-targeting (that key is Show-ID only)."""
    show = _order(promoted_title="Frisco King", region="USA", campaign={"name": "Paramount + - USA"},
                  durations=[30], showlist=["FBI"], content_type="show", content_id="956479957")
    movie = _order(promoted_title="The Man In The White Van", region="USA",
                   campaign={"name": "Paramount + - USA"}, durations=[30], showlist=["FBI"],
                   content_type="movie", content_id="956479957")
    assert _rec_show_kv(show), "a Show should carry the Recommended Show argument"
    assert _rec_show_kv(movie) == [], "a Movie must NOT carry a Recommended Show argument"


def test_primary_trafficker_lands_on_the_io():
    order = _order(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                   durations=[30], showlist=["FBI"], primary_trafficker="Kate Kling")
    plan = FreeWheelClient.to_freewheel_plan(order)
    assert plan["insertion_order_body"].get("primary_trafficker") == "Kate Kling"
    # Absent when not provided (no empty field forced onto the IO).
    order2 = _order(promoted_title="NCIS", region="USA", campaign={"name": "Paramount + - USA"},
                    durations=[30], showlist=["FBI"])
    assert "primary_trafficker" not in FreeWheelClient.to_freewheel_plan(order2)["insertion_order_body"]
