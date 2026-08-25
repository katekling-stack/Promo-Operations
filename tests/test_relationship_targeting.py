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


def test_pause_key_value_excludes_are_region_scoped():
    """Domestic (US) pause sets use the short custom key-value exclude list; all
    international regions use the fuller one."""
    from promo_ops.plan_loader import support_plan_from_dict

    def _pause_kv(region, campaign):
        plan = support_plan_from_dict({
            "promoted_title": "X", "region": region, "campaign": {"name": campaign},
            "formats": ["pause_ads"], "durations": [30],
            "showlist": ["NCIS"], "genres": ["Drama"],
        })
        order = OrderBuilder().build(plan)
        p = next(pp for pp in order.placements if "Pause Ad (Tier 4)" in pp.name)
        body = FreeWheelClient._placement_body(p)
        return set(body["relationship_targeting"]["set"][0]["custom_targeting"]
                   ["exclude"]["key_value"])

    assert _pause_kv("USA", "Paramount + - USA") == {"sb=14", "tsb=14", "tve=14", "tve=17"}
    assert _pause_kv("IE", "Paramount + - IE") == {
        "sb=14", "sb=17", "tsb=14", "tsb=17",
        "tve=14", "tve=15", "tve=17", "tve=24", "tve=25"}


def test_recommended_show_key_value_when_content_id_present():
    order = _order(content_id="956609957")
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    rec = _sets(t1)["Recommended Show"]
    assert rec["custom_targeting"]["include"]["key_value"] == "recommended_show=956609957"


def test_recommended_show_id_field_drives_key_value():
    # Dedicated "Recommended Show ID" plan field feeds the key-value (over Content ID).
    plan = load_plan(FRISCO)
    plan.recommended_show_id = "12345"
    order = OrderBuilder().build(plan)
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    rec = _sets(t1)["Recommended Show"]
    assert rec["custom_targeting"]["include"]["key_value"] == "recommended_show=12345"


def test_pause_ads_have_no_pluto_and_platform_sgs():
    order = _order()
    pause2 = next(p for p in order.placements if p.format == "pause_ads" and p.tier == 2)
    s = _sets(pause2)
    assert "Channels" not in s and "Pluto Categories" not in s     # no Pluto on pause
    inc = s["Affinity Shows"]["content_targeting"]["network_items"]["include"]
    sgs = [sub["site_group"] for sub in inc["set"] if "site_group" in sub]
    assert ["929447", "929449"] in sgs                            # CTV + Desktop platforms


def test_guaranteed_plan_lines_carry_tier1_audience_and_recommended_show():
    # P+ adult Plan placements now carry Tier 1 targeting: an Affinity Shows set with the DDA
    # audience segments (from the showlist) + a Recommended Show — replacing the old Genre.
    order = _order(content_id="956609957")
    PPLUS = relationship_targeting_config()["domestic_usa"]["pplus_site_group"]
    for fmt in ("premium_preroll", "essential_bumper"):
        p = next(p for p in order.placements if p.format == fmt)
        s = _sets(p)
        assert set(s) == {"Affinity Shows", "Recommended Show"}, fmt
        assert "Genre" not in s
        aff = s["Affinity Shows"]
        assert aff["audience_targeting"]["include"]["audience_item"]           # DDA segments
        inc = aff["content_targeting"]["network_items"]["include"]
        assert inc["site_group"] == PPLUS                                      # P+ platform SG
        assert "series" not in inc                                             # no showlist series


def test_recommended_show_prebuilt_with_placeholder_when_blank():
    # Blank Content ID / Recommended Show ID -> scaffolded with the placeholder.
    order = _order()   # Frisco plan: no content_id
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    kv = _sets(t1)["Recommended Show"]["custom_targeting"]["include"]["key_value"]
    assert kv == "recommended_show=TBD"


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
