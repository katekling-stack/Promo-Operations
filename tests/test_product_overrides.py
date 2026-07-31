"""Products section toggles include/exclude products; blank = brand default."""

from __future__ import annotations

import csv

from promo_ops.config import REPO_ROOT
from promo_ops.integrations.gsheets import assemble_plan_template, parse_plan_tab
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.integrations.salesforce import build_plan_dict


def _plan(campaign: str, overrides: dict) -> list[str]:
    return support_plan_from_dict({
        "promoted_title": "T", "region": "USA",
        "campaign": {"name": campaign},
        "product_overrides": overrides,
    }).formats


def test_optout_drops_a_brand_default_product():
    assert "pause_ads" not in _plan("Paramount + - USA", {"pause_ads": False})
    # The rest of the P+ set survives.
    assert "remnant_video" in _plan("Paramount + - USA", {"pause_ads": False})


def test_blank_toggles_keep_brand_default():
    assert _plan("Paramount + - USA", {}) == [
        "remnant_video", "pause_ads", "premium_preroll", "essential_bumper"]


def test_bumper_family_optout_removes_brand_specific_bumper():
    assert "mtve_after_midroll_bumper" not in _plan("MTVE - USA",
                                                    {"after_midroll_bumper": False})


def test_optin_to_unsupported_product_is_ignored():
    # premium_preroll is a Paramount+ product; opting a CBS Sports plan into it
    # shouldn't fabricate it.
    assert _plan("CBS Sports - USA", {"premium_preroll": True}) == ["remnant_video"]


def test_pause_ads_is_universally_optional():
    # Pause Ads run across brands, so any campaign can opt in even when it isn't
    # part of the brand's default set (CBS Sports defaults to remnant_video only).
    assert _plan("CBS Sports - USA", {"pause_ads": True}) == ["remnant_video", "pause_ads"]


def test_plan_tab_parses_yes_no_toggles():
    rows = [
        ["Include Pause Ads", "No", "(Y/N)"],
        ["Include CBS Pre-Roll", "Yes", "(Y/N)"],
        ["Include 1Z Lockdown", "", "(Y/N)"],   # blank -> absent
    ]
    plan = parse_plan_tab(rows)
    assert plan["product_overrides"] == {"pause_ads": False, "cbs_preroll": True}


def test_salesforce_toggle_fields_coerce_to_bool():
    plan = build_plan_dict({
        "Promoted_Title__c": "T", "Region__c": "USA",
        "Campaign_Name__c": "Paramount + - USA",
        "Include_Pause_Ads__c": "No",
        "Include_Premium_Pre_Roll__c": "Yes",
    })
    assert plan["product_overrides"] == {"pause_ads": False, "premium_preroll": True}
