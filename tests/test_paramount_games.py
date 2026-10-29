"""Campaign 'Paramount Games - USA' (FreeWheel campaign 95537948): tiered video lines + Pause Ads, built like
the other US promo brands. Matches its live reference IO (Avatar Legends: The Fighting Game - USA, 95537959):
standard US priorities, ad units 71999/72000/72001 on :15 lines, Pause Ad unit 63413, 1 per 30 min."""

from __future__ import annotations

import importlib.util
import sys

from promo_ops.config import REPO_ROOT, brand_for_campaign, brands_config
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

PLAN = {"promoted_title": "Top Gun: Battlefield", "region": "USA", "campaign": {"name": "Paramount Games - USA"},
        "durations": [15, 30], "genres": ["Action"], "flight": {"start": "2026-11-01", "end": "2026-12-01"},
        "product_overrides": {"pause_ads": True}}


def test_the_campaign_is_configured_with_its_real_freewheel_id():
    cfg = brands_config()["brands"]["paramount_games_usa"]
    assert cfg["template_campaign_id"] == "95537948" and cfg["campaign_name"] == "Paramount Games - USA"
    assert not cfg.get("kids")
    assert brand_for_campaign({"name": "Paramount Games - USA"}) == "paramount_games_usa"


def test_the_form_offers_the_campaign_under_usa():
    sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("bpf", REPO_ROOT / "scripts" / "build_plan_form.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    camps = [c for c in mod.app_data()["campaigns"] if c["name"] == "Paramount Games - USA"]
    assert camps and camps[0]["region"] == "USA" and not camps[0]["kids"]


def test_it_builds_tiered_video_and_pause_lines_with_the_standard_units():
    order = OrderBuilder().build(support_plan_from_dict(PLAN))
    assert order.brand == "paramount_games_usa" and order.name.endswith("USA")
    names = [p.name for p in order.placements]
    for tier in (1, 2, 3, 4):
        assert any(f"(Tier {tier})" in n and "Pause Ad" in n for n in names), tier
        assert any(f"15 (Tier {tier})" in n for n in names), tier
    t2_15 = next(p for p in order.placements if "15 (Tier 2)" in p.name and "Pause" not in p.name)
    assert set(t2_15.ad_unit_ids) == {"71999", "72000", "72001"} and t2_15.priority_level == 5
    pause = next(p for p in order.placements if "Pause Ad (Tier 2)" in p.name)
    assert list(pause.ad_unit_ids) == ["63413"]
    assert t2_15.frequency_cap == "1 per 30 min"
    assert not [n for n in names if "Pre-Roll" in n or "Bumper" in n]        # this campaign has no Plan lines
