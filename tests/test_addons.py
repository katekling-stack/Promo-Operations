"""Video Domination + Operative Takeover add-ons."""

from __future__ import annotations

from promo_ops.addons import build_addons
from promo_ops.plan_loader import support_plan_from_dict


def test_pluto_video_domination_freewheel_body():
    plan = support_plan_from_dict({
        "promoted_title": "Beverly Hills Cop", "region": "USA",
        "campaign": {"name": "Pluto TV - USA"}, "season_or_messaging": "Franchise",
        "video_domination": "pluto",
        "video_domination_targeting": ["True Crime", "Movies - Action"]})
    vd = build_addons(plan)["video_domination"]
    assert vd.engine == "freewheel"
    b = vd.freewheel_placement
    assert b["name"] == "Beverly Hills Cop - Franchise - Pluto Video Domination - USA"
    assert b["budget"]["budget_model"] == "ALL_IMPRESSION"
    assert b["override"] == {"precedence_level": "HIGHEST"}
    periods = {c["period"] for c in b["delivery"]["frequency_cap"]}
    assert periods == {"1440", "STREAM", "ASSET"}          # 1/day + 1/stream + 1/asset
    assert [n["ad_unit_id"] for n in b["ad_product"]["ad_unit_node"]] == ["71999", "72000"]
    cats = b["relationship_targeting"]["set"][0]["content_targeting"]["network_items"]["include"]["site_group"]
    assert cats and not vd.unresolved_categories       # resolved to Pluto category SGs


def test_operative_video_dominations():
    for opt, order_id in [("standard", "66933"), ("aus_10_streaming", "71779"),
                          ("uk_my5", "71842")]:
        plan = support_plan_from_dict({
            "promoted_title": "X", "region": "AU", "campaign": {"name": "Paramount + - AU"},
            "video_domination": opt})
        vd = build_addons(plan)["video_domination"]
        assert vd.engine == "operative" and vd.operative_order_id == order_id
        assert vd.operative_order_name and vd.freewheel_placement is None


def test_takeover_specs():
    # P+ order name gets the "P+ …" prefix; product lines + push advertiser resolve.
    plan = support_plan_from_dict({
        "promoted_title": "Frisco King", "region": "USA",
        "campaign": {"name": "Paramount + - USA"}, "takeover": "hpto",
        "flight": {"start": "2026-10-01", "end": "2026-10-07"}})
    tk = build_addons(plan)["takeover"]
    assert tk.type == "hpto" and tk.line_kind == "sponsorship"
    assert tk.operative_order_name.startswith("P+ HPTO - Frisco King")
    assert "2026-10-01 - 2026-10-07" in tk.operative_order_name
    assert len(tk.product_lines) == 5
    assert tk.gam_push_advertiser == "CBS Interactive"
    assert tk.booking_rules.get("push_quantity") == 100
    # 3-Peat is a standard line (different push rules).
    tp = build_addons(support_plan_from_dict({
        "promoted_title": "X", "region": "USA", "campaign": {"name": "CBS Sports - USA"},
        "takeover": "three_peat"}))["takeover"]
    assert tp.line_kind == "standard"
    assert tp.booking_rules.get("push_quantity_increase_pct") == 3


def test_booking_worksheet_renders_takeover_steps():
    from promo_ops.addons import render_booking_worksheet
    plan = support_plan_from_dict({
        "promoted_title": "Frisco King", "region": "USA",
        "campaign": {"name": "Paramount + - USA"}, "takeover": "hpto",
        "video_domination": "standard",
        "flight": {"start": "2026-10-01", "end": "2026-10-07"}})
    sheet = render_booking_worksheet(build_addons(plan))
    assert "TAKEOVER — Home Page Takeover" in sheet
    assert "Copy a similar Operative order" in sheet
    assert "Push All to GAM under advertiser “CBS Interactive”" in sheet
    assert "push quantity 100" in sheet                      # sponsorship rule
    # Operative VD copy step present too.
    assert "Copy Operative order 66933" in sheet


def test_booking_worksheet_empty_when_no_addons():
    from promo_ops.addons import render_booking_worksheet
    plan = support_plan_from_dict({"promoted_title": "X", "region": "USA",
                                   "campaign": {"name": "Paramount + - USA"}})
    assert "nothing to book" in render_booking_worksheet(build_addons(plan))


def test_no_addons_when_plan_has_none():
    plan = support_plan_from_dict({"promoted_title": "X", "region": "USA",
                                   "campaign": {"name": "Paramount + - USA"}})
    addons = build_addons(plan)
    assert addons["video_domination"] is None and addons["takeover"] is None
