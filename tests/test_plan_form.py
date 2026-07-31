"""The interactive HTML plan form is generated from live config and its exported
plan-dict shape is consumable by the builder — the form can't drift from the tool."""

from __future__ import annotations

import importlib.util
import json
import re

from promo_ops.config import REPO_ROOT
from promo_ops.plan_loader import support_plan_from_dict, validate_plan

_spec = importlib.util.spec_from_file_location(
    "build_plan_form", REPO_ROOT / "scripts" / "build_plan_form.py")
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def test_app_data_covers_regions_and_campaigns():
    data = pf.app_data()
    codes = {r["code"] for r in data["regions"]}
    assert {"USA", "AU", "LATAM", "BR", "FR", "ES"} <= codes
    assert data["campaigns"], "expected campaigns baked in from config"
    # Every campaign resolves to a known region and carries a brand + product list.
    for c in data["campaigns"]:
        assert c["region"] in codes, c
        assert c["brand"] and isinstance(c["products"], list)


def test_pause_ads_offered_on_every_campaign():
    # Pause Ads run across brands, so the form surfaces the toggle everywhere.
    for c in pf.app_data()["campaigns"]:
        assert "pause_ads" in c["products"], c["name"]


def test_build_writes_html_with_data_embedded(tmp_path):
    out = pf.build(tmp_path / "form.html")
    html = out.read_text(encoding="utf-8")
    assert "/*APP_DATA*/" not in html          # placeholder was substituted
    m = re.search(r"const APP = (\{.*?\});", html, re.S)
    assert m, "APP data block not found"
    data = json.loads(m.group(1))
    assert data["regions"] and data["campaigns"]


def test_exported_plan_shape_is_buildable():
    # Mirror what the form's buildPlan() emits and confirm the loader accepts it.
    raw = {
        "promoted_title": "Frisco King",
        "region": "USA",
        "campaign": {"name": "Paramount + - USA"},
        "content_type": "show",
        "durations": [30, 15],
        "product_overrides": {"pause_ads": True},
        "genres": ["Drama"],
        "showlist": ["NCIS"],
        "pluto": {"categories": ["Drama"], "channels": ["CBS Drama"]},
    }
    plan = support_plan_from_dict(raw)
    assert plan.promoted_title == "Frisco King"
    assert "pause_ads" in plan.formats
    assert validate_plan(plan) == []
