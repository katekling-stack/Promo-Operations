"""Salesforce hybrid Case -> plan dict (design-first; no live Salesforce)."""

import csv

from promo_ops.integrations.salesforce import build_plan_dict
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.config import REPO_ROOT

# Core fields as they'd arrive on the Case record (hybrid: core on Case).
CASE_FIELDS = {
    "Id": "500XX000000Frisco",
    "Promoted_Title__c": "Frisco King",
    "Region__c": "USA",
    "Advertiser__c": "VCBS English - USA - Adult (Promo)",
    "Advertiser_ID__c": "1000520",
    "Campaign_Name__c": "Paramount + - USA",
    "Campaign_ID__c": "86543608",
    "Insertion_Order_Name__c": "Frisco King - USA",
    "Season_or_Messaging__c": "Season 1",
    "Video_Durations__c": "30; 15",
    "Content_Type__c": "show",
    "Recommended_Show_ID__c": "956609957",
    "Formats__c": "remnant_video; pause_ads; premium_preroll; essential_bumper",
    "Flight_Start__c": "2026-10-01",
    "Flight_End__c": "2026-12-31",
}


def _targeting_rows():
    path = REPO_ROOT / "templates" / "campaign-plan" / "Targeting.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_case_core_fields_map_into_plan():
    plan = build_plan_dict(CASE_FIELDS)
    assert plan["promoted_title"] == "Frisco King"
    assert plan["advertiser"] == {"name": "VCBS English - USA - Adult (Promo)",
                                  "resolved_id": "1000520"}
    assert plan["campaign"]["resolved_id"] == "86543608"
    assert plan["durations"] == ["30", "15"]
    assert plan["formats"] == ["remnant_video", "pause_ads",
                               "premium_preroll", "essential_bumper"]
    assert plan["flight"] == {"start": "2026-10-01", "end": "2026-12-31"}
    assert plan["recommended_show_id"] == "956609957"
    assert plan["salesforce_case"] == "500XX000000Frisco"


def test_attached_targeting_sheet_merges_in():
    plan = build_plan_dict(CASE_FIELDS, _targeting_rows())
    assert plan["networks"] == ["Paramount Network"]
    assert len(plan["showlist"]) == 22
    assert plan["pluto"]["categories"][0] == "True Crime"
    assert "CBS Sports HQ" in plan["pluto"]["channels"]


def test_case_builds_full_order():
    plan = support_plan_from_dict(build_plan_dict(CASE_FIELDS, _targeting_rows()))
    order = OrderBuilder().build(plan)
    assert len(order.placements) == 14           # 8 video + 4 pause + 2 Plan
    # Recommended Show ID from the Case drives the key-value.
    t1 = next(p for p in order.placements if p.tier == 1 and p.format == "remnant_video")
    assert t1.recommended_show_value == "956609957"
