"""Mirroring a plan to another market swaps region + campaign, keeps the creative."""

from __future__ import annotations

import pytest

from promo_ops import mirror
from promo_ops.plan_loader import support_plan_from_dict, validate_plan


def _source():
    return {
        "promoted_title": "Frisco King", "region": "FR",
        "campaign": {"name": "Paramount + - FR"},
        "season_or_messaging": "Season 1", "durations": [30, 15],
        "genres": ["Drama"], "showlist": ["NCIS"],
        "product_overrides": {"pause_ads": True},
        "brand": "paramount_plus_fr", "insertion_order_name": "Frisco King - FR",
    }


def test_equivalent_campaign_same_family_other_region():
    assert mirror.equivalent_campaign("Paramount + - FR", "GSA") == "Paramount + - GSA"
    assert mirror.equivalent_campaign("Paramount + - FR", "IT") == "Paramount + - IT"
    # Kids-ness is part of the identity: an adult source maps to an adult target.
    assert mirror.equivalent_campaign("Paramount + - Kids - FR", "IT") == "Paramount + - Kids  - IT"


def test_equivalent_campaign_none_when_market_lacks_brand():
    # CBS Sports only exists for USA — no FR equivalent.
    assert mirror.equivalent_campaign("CBS Sports - USA", "FR") is None


def test_mirror_plan_swaps_region_and_campaign_keeps_creative():
    out = mirror.mirror_plan(_source(), "GSA")
    assert out["region"] == "GSA"
    assert out["campaign"] == {"name": "Paramount + - GSA"}
    # Creative + targeting carry over.
    assert out["promoted_title"] == "Frisco King"
    assert out["genres"] == ["Drama"] and out["showlist"] == ["NCIS"]
    assert out["product_overrides"] == {"pause_ads": True}
    # Source-specific identity is dropped so it re-derives for the target.
    assert "brand" not in out and "insertion_order_name" not in out
    # The mirrored plan is a valid, buildable plan for the target market.
    plan = support_plan_from_dict(out)
    assert plan.region == "GSA"
    assert validate_plan(plan) == []


def test_mirror_plan_raises_without_equivalent():
    src = {"promoted_title": "T", "region": "USA", "campaign": {"name": "CBS Sports - USA"}}
    with pytest.raises(ValueError):
        mirror.mirror_plan(src, "FR")


def test_mirror_to_markets_reports_skips():
    res = mirror.mirror_to_markets(_source(), ["GSA", "IT", "NO"])
    assert set(res["plans"]) == {"GSA", "IT"}          # NO (Nordics) has no P+ adult brand
    assert "NO" in res["skipped"]
