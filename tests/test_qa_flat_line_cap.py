"""Flat (untiered) lines whose template fixes a frequency cap -- the Kids remnant lines, 1 per 15 min --
are checked against THAT cap, not the tier default (1 per 30 min). Regression: QA flagged a correct
Paw Patrol Kids IO with four false warnings."""

from __future__ import annotations

import copy

from promo_ops.config import brands_config
from promo_ops.qa import QAAuditor
from test_qa import _live
from test_qa_noise import _Mock

KIDS_CID = brands_config()["brands"]["paramount_plus_kids"]["template_campaign_id"]
PLAN = {"promoted_title": "Frasier", "region": "USA", "campaign": {"name": "Paramount + - Kids - USA"},
        "durations": [30, 15], "genres": ["Kids"], "kids_audience": ["younger"],
        "flight": {"start": "2026-10-01", "end": "2026-11-01"}}


def _audit(io, pls):
    return QAAuditor(client=_Mock(io, pls)).audit_io("1")


def _remnant(pls):
    return [p for p in pls if "Now Streaming" in p["name"] or ("Kids" in p["name"] and "Plan" not in p["name"])]


def _caps(rep, names, level=None):
    return [f for f in rep.findings if f.category == "freq_cap" and f.placement in names
            and (level is None or f.level == level)]


def test_a_correct_kids_remnant_line_at_one_per_fifteen_is_not_flagged():
    io, pls = _live(PLAN, KIDS_CID)
    lines = _remnant(pls)
    assert lines, "expected kids remnant lines"
    rep = _audit(io, pls)
    assert not _caps(rep, {p["name"] for p in lines}, "warn"), [f.line() for f in _caps(rep, {p["name"] for p in lines}, "warn")]
    assert _caps(rep, {p["name"] for p in lines}, "ok")


def test_a_kids_remnant_line_with_the_wrong_cap_is_still_flagged():
    io, pls = _live(PLAN, KIDS_CID)
    pls = copy.deepcopy(pls)
    victim = _remnant(pls)[0]
    victim["delivery"]["frequency_cap"] = [{"value": 1, "type": "STANDARD", "period": 30}]
    warns = _caps(_audit(io, pls), {victim["name"]}, "warn")
    assert warns and warns[0].expected == ["1 per 15 min"] and warns[0].actual == ["1 per 30 min"]
