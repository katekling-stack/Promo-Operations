"""Channel 5 (My5) targeting: 5 - UK / 5 - Kids - UK target My5 endpoints. The CM-selected
My5 Site Groups (My5 Inventory field) are AND-ed into every tier; empty falls back to the
brand default (Adults: VOD; Kids: VOD + Milkshake). Placements are named "(My5)" and keep
pre/mid/post at all durations, Tiers 1-4 for adults."""

from __future__ import annotations

import json

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

VOD = "1225051"          # SG: Stream Type: VOD: My5
LIVE = "1247996"         # SG: Stream Type: Live: My5
MTV_OWNED = "1273285"    # SG: My5 Channels: UK: MTV Owned
NON_MTV = "1273286"      # SG: My5 Channels: UK: Non-MTV Owned
MILKSHAKE = "1248019"    # SG: My5 Channels: UK: Milkshake


def _sgs(order):
    ids = set()
    for p in order.placements:
        js = json.dumps(FreeWheelClient._placement_body(p))
        for token in (VOD, LIVE, MTV_OWNED, NON_MTV, MILKSHAKE, "929392"):
            if f'"{token}"' in js:
                ids.add(token)
    return ids


def _adult(**kw):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="T", region="UK", campaign={"name": "5 - UK"},
        durations=[20, 30], genres=["Sports"], **kw)))


def test_adult_defaults_to_my5_vod_tiers_1_to_4():
    o = _adult()
    assert len(o.placements) == 6                       # Tiers 1-4 (T3/T4 per duration)
    tiers = {p.tier for p in o.placements}
    assert tiers == {1, 2, 3, 4}
    assert _sgs(o) == {VOD}                              # default VOD, and NOT the old 929392
    assert all("(My5)" in p.name for p in o.placements)  # named "(Tier N) (My5) - UK"


def test_adult_explicit_my5_selection_is_anded_in():
    o = _adult(my5_site_groups=["SG: Stream Type: Live: My5", "SG: My5 Channels: UK: MTV Owned"])
    assert _sgs(o) == {LIVE, MTV_OWNED}


def test_adult_pre_mid_post_on_every_duration():
    o = _adult()
    for p in o.placements:
        names = " ".join(p.ad_unit_names).lower()
        assert "preroll" in names and "midroll" in names and "postroll" in names


def test_kids_defaults_to_my5_vod_plus_milkshake():
    o = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="SpongeBob", region="UK", campaign={"name": "5 - Kids - UK"},
        durations=[20, 30], kids_audience=["older", "younger"])))
    assert o.placements
    got = _sgs(o)
    assert VOD in got and MILKSHAKE in got              # My5 kids inventory layered in
    assert "929392" not in got                          # not the generic VCBS platform
    assert all("(My5)" in p.name for p in o.placements)
