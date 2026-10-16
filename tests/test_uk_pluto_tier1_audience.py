"""UK P+ Pluto breakout lines: Tier 1 targets the SAME showlist-derived DDA audience segments as
the P+ line (constrained to the Pluto platform SG), instead of an empty audience set. Tier 2 on
the Pluto line stays channel-based (no showlist series)."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

PLUTO_SG = "929392"


def _order():
    return OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Zeta", "region": "UK", "campaign": {"name": "Paramount + - UK"},
        "content_type": "show", "content_id": "970005041", "recommended_show_id": "970005041",
        "durations": [30], "showlist": ["NCIS", "Tulsa King"], "genres": ["Comedy"],
        "product_overrides": {"pluto_breakout": True},
        "pluto": {"categories": ["Comedy"], "channels": ["Pluto TV Comedy Movies"]}}))


def _line(order, tier, pluto):
    return next(p for p in order.placements
                if p.tier == tier and p.duration == 30 and p.format.startswith("pplus_uk_remnant")
                and (("(Pluto)" in p.name) == pluto))


def _walk(node, key, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key and isinstance(v, list):
                out.update(map(str, v))
            else:
                _walk(v, key, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, key, out)


def _affinity_set(p):
    body = FreeWheelClient._placement_body(p)
    return next(s for s in body["relationship_targeting"]["set"] if s["set_name"] == "Affinity Shows")


def test_pluto_tier1_carries_the_showlist_audience_segments():
    order = _order()
    pplus_set, pluto_set = _affinity_set(_line(order, 1, False)), _affinity_set(_line(order, 1, True))
    pplus_ids = set(pplus_set["audience_targeting"]["include"]["audience_item"])
    pluto_ids = set(pluto_set["audience_targeting"]["include"]["audience_item"])
    assert pluto_ids, "Pluto Tier 1 must not be empty"
    assert pluto_ids == pplus_ids                    # same showlist -> same segments


def test_pluto_tier1_is_constrained_to_the_pluto_platform():
    sgs: set[str] = set()
    _walk(_affinity_set(_line(_order(), 1, True)).get("content_targeting"), "site_group", sgs)
    assert PLUTO_SG in sgs


def test_pluto_tier2_still_has_no_showlist_series():
    body = FreeWheelClient._placement_body(_line(_order(), 2, True))
    series: set[str] = set()
    _walk(body["relationship_targeting"], "series", series)
    # (the only series on this line would be a self-exclusion, never the showlist)
    assert not any(s["set_name"] == "Affinity Shows" and
                   _has_include_series(s) for s in body["relationship_targeting"]["set"])


def _has_include_series(s) -> bool:
    inc: set[str] = set()
    _walk((s.get("content_targeting") or {}).get("network_items", {}).get("include"), "series", inc)
    return bool(inc)
