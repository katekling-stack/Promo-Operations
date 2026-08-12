"""House Pre-Roll is a SHORT-creative unit: it runs on :20/:15/:10-and-below and is dropped
at :30 and above (which then run House Mid-Roll + Post-Roll only). Applies across the board
— tiered, standard, and kids. Brand-specific pre-rolls (Viacom, INTL, Net10) are NOT dropped
by this rule; only the House Pre-Roll drops."""

from __future__ import annotations

from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

PRE = "Paramount House Preroll"
MID = "Paramount House Midroll"
POST = "Paramount House Postroll"


def _tier1_units(campaign, region, dur, **extra):
    base = dict(promoted_title="NCIS", region=region, campaign={"name": campaign},
                durations=[dur], showlist=["FBI"], pluto={"channels": ["Comedy"]})
    base.update(extra)
    o = OrderBuilder().build(support_plan_from_dict(base))
    for p in o.placements:
        if p.tier == 1:
            return p.ad_unit_names
    return o.placements[0].ad_unit_names


def test_short_creatives_get_house_preroll():
    for dur in (10, 15, 20):
        u = _tier1_units("Paramount + - USA", "USA", dur)
        assert PRE in u and MID in u and POST in u, (dur, u)


def test_thirty_and_above_drop_house_preroll():
    for dur in (30, 45, 60):
        u = _tier1_units("Paramount + - USA", "USA", dur)
        assert PRE not in u and MID in u and POST in u, (dur, u)


def test_pluto_usa_short_creative_has_preroll():
    # The reported bug: Pluto TV - USA :15 was missing the House Pre-Roll.
    u = _tier1_units("Pluto TV - USA", "USA", 15)
    assert PRE in u, u


def test_cbs_news_now_follows_the_rule():
    assert PRE in _tier1_units("CBS News - USA", "USA", 15)
    assert PRE not in _tier1_units("CBS News - USA", "USA", 30)


def test_mtve_viacom_preroll_kept_on_all_durations():
    # MTVE keeps its own Viacom pre-roll at every duration; only the House Pre-Roll is gated.
    short = _tier1_units("MTVE - USA", "USA", 15)
    long = _tier1_units("MTVE - USA", "USA", 30)
    assert any("Viacom_Promo_Pre_Roll" in n for n in short), short
    assert any("Viacom_Promo_Pre_Roll" in n for n in long), long


def test_standard_placements_follow_the_rule():
    short = _tier1_units("Pluto TV - USA", "USA", 15, standard=True)
    long = _tier1_units("Pluto TV - USA", "USA", 30, standard=True)
    assert PRE in short, short
    assert PRE not in long, long
