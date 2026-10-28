"""A plan whose Tier 1 would have NO audience (it names shows, but none has a segment in the order's
region) would run across the whole platform at top priority. It is BLOCKED -- on the Review page,
in `promo-ops push --live`, and inside the FreeWheel create call -- until a regional segment exists
for at least one show. A plan with at least one regional segment is never blocked."""

from __future__ import annotations

import json

import pytest

from promo_ops import cli, review
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from test_qa_noise import UK_PLAN, _UK_TITLE

NO_SEGMENT = {**UK_PLAN, "showlist": ["Zzz Not A Real Show", "Another Fake Title"]}


def _order(plan):
    return OrderBuilder().build(support_plan_from_dict(plan))


def test_no_regional_segment_for_any_show_is_blocked():
    problems = review.blocking_problems(_order(NO_SEGMENT))
    assert len(problems) == 1
    assert "UK" in problems[0] and "whole platform" in problems[0] and "request" in problems[0].lower()


def test_one_covered_show_is_enough_to_go_ahead():
    plan = {**UK_PLAN, "showlist": [_UK_TITLE, "Zzz Not A Real Show"]}
    assert review.blocking_problems(_order(plan)) == []        # the alert about the other show remains


def test_a_plan_that_names_no_shows_is_not_blocked():
    plan = {k: v for k, v in UK_PLAN.items() if k != "showlist"}
    assert review.blocking_problems(_order(plan)) == []


def test_the_review_page_shows_everything_but_says_it_is_blocked():
    r = review.review_plan(NO_SEGMENT)
    assert r["ok"] is False and r["blocked"] is True
    assert any("whole platform" in p for p in r["problems"])
    assert r["placements"] and r["summary"]["io_name"] and r["alerts"]      # the CM can still see the plan


def test_a_clean_plan_is_not_marked_blocked():
    r = review.review_plan(UK_PLAN)
    assert r["ok"] is True and r["blocked"] is False


def test_live_push_is_refused_before_anything_is_touched(tmp_path, monkeypatch, capsys):
    f = tmp_path / "p.plan.json"
    f.write_text(json.dumps(NO_SEGMENT), encoding="utf-8")

    def boom(*a, **k):
        raise AssertionError("FreeWheel must not be touched")
    monkeypatch.setattr(FreeWheelClient, "__init__", boom)
    rc = cli.main(["push", str(f), "--target", "freewheel", "--live"])
    err = capsys.readouterr().err
    assert rc == 2 and "BLOCKED" in err and "whole platform" in err


def test_a_dry_run_still_previews_but_says_it_would_be_blocked(tmp_path, monkeypatch, capsys):
    f = tmp_path / "p.plan.json"
    f.write_text(json.dumps(NO_SEGMENT), encoding="utf-8")
    monkeypatch.setattr(cli, "_push_target", lambda order, target, live: {"dry_run": True})
    rc = cli.main(["push", str(f), "--target", "freewheel"])
    cap = capsys.readouterr()
    assert rc == 0 and "dry_run" in cap.out and "would be BLOCKED" in cap.err


def test_the_create_call_itself_refuses_so_no_other_caller_can_skip_the_check():
    order = _order(NO_SEGMENT)
    c = FreeWheelClient.__new__(FreeWheelClient)
    c._ensure_io_brand = lambda o, campaign_id=None: None
    c.resolve_campaign_id = lambda n: "999"
    touched = []
    c._invoke = lambda *a, **k: touched.append(a) or {}
    with pytest.raises(RuntimeError, match="no UK audience segment"):
        c.create_order(order, dry_run=False)
    assert touched == []
    assert c.create_order(order, dry_run=True)["dry_run"] is True          # previewing is still fine


def test_empty_audience_data_is_reported_as_a_data_problem_not_as_missing_segments(tmp_path, monkeypatch):
    empty = tmp_path / "synced_audience_items.csv"
    empty.write_text("show,segment_name,segment_id,platform,region,source\n", encoding="utf-8")
    monkeypatch.setattr(review, "AUDIENCE_ITEMS_FILE", empty)
    problems = review.blocking_problems(_order(UK_PLAN))
    assert len(problems) == 1
    assert "audience data" in problems[0].lower() and "update.sh" in problems[0]
    assert "request" not in problems[0].lower()
    r = review.review_plan(UK_PLAN)
    assert r["ok"] is False and "audience data" in r["problems"][0].lower()


def test_healthy_audience_data_adds_no_data_problem():
    assert review.audience_data_problem() is None
