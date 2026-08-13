"""Partner - {NO/DK/SE}: Viaplay-style promo partner brand, Pluto TV ONLY. Tiered remnant
1-4 (Tier 1 audience included), House ad units with Pre-roll on :20 and under (dropped at
:30+, leaving Mid/Post-roll). Mirrors the live Partner IOs (DK IO 96141616, SE IO 81464925)."""

from __future__ import annotations

import pytest

from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

PREROLL, MIDROLL, POSTROLL = "71999", "72000", "72001"


def _order(region, campaign, durations):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="Sex and the City", region=region, campaign={"name": campaign},
        durations=durations, showlist=["FBI"], genres=["Drama"])))


@pytest.mark.parametrize("region,campaign", [
    ("DK", "Partner - DK"), ("NO", "Partner - NO"), ("SE", "Partner - SE")])
def test_partner_builds_tiers_1_4_pluto_only(region, campaign):
    order = _order(region, campaign, [15, 30])
    remnant = [p for p in order.placements if p.tier]
    # Tier 1 included (audience) through Tier 4.
    assert sorted({p.tier for p in remnant}) == [1, 2, 3, 4]
    # Pluto TV only — every tier's main site group is the Pluto SG, nothing else.
    assert all(p.main_site_groups == ["929392"] for p in remnant)


@pytest.mark.parametrize("region,campaign", [
    ("DK", "Partner - DK"), ("NO", "Partner - NO"), ("SE", "Partner - SE")])
def test_partner_preroll_under_20_midpost_30_plus(region, campaign):
    order = _order(region, campaign, [15, 20, 30, 45])
    for p in order.placements:
        if not p.tier:
            continue
        units = set(p.ad_unit_ids)
        if p.duration <= 20:
            assert PREROLL in units, (p.name, p.duration, p.ad_unit_ids)   # pre-roll on :20 and under
        else:
            assert PREROLL not in units, (p.name, p.duration, p.ad_unit_ids)  # dropped at :30+
        assert {MIDROLL, POSTROLL} <= units                                # mid/post-roll always
