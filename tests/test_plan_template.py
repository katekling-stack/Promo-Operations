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
    # The lean template carries only the fields a planner fills; Brand, Formats,
    # Advertiser, IO name and recommended/exclude show are auto-derived (blank here)
    # and populated by _apply_defaults / the builder, not by the raw tab parse.
    plan = parse_plan_tab(_rows("Plan.csv"))
    assert plan["promoted_title"] == "Frisco King"
    assert plan["region"] == "USA"
    assert plan["campaign"]["name"] == "Paramount + - USA"
    assert plan["season_or_messaging"] == "Season 1"
    assert plan["durations"] == ["30", "15"]
    assert plan["content_type"] == "show"
    # Auto-derived overrides are intentionally absent from the lean template.
    assert "formats" not in plan
    assert "insertion_order_name" not in plan
    assert "recommended_show" not in plan
    assert "exclude_show" not in plan
    assert "brand" not in plan


def test_targeting_tab_parses_columns():
    plan = parse_targeting_tab(_rows("Targeting.csv"))
    assert plan["networks"] == ["Paramount Network"]
    assert len(plan["showlist"]) == 22
    assert plan.get("audience_segments", []) == []   # Tier 1 = DDA auto-resolved; AAM sunset
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
    # Brand + Formats (asserted above) are auto-derived from the Campaign by
    # _apply_defaults. recommended_show / exclude_show / insertion_order_name are
    # build-time defaults — blank on the lean sheet, filled by the builder — so they're
    # covered by test_template_builds_same_order rather than compared here.
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
