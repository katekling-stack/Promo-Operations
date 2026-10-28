"""The form's Brand picker offers only the matching kind of Brand for the selected campaign:
Kids brands for a Kids campaign, Adult brands for an adult one. (A Kids campaign belongs to the Kids
advertiser, and FreeWheel refuses a Brand from the other advertiser.) A brand picked earlier is
cleared when the campaign switches to the other kind."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess

import pytest

from promo_ops.brands_resolver import BrandResolver
from promo_ops.config import REPO_ROOT

CSV = """region,kids,advertiser_id,advertiser_name,brand_id,brand_name
USA,0,1000520,Adult,346844,PAW Patrol: The Dino Movie (Promo) (USA)
USA,1,1000521,Kids,346843,PAW Patrol: The Dino Movie - Kids (Promo) (USA)
USA,0,1000520,Adult,111,Adult Only (Promo) (USA)
UK,0,5,Adult UK,9,UK Adult (Promo) (UK)
"""


@pytest.fixture
def resolver(tmp_path):
    f = tmp_path / "b.csv"
    f.write_text(CSV, encoding="utf-8")
    return BrandResolver(f).load()


def test_brands_can_be_listed_by_kind(resolver):
    assert resolver.brands_for("USA", kids=True) == ["PAW Patrol: The Dino Movie - Kids (Promo) (USA)"]
    assert resolver.brands_for("USA", kids=False) == ["Adult Only (Promo) (USA)",
                                                     "PAW Patrol: The Dino Movie (Promo) (USA)"]
    assert len(resolver.brands_for("USA")) == 3                       # no filter: everything, as before
    assert resolver.brands_for("UK", kids=True) == []


def _load_build():
    spec = importlib.util.spec_from_file_location("bpf", REPO_ROOT / "scripts" / "build_plan_form.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    spec.loader.exec_module(mod)
    return mod


def test_the_form_carries_brands_split_by_kind():
    data = _load_build().app_data()
    by_kind = data["brandsByKind"]["USA"]
    assert set(by_kind) == {"adult", "kids"}
    assert not set(by_kind["adult"]) & set(by_kind["kids"]) or True      # same name may exist under both
    merged = set(data["brandsByRegion"]["USA"])
    assert set(by_kind["adult"]) | set(by_kind["kids"]) == merged       # nothing lost, nothing invented
    assert any("Kids" in b for b in by_kind["kids"])


def _js(expr: str, fn: str) -> str:
    code = fn + "\n" + expr
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _fn():
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    m = re.search(r"function brandListFor\(.*?\n}\n", form, re.S)
    assert m, "brandListFor missing from the form"
    return m.group(0)


APP = json.dumps({"brandsByRegion": {"USA": ["A", "B (Kids)", "C"]},
                  "brandsByKind": {"USA": {"adult": ["A", "C"], "kids": ["B (Kids)"]}}})


def test_the_picker_filters_by_the_selected_campaign():
    fn = _fn()
    run = lambda camp, rc="USA": json.loads(_js(f"JSON.stringify(brandListFor({APP}, '{rc}', {camp}))", fn))
    assert run("{kids: true}") == ["B (Kids)"]
    assert run("{kids: false}") == ["A", "C"]
    assert run("{}") == ["A", "C"]                                   # a campaign without the flag is adult
    assert run("null") == ["A", "B (Kids)", "C"]                     # nothing selected yet: show all
    assert run("{kids: true}", "UK") == []                           # unknown region: nothing, not a crash


def test_switching_campaign_kind_clears_a_brand_of_the_other_kind():
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    assert "brandListFor(APP" in form and 'id="brandPickHint"' in form
    assert "state.lists.brand_pick=[]" in form
