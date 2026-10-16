"""FreeWheel returns a one-item collection as a bare object/string instead of a one-item list
(a single ad unit, a single relationship set, a single country or site group...). The auditor
must read both shapes identically -- reading a lone ad unit as "none" produced false
"NO ad units attached" errors on live bumpers, and a lone set read as "no sets"."""

from __future__ import annotations

import copy

from promo_ops.qa import PlacementView
from test_qa import AU_PLAN, _audit, _live


def collapse(node):
    """Mimic FreeWheel's JSON: any one-element list becomes the element itself."""
    if isinstance(node, dict):
        return {k: collapse(v) for k, v in node.items()}
    if isinstance(node, list):
        items = [collapse(x) for x in node]
        return items[0] if len(items) == 1 else items
    return node


def _signature(rep):
    return sorted((f.level, f.category, f.placement, f.message) for f in rep.findings)


def test_collapsed_single_items_audit_exactly_like_the_originals():
    io, pls = _live(AU_PLAN, "73850057")
    normal = _audit(io, pls)
    collapsed = _audit(io, [collapse(copy.deepcopy(p)) for p in pls])
    assert _signature(collapsed) == _signature(normal)
    assert not collapsed.by_level("error") and not collapsed.by_level("warn")


def test_the_individual_accessors_handle_both_shapes():
    io, pls = _live(AU_PLAN, "73850057")
    bumper = next(p for p in pls if "Bumper" in p["name"])
    raw = collapse(copy.deepcopy(bumper))
    pv, ref = PlacementView(raw), PlacementView(bumper)
    assert pv.ad_unit_ids() == ref.ad_unit_ids() and pv.ad_unit_ids()
    assert pv.set_names() == ref.set_names()
    assert pv.geo_country_ids() == ref.geo_country_ids() and pv.geo_country_ids()
    assert pv.all_site_groups("include") == ref.all_site_groups("include")


def test_a_lone_relationship_set_object_is_one_set():
    io, pls = _live(AU_PLAN, "73850057")
    t2 = next(p for p in pls if "(Tier 2)" in p["name"] and "relationship_targeting" in p)
    raw = copy.deepcopy(t2)
    only = raw["relationship_targeting"]["set"]
    raw["relationship_targeting"]["set"] = only[0] if len(only) == 1 else only
    assert PlacementView(raw).set_names() == PlacementView(t2).set_names()
