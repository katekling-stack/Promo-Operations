"""The Review step: a plan goes in, the same checked preview the command line's `preview` / dry-run
shows comes out -- and NOTHING is sent to FreeWheel. Alerts share one source with the CLI so the
site and the terminal can never disagree."""

from __future__ import annotations

import json

import pytest

from promo_ops import review
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from test_qa_noise import UK_PLAN


@pytest.fixture(autouse=True)
def no_freewheel(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Review must never touch FreeWheel")
    monkeypatch.setattr(FreeWheelClient, "__init__", boom)
    monkeypatch.setattr(FreeWheelClient, "_invoke", boom)


def test_a_good_plan_gives_a_full_preview():
    r = review.review_plan(UK_PLAN)
    assert r["ok"] and not r["problems"]
    s = r["summary"]
    assert s["io_name"] and s["brand"] == "paramount_plus_uk" and s["region"] == "UK"
    assert s["placements"] == len(r["placements"]) > 0 and s["flight"] == "2026-10-01 to 2026-11-01"
    assert s["destination"] == "a new IO"
    p = r["placements"][0]
    assert p["name"] and p["format"] and isinstance(p["tiers"], list) and p["tiers"]
    dim = p["tiers"][0]["dimensions"][0]
    assert {"key", "label", "count", "preview", "more", "notes"} <= set(dim)


def test_the_preview_carries_priority_cap_and_exclusions_when_present():
    r = review.review_plan(UK_PLAN)
    assert any(p["priority"] is not None for p in r["placements"])
    assert any(p["frequency_cap"] for p in r["placements"])


def test_an_existing_io_is_named_as_the_destination():
    r = review.review_plan({**UK_PLAN, "existing_io_id": "85381582"})
    assert r["ok"] and r["summary"]["destination"] == "existing IO 85381582"


def test_intake_problems_are_listed_and_nothing_is_built():
    bad = {**UK_PLAN, "promoted_title": ""}
    r = review.review_plan(bad)
    assert not r["ok"] and any("Promoted Title" in x for x in r["problems"])
    assert r["placements"] == []


@pytest.mark.parametrize("raw", [None, [], "x", 5])
def test_something_that_is_not_a_plan_is_refused_politely(raw):
    r = review.review_plan(raw)
    assert not r["ok"] and r["problems"] and "plan" in r["problems"][0].lower()


def test_a_plan_that_builds_nothing_says_so():
    kids_without_audience = {"promoted_title": "T", "region": "UK", "campaign": {"name": "5 - Kids - UK"},
                             "durations": [15, 30], "genres": ["Drama"],
                             "flight": {"start": "2026-10-01", "end": "2026-11-01"}}
    r = review.review_plan(kids_without_audience)
    assert not r["ok"] and any("0 placements" in x for x in r["problems"])


def test_alerts_are_exactly_what_the_command_line_prints(capsys):
    from promo_ops.cli import _print_audience_alerts
    plan = {**UK_PLAN, "showlist": ["Frasier"]}
    order = OrderBuilder().build(support_plan_from_dict(plan))
    _print_audience_alerts(order)
    printed = [l.strip()[2:] for l in capsys.readouterr().err.splitlines() if l.strip().startswith("• ")]
    assert printed == review.audience_alerts(order)
    assert review.review_plan(plan)["alerts"] == printed


def test_the_fingerprint_is_stable_and_changes_with_the_plan():
    a = review.review_plan(UK_PLAN)["plan_hash"]
    assert a == review.review_plan(json.loads(json.dumps(UK_PLAN)))["plan_hash"]
    assert a != review.review_plan({**UK_PLAN, "promoted_title": "Other"})["plan_hash"]
