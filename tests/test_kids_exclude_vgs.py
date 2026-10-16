"""Kids audience exclusions: asking to target Younger Kids excludes VG 165056324 and asking to
target Older Kids excludes VG 165055190 -- on EVERY placement (every set, guaranteed lines too)
of EVERY kids brand in every region. Only the selected audience's VG is excluded, and adult
brands are never touched."""

from __future__ import annotations

import pytest

from promo_ops.config import brands_config, kids_exclude_video_groups, regions_config
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

YOUNGER_X = "165056324"
OLDER_X = "165055190"


def _excluded_on_every_placement(order, vg):
    """True iff `vg` is in the video-group exclude of every set of every placement (or the
    placement-level exclude for set-less flat lines). Returns (ok, offender_names)."""
    bad = []
    for p in order.placements:
        body = FreeWheelClient._placement_body(p)
        sets = (body.get("relationship_targeting") or {}).get("set", [])
        if sets:
            ok = all(vg in ((s.get("content_targeting") or {}).get("network_items", {})
                            .get("exclude") or {}).get("video_group", []) for s in sets)
        else:
            ok = vg in ((body.get("content_targeting") or {}).get("exclude") or {}).get("video_group", [])
        if not ok:
            bad.append(p.name)
    return not bad, bad


def _any_exclude(order, vg):
    for p in order.placements:
        if vg in str(FreeWheelClient._placement_body(p)):
            return True
    return False


def _kids_order(campaign, region, audience):
    return OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Kamp Koral", "region": region, "campaign": {"name": campaign},
        "durations": [30], "showlist": ["SpongeBob SquarePants"], "genres": ["Kids"],
        "kids_audience": audience, "content_type": "show", "content_id": "123"}))


def test_config_resolution():
    assert kids_exclude_video_groups(["younger"]) == [YOUNGER_X]
    assert kids_exclude_video_groups(["older"]) == [OLDER_X]
    assert set(kids_exclude_video_groups(["older", "younger"])) == {YOUNGER_X, OLDER_X}
    assert kids_exclude_video_groups([]) == [] and kids_exclude_video_groups(None) == []


def _kids_campaigns():
    regions = set(regions_config().get("regions", {}))
    out = []
    for key, cfg in brands_config()["brands"].items():
        if not cfg.get("kids"):
            continue
        name = str(cfg.get("campaign_name") or "")
        region = name.rsplit("-", 1)[-1].strip()
        if region in regions:
            out.append(pytest.param(name, region, id=key))
    return out


def test_every_kids_brand_is_covered_by_the_parametrization():
    assert len(_kids_campaigns()) >= 70        # guards against silently testing nothing


@pytest.mark.parametrize("campaign,region", _kids_campaigns())
def test_both_audiences_excluded_on_every_placement_of_every_kids_brand(campaign, region):
    order = _kids_order(campaign, region, ["older", "younger"])
    assert order.placements, campaign
    for vg in (YOUNGER_X, OLDER_X):
        ok, bad = _excluded_on_every_placement(order, vg)
        assert ok, (campaign, vg, bad[:3])


@pytest.mark.parametrize("audience,present,absent", [
    (["younger"], YOUNGER_X, OLDER_X),
    (["older"], OLDER_X, YOUNGER_X),
])
def test_only_the_selected_audiences_vg_is_excluded(audience, present, absent):
    order = _kids_order("Paramount + - Kids - FR", "FR", audience)
    assert _excluded_on_every_placement(order, present)[0]
    assert not _any_exclude(order, absent)


def test_adult_brands_are_never_touched():
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "NCIS", "region": "USA", "campaign": {"name": "Paramount + - USA"},
        "durations": [30], "showlist": ["FBI"], "genres": ["Drama"],
        "kids_audience": ["younger", "older"]}))
    assert not _any_exclude(order, YOUNGER_X) and not _any_exclude(order, OLDER_X)
