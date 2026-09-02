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


def _order(region, campaign, ratings=None, includes=None):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region=region, campaign={"name": campaign},
        durations=[30], showlist=["FBI"], genres=["Drama"],
        rating_restrictions=ratings or [], rating_inclusions=includes or [])))


def _every_set_ands_vg(order, vg):
    """True iff `vg` appears as an AND-ed content include subset in every targeting set
    (and, for set-less flat lines, in the placement-level content include)."""
    seen_any = False
    for p in order.placements:
        if not p.tier:
            continue
        b = FreeWheelClient._placement_body(p)
        sets = b.get("relationship_targeting", {}).get("set", [])
        if sets:
            for s in sets:
                inc = (s.get("content_targeting") or {}).get("network_items", {}).get("include", {})
                subs = inc.get("set", [inc])
                if not any(vg in (x.get("video_group") or []) for x in subs):
                    return False
                seen_any = True
        else:
            inc = (b.get("content_targeting") or {}).get("include", {})
            subs = inc.get("set", [inc])
            if not any(vg in (x.get("video_group") or []) for x in subs):
                return False
            seen_any = True
    return seen_any


def test_resolver_top_level_and_resolve():
    r = RatingRestrictionResolver().load()
    us = r.ratings_for("US")
    assert "TV-MA" in us and "R" in us
    assert all(":" not in label for label in us)          # sub-variants hidden from the picker
    # Excluding a rating expands to its whole family (base + descriptor variants), so the
    # base VGs are always included; picking TV-MA also pulls in TV-MA: V, TV-MA: L, etc.
    resolved = r.resolve("US", ["TV-MA", "TV-14"])
    assert {"877330305", "877330364"}.issubset(set(resolved))
    assert len(resolved) >= 2


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


def test_short_rating_label_never_passes_through_as_vg_id():
    # A short all-digit label ("15"/"18") is a RATING, not a VG id — it must resolve to a real
    # VG id or be dropped, never emitted raw (which 422s "Asset Group item [15,18] doesn't exist").
    r = RatingRestrictionResolver().load()
    assert r.resolve("US", ["15", "18"]) == []              # US has no such labels -> dropped
    assert all(len(x) >= 5 for x in r.resolve("UK", ["15", "18"]))


def test_ie_ratings_alias_to_uk():
    # Ireland has no rating VGs of its own; it shares the UK/BBFC classification, so its
    # ratings resolve to the UK Content Rating VGs (real ids, never the raw "15"/"18").
    r = RatingRestrictionResolver().load()
    assert r.ratings_for("IE") == r.ratings_for("UK")
    ie = r.resolve("IE", ["15", "15+", "18", "18+"])
    assert ie == r.resolve("UK", ["15", "15+", "18", "18+"])
    assert ie and all(x.isdigit() and len(x) >= 5 for x in ie)


def test_no_ratings_no_exclusion_change():
    order = _order("USA", "Paramount + - USA", [])
    assert "877330305" not in _excluded_vgs(order)


def test_rating_include_anded_into_every_set():
    # Include TV-14: the TV-14 VG (877330364) is AND-ed into every argument.
    order = _order("USA", "Paramount + - USA", includes=["TV-14"])
    assert _every_set_ands_vg(order, "877330364")


def test_include_and_exclude_coexist():
    order = _order("USA", "Paramount + - USA", ratings=["TV-MA"], includes=["TV-14"])
    assert _every_set_ands_vg(order, "877330364")          # include AND-ed
    assert "877330305" in _excluded_vgs(order)             # exclude still applied


def test_include_region_aware():
    # GSA include resolves to a GSA rating VG; a US label does not resolve under GSA.
    r = RatingRestrictionResolver().load()
    assert r.resolve("GSA", ["18"]) and not r.resolve("GSA", ["TV-14"])


def test_include_respects_freewheel_3_set_cap():
    # FreeWheel rejects an advanced include with >3 AND-ed sets. Even on placements that
    # already have 3 sets (e.g. pause Tier 2 = series + 2 platform SGs), adding a rating
    # include must merge in rather than create a 4th set.
    order = _order("USA", "Paramount + - USA", ratings=["TV-MA"], includes=["TV-14"])
    for p in order.placements:
        if not p.tier:
            continue
        b = FreeWheelClient._placement_body(p)
        for s in b.get("relationship_targeting", {}).get("set", []):
            inc = (s.get("content_targeting") or {}).get("network_items", {}).get("include", {})
            subs = inc.get("set", [inc])
            assert len(subs) <= 3, (p.name, s.get("set_name"), len(subs))
    # and the include is still present everywhere despite the merge
    assert _every_set_ands_vg(order, "877330364")


def test_no_include_no_extra_and_subset():
    # Without an include, the genre set keeps its original 2-subset AND (SG + genre VG).
    order = _order("USA", "Paramount + - USA")
    p3 = next(p for p in order.placements if p.tier == 3 and not p.guaranteed)
    inc = (FreeWheelClient._placement_body(p3)["relationship_targeting"]["set"][0]
           ["content_targeting"]["network_items"]["include"])
    assert len(inc.get("set", [])) == 2
