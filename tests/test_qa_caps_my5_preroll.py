"""Two frequency-cap rules from the team:
  * Premium Pre-Roll caps are allowed to differ, so QA does not flag them.
  * An UNTIERED My5 line (like the dedicated '5 - UK' campaign's) should be 1 per hour; tiered
    My5 lines keep the tier caps."""

from __future__ import annotations

import copy

from promo_ops.qa import QAAuditor
from test_qa_noise import UK_CID, UK_PLAN, _Mock
from test_qa import _live

PLAN = {**UK_PLAN, "durations": [15, 30], "product_overrides": {"my5_breakout": True, "pause_ads": False}}


def _lines():
    io, pls = _live(PLAN, UK_CID)
    return io, copy.deepcopy(pls)


def _set_cap(p, value, minutes):
    p.setdefault("delivery", {})["frequency_cap"] = [{"value": value, "type": "STANDARD", "period": minutes}]


def _audit(io, pls):
    return QAAuditor(client=_Mock(io, pls)).audit_io("1")


def _cap_findings(rep, name_part, level=None):
    return [f for f in rep.findings if f.category == "freq_cap" and name_part in f.placement
            and (level is None or f.level == level)]


def test_premium_pre_roll_caps_are_not_flagged():
    io, pls = _lines()
    pre = next(p for p in pls if "Pre-Roll" in p["name"] and "Premium" in p["name"])
    _set_cap(pre, 1, 20160)                         # 2 weeks where the tool's template says 1 week
    rep = _audit(io, pls)
    assert not _cap_findings(rep, pre["name"], "warn") and not _cap_findings(rep, pre["name"], "error")


def test_other_guaranteed_lines_are_still_checked():
    io, pls = _lines()
    bump = next((p for p in pls if "Bumper" in p["name"] or "Essential" in p["name"]), None)
    if bump is None:
        return                                       # this plan builds no bumper line
    _set_cap(bump, 99, 5)
    assert _cap_findings(_audit(io, pls), bump["name"], "warn")


def _untiered_my5(pls, cap):
    my5 = next(p for p in pls if "(My5)" in p["name"] and "(Tier 2)" in p["name"] and "30" in p["name"])
    my5["name"] = "Dexter: Resurrection - Season 1 - 30 (My5) (Dexter) - UK"
    _set_cap(my5, *cap)
    return my5


def test_an_untiered_my5_line_at_one_per_hour_is_fine():
    io, pls = _lines()
    my5 = _untiered_my5(pls, (1, 60))
    rep = _audit(io, pls)
    assert not _cap_findings(rep, my5["name"], "warn")
    assert _cap_findings(rep, my5["name"], "ok")


def test_an_untiered_my5_line_at_one_per_thirty_minutes_is_flagged():
    io, pls = _lines()
    my5 = _untiered_my5(pls, (1, 30))
    warns = _cap_findings(_audit(io, pls), my5["name"], "warn")
    assert warns and warns[0].expected == ["1 per hr"] and warns[0].actual == ["1 per 30 min"]


def test_tiered_my5_lines_keep_their_tier_caps():
    io, pls = _lines()
    tiered = next(p for p in pls if "(My5)" in p["name"] and "(Tier 2)" in p["name"])
    rep = _audit(io, pls)
    assert not _cap_findings(rep, tiered["name"], "warn")      # built by the tool -> 1 per 30 min matches
    _set_cap(tiered, 1, 60)
    assert _cap_findings(_audit(io, pls), tiered["name"], "warn")
