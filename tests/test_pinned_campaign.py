"""The parent campaign is pinned to the id in brands.yaml (template_campaign_id) at load
time — BEFORE any live name lookup — because two campaigns can share a name (e.g. an old
"Paramount + - USA" that hit FreeWheel's 500-IO cap and its replacement), and a name search
would pick the wrong one. Regression: pushes landed on the full 54026435 instead of 86543608."""

from __future__ import annotations

from promo_ops.config import pinned_campaign_id
from promo_ops.plan_loader import support_plan_from_dict


def test_pinned_campaign_id_from_config():
    assert pinned_campaign_id("Paramount + - USA") == "86543608"
    assert pinned_campaign_id("unknown campaign") is None
    assert pinned_campaign_id("") is None


def test_load_pins_campaign_resolved_id_by_name():
    plan = support_plan_from_dict(dict(
        promoted_title="The Program: Texas Tech", region="USA",
        campaign={"name": "Paramount + - USA"}, durations=[30], genres=["Drama"]))
    assert plan.campaign.get("resolved_id") == "86543608"


def test_explicit_resolved_id_is_not_overwritten():
    plan = support_plan_from_dict(dict(
        promoted_title="T", region="USA",
        campaign={"name": "Paramount + - USA", "resolved_id": "99999999"},
        durations=[30], genres=["Drama"]))
    assert plan.campaign.get("resolved_id") == "99999999"


def test_unpinned_campaign_left_alone():
    plan = support_plan_from_dict(dict(
        promoted_title="T", region="USA",
        campaign={"name": "Some Unpinned Campaign - ZZ"}, durations=[30], genres=["Drama"]))
    assert not plan.campaign.get("resolved_id")
