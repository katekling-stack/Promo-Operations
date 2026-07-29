"""SG: Custom: Brazil and LATAM Paramount Promo Blocks (1258011) is excluded on every
ADULT placement running on Pluto (Pluto SG in its main), across all tiers + standard
lines — EXCEPT the Pluto TV - BR / Pluto TV - LATAM campaigns. Not on kids or on the
guaranteed P+ lines (which don't run on Pluto)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

BLOCK = "1258011"


def _has_block(p):
    body = FreeWheelClient._placement_body(p)
    if any(BLOCK in s.get("content_targeting", {}).get("network_items", {})
           .get("exclude", {}).get("site_group", [])
           for s in body.get("relationship_targeting", {}).get("set", [])):
        return True
    return BLOCK in body.get("content_targeting", {}).get("exclude", {}).get("site_group", [])


def _order(region, campaign, **extra):
    base = {"promoted_title": "X", "region": region, "campaign": {"name": campaign},
            "durations": [30]}
    return OrderBuilder().build(support_plan_from_dict({**base, **extra}))


def test_block_on_adult_pluto_tiers_all():
    # Every adult remnant tier (1-4) on a Pluto-running brand carries the block.
    order = _order("LATAM", "Paramount + - LATAM", content_id="1",
                   showlist=["NCIS"], genres=["Drama"])
    remnant = [p for p in order.placements if not p.guaranteed]
    assert remnant and all(_has_block(p) for p in remnant)
    assert {p.tier for p in remnant} == {1, 2, 3, 4}
    # Guaranteed P+ lines run on P+ only -> no block.
    assert all(not _has_block(p) for p in order.placements if p.guaranteed)


def test_block_on_domestic_and_us_pluto():
    # Domestic brands rely on the default main (incl Pluto) -> block applies.
    dom = _order("USA", "Paramount + - USA", content_id="1", showlist=["NCIS"], genres=["Drama"])
    assert all(_has_block(p) for p in dom.placements if not p.guaranteed)
    us_pluto = _order("USA", "Pluto TV - USA", pluto={"channels": ["Comedy"]})
    assert all(_has_block(p) for p in us_pluto.placements)


def test_block_excepted_on_br_latam_pluto_campaigns():
    for region, campaign in [("LATAM", "Pluto TV - LATAM"), ("BR", "Pluto TV - BR")]:
        order = _order(region, campaign, pluto={"channels": ["Comedy"]})
        assert all(not _has_block(p) for p in order.placements), campaign


def test_block_not_on_kids_or_no_pluto_regions():
    kids = _order("BR", "Paramount + - Kids - BR", content_id="1", kids_audience=["older"])
    assert all(not _has_block(p) for p in kids.placements)
    au = _order("AU", "Paramount + - AU", content_id="1", showlist=["NCIS"], genres=["Drama"])
    assert all(not _has_block(p) for p in au.placements)   # AU has no Pluto
