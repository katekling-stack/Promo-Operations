"""Relationship-targeting structure — mirrors the Dutton Ranch IO."""

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import load_plan
from promo_ops.config import REPO_ROOT, relationship_targeting_config

FRISCO = str(REPO_ROOT / "plans" / "frisco-king-usa.yaml")
MAIN = relationship_targeting_config()["domestic_usa"]["main_site_groups"]


def _sets(placement):
    body = FreeWheelClient._placement_body(placement)
    return {s["set_name"]: s for s in body.get("relationship_targeting", {}).get("set", [])}


def _order(content_id=None):
    plan = load_plan(FRISCO)
    if content_id:
        plan.content_id = content_id
    return OrderBuilder().build(plan)


def test_main_sgs_anded_into_tier1_audience():
    order = _order()
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    s = _sets(t1)["Affinity Shows"]
    assert s["audience_targeting"]["include"]["audience_item"]          # DDA
    assert s["content_targeting"]["network_items"]["include"]["site_group"] == MAIN


def test_main_sgs_anded_with_series_in_tier2():
    order = _order()
    t2 = next(p for p in order.placements if p.tier == 2 and p.format == "remnant_video")
    inc = _sets(t2)["Affinity Shows"]["content_targeting"]["network_items"]["include"]
    kinds = {tuple(k for k in sub if k != "relation_in_set"): sub for sub in inc["set"]}
    assert kinds[("series",)]["series"]
    assert kinds[("site_group",)]["site_group"] == MAIN


def test_tier3_genre_uses_video_groups():
    order = _order()
    t3 = next(p for p in order.placements if p.tier == 3 and p.format == "remnant_video")
    inc = _sets(t3)["Genre"]["content_targeting"]["network_items"]["include"]
    vg = next(sub["video_group"] for sub in inc["set"] if "video_group" in sub)
    assert "74003240" in vg   # VG: Genre: Western
    assert "74003267" in vg   # VG: Genre: Crime


def test_recommended_show_key_value_when_content_id_present():
    order = _order(content_id="956609957")
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    rec = _sets(t1)["Recommended Show"]
    assert rec["custom_targeting"]["include"]["key_value"] == "recommended_show=956609957"


def test_pause_ads_have_no_pluto_and_platform_sgs():
    order = _order()
    pause2 = next(p for p in order.placements if p.format == "pause_ads" and p.tier == 2)
    s = _sets(pause2)
    assert "Channels" not in s and "Pluto Categories" not in s     # no Pluto on pause
    inc = s["Affinity Shows"]["content_targeting"]["network_items"]["include"]
    sgs = [sub["site_group"] for sub in inc["set"] if "site_group" in sub]
    assert ["929447", "929449"] in sgs                            # CTV + Desktop platforms


def test_guaranteed_has_genre_and_recommended_show():
    order = _order(content_id="956609957")
    prem = next(p for p in order.placements if p.format == "premium_preroll")
    s = _sets(prem)
    assert "Genre" in s and "Recommended Show" in s
    inc = s["Genre"]["content_targeting"]["network_items"]["include"]
    assert any("video_group" in sub for sub in inc["set"])         # genre VGs


def test_test_channels_excluded_from_pluto():
    order = _order()
    t2 = next(p for p in order.placements if p.tier == 2 and p.format == "remnant_video")
    channels = _sets(t2)["Channels"]["content_targeting"]["network_items"]["include"]["site_group"]
    # resolver drops any site group with a "Test" token in the name
    from promo_ops.site_groups import SiteGroupResolver
    r = SiteGroupResolver().load()
    names = {sg["id"]: sg["name"] for sg in
             r.select_all("", prefix="SG: PlutoTV Channels: US: ").site_groups}
    assert all("test" not in names.get(cid, "").lower() for cid in channels)
