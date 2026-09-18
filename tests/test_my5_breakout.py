"""Optional My5 (Channel 5) breakout for non-My5 UK brands (Paramount+ UK, MTVE UK).

Off by default; the "My5 breakout" product (product_overrides.my5_breakout) opts in a tiered
My5 remnant (`my5_remnant`) that runs on the CM-selected My5 inventory instead of P+/Pluto —
mirroring the dedicated "5 - UK" campaign's lines: (My5) name infix, pre/mid/post on every
duration. The P+ Recommended Show (a Paramount+ feature) must NOT ride on these Pluto-/My5-only
breakout lines.
"""

from __future__ import annotations

import json

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

VOD = "1225051"          # SG: Stream Type: VOD: My5 (the my5_remnant default)
LIVE = "1247996"         # SG: Stream Type: Live: My5


def _order(campaign, *, my5=None, **overrides):
    po = {"my5_breakout": True} if my5 is not False else {}
    if my5 is False:
        po = {}
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="Frasier", region="UK", campaign={"name": campaign},
        durations=[15, 30], genres=["Comedy"], showlist=["Cheers"],
        recommended_show_id="970002006", content_type="show",
        product_overrides=po, **overrides)))


@pytest.mark.parametrize("campaign", ["Paramount + - UK", "MTVE - UK"])
def test_my5_breakout_off_by_default(campaign):
    order = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="Frasier", region="UK", campaign={"name": campaign},
        durations=[30], genres=["Comedy"])))
    assert not [p for p in order.placements if p.format == "my5_remnant"]


@pytest.mark.parametrize("campaign", ["Paramount + - UK", "MTVE - UK"])
def test_my5_breakout_builds_tiers_1_4_on_my5_inventory(campaign):
    order = _order(campaign)
    my5 = [p for p in order.placements if p.format == "my5_remnant"]
    assert my5, "expected My5 breakout placements"
    assert sorted({p.tier for p in my5}) == [1, 2, 3, 4]
    # Every My5 line runs on the My5 platform and carries the (My5) name infix.
    assert all(p.platforms == ["My5"] for p in my5)
    assert all("(My5)" in p.name for p in my5)
    # Default My5 inventory (VOD) is AND-ed into every tier; never the Pluto SG.
    for p in my5:
        js = json.dumps(FreeWheelClient._placement_body(p))
        assert f'"{VOD}"' in js
        assert '"929392"' not in js


def test_my5_breakout_explicit_selection_is_used():
    order = _order("Paramount + - UK", my5_site_groups=["SG: Stream Type: Live: My5"])
    my5 = [p for p in order.placements if p.format == "my5_remnant"]
    for p in my5:
        js = json.dumps(FreeWheelClient._placement_body(p))
        assert f'"{LIVE}"' in js and f'"{VOD}"' not in js


def test_my5_breakout_has_no_pplus_recommended_show():
    order = _order("Paramount + - UK")
    my5 = [p for p in order.placements if p.format == "my5_remnant"]
    for p in my5:
        body = FreeWheelClient._placement_body(p)
        names = [s.get("set_name") for s in (body.get("relationship_targeting") or {}).get("set", [])]
        assert "Recommended Show" not in names, (p.name, names)


def test_my5_breakout_coexists_with_normal_pplus_lines():
    # Opting into My5 must NOT drop the campaign's usual P+ lines, and the P+ Tier 1 keeps
    # its Recommended Show.
    order = _order("Paramount + - UK")
    pplus = [p for p in order.placements if p.format == "pplus_uk_remnant_pplus"]
    assert pplus, "normal P+ lines should still be built"
    t1 = [p for p in pplus if p.tier == 1]
    body = FreeWheelClient._placement_body(t1[0])
    names = [s.get("set_name") for s in (body.get("relationship_targeting") or {}).get("set", [])]
    assert "Recommended Show" in names
