"""The campaign-plan sheet template must round-trip to the same plan as the YAML."""

from __future__ import annotations

import csv
from pathlib import Path

from promo_ops.integrations.gsheets import (
    assemble_plan_template,
    parse_plan_tab,
    parse_targeting_tab,
)
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import load_plan, support_plan_from_dict

TEMPLATE_DIR = Path("templates/campaign-plan")


def _rows(name: str) -> list[list[str]]:
    with (TEMPLATE_DIR / name).open(encoding="utf-8", newline="") as fh:
        return [row for row in csv.reader(fh)]


def test_plan_tab_parses_scalars_and_lists():
    plan = parse_plan_tab(_rows("Plan.csv"))
    assert plan["promoted_title"] == "Frisco King"
    assert plan["region"] == "USA"
    assert plan["formats"] == ["remnant_video", "pause_ads", "premium_preroll", "essential_bumper"]
    assert plan["campaign"]["name"] == "Paramount + - USA"
    assert plan["insertion_order_name"] == "Frisco King - USA"
    assert plan["recommended_show"] == "Frisco King"
    assert plan["exclude_show"] == "Frisco King"
    assert plan["campaign"]["clone_from_template"] is True
    assert plan["advertiser"]["name_contains"] == ["VCBS"]


def test_targeting_tab_parses_columns():
    plan = parse_targeting_tab(_rows("Targeting.csv"))
    assert plan["networks"] == ["Paramount Network"]
    assert len(plan["showlist"]) == 22
    assert plan["audience_segments"] == ["High Stakes Drama Fans", "Procedural Drama Fans"]
    assert plan["pluto"]["categories"][0] == "True Crime"
    assert "CBS Sports HQ" in plan["pluto"]["channels"]


def test_template_roundtrips_to_yaml_plan():
    sheet_dict = assemble_plan_template(_rows("Plan.csv"), _rows("Targeting.csv"))
    sheet_plan = support_plan_from_dict(sheet_dict)
    yaml_plan = load_plan("plans/frisco-king-usa.yaml")

    assert sheet_plan.promoted_title == yaml_plan.promoted_title
    assert sheet_plan.region == yaml_plan.region
    assert sheet_plan.brand == yaml_plan.brand
    assert sheet_plan.formats == yaml_plan.formats
    assert sheet_plan.showlist == yaml_plan.showlist
    assert sheet_plan.genres == yaml_plan.genres
    assert sheet_plan.networks == yaml_plan.networks
    assert sheet_plan.pluto_channels == yaml_plan.pluto_channels
    assert sheet_plan.pluto_categories == yaml_plan.pluto_categories
    assert sheet_plan.audience_segments == yaml_plan.audience_segments
    assert sheet_plan.recommended_show == yaml_plan.recommended_show
    assert sheet_plan.exclude_show == yaml_plan.exclude_show
    assert sheet_plan.insertion_order_name == yaml_plan.insertion_order_name
    assert sheet_plan.season_or_messaging == yaml_plan.season_or_messaging
    assert sheet_plan.durations == yaml_plan.durations
    assert sheet_plan.content_type == yaml_plan.content_type


def test_template_builds_same_order():
    sheet_dict = assemble_plan_template(_rows("Plan.csv"), _rows("Targeting.csv"))
    order_from_sheet = OrderBuilder().build(support_plan_from_dict(sheet_dict))
    order_from_yaml = OrderBuilder().build(load_plan("plans/frisco-king-usa.yaml"))
    assert order_from_sheet.name == order_from_yaml.name
    assert [p.name for p in order_from_sheet.placements] == \
           [p.name for p in order_from_yaml.placements]
