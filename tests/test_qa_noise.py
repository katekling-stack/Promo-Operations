"""QA must not cry wolf. Four things it used to flag that are NOT problems on a correct order:

  * Pause Ad lines (they use the Pause ad unit, not the video ones)
  * placements that have already finished running (status COMPLETED -- nothing left to fix)
  * the IO-level time zone (the tool never sets it; each placement carries the market's)
  * Tier 2 Pluto lines that target channels (their site groups are the channels, not the
    platform "main" site group)

Each is tested on a correct order the tool built itself, then a genuinely wrong one is checked
to confirm the real mistake is still caught."""

from __future__ import annotations

import copy

from promo_ops.audience_segments import AudienceSegmentResolver
from promo_ops.config import brands_config
from promo_ops.qa import QAAuditor
from test_qa import _live

UK_CID = brands_config()["brands"]["paramount_plus_uk"]["template_campaign_id"]
# Tier 1 is region-only, so the showlist needs a title that has a UK (EU/UK-bucket) segment
_UK_TITLE = sorted(t for t, f in AudienceSegmentResolver().load().title_families().items() if "eu" in f)[0]

UK_PLAN = {
    "promoted_title": "Frasier", "region": "UK", "campaign": {"name": "Paramount + - UK"},
    "content_type": "show", "content_id": "970002006", "recommended_show_id": "970002006",
    "durations": [30], "showlist": [_UK_TITLE], "genres": ["Comedy"],
    "flight": {"start": "2026-10-01", "end": "2026-11-01"},
}


class _Mock:
    def __init__(self, io, placements):
        self._io, self._pls = io, placements

    def get_insertion_order(self, io_id):
        return {"data": {"insertion_order": self._io}}

    def list_placements(self, io_id):
        return self._pls


def _audit(io, pls, **kw):
    return QAAuditor(client=_Mock(io, pls)).audit_io("1", **kw)


def _noisy(rep, only=None):
    return [f for f in rep.findings if f.level in ("warn", "error")
            and (only is None or only(f))]


# --- Pause Ad lines ----------------------------------------------------------------------- #

def test_pause_ad_lines_are_not_held_to_the_video_ad_units():
    plan = {**UK_PLAN, "product_overrides": {"pause_ads": True}}
    io, pls = _live(plan, UK_CID)
    pause = [p for p in pls if "Pause" in p["name"]]
    assert pause, "expected the plan to build Pause Ad placements"
    rep = _audit(io, pls)
    assert not _noisy(rep, lambda f: "Pause" in f.placement), \
        [f.line() for f in _noisy(rep, lambda f: "Pause" in f.placement)]


def test_a_pause_line_with_the_wrong_ad_unit_is_still_caught():
    plan = {**UK_PLAN, "product_overrides": {"pause_ads": True}}
    io, pls = _live(plan, UK_CID)
    pls = copy.deepcopy(pls)
    victim = next(p for p in pls if "Pause" in p["name"])
    victim["ad_product"]["ad_unit_node"] = [{"ad_unit_id": "69304"}]       # a VIDEO unit on a pause line
    rep = _audit(io, pls)
    assert _noisy(rep, lambda f: f.placement == victim["name"] and f.category == "ad_units")


# --- finished placements -------------------------------------------------------------------- #

def _with_status(pls, status, wrong=False):
    pls = copy.deepcopy(pls)
    if wrong:   # break the first placement's time zone: a genuine ERROR if it were checked
        pls[0]["schedule"]["time_zone"] = "(GMT-05:00) America - New York"
    for p in pls:
        p["status"] = status
    return pls


def test_completed_placements_are_skipped_by_default_and_counted():
    io, pls = _live(UK_PLAN, UK_CID)
    rep = _audit(io, _with_status(pls, "COMPLETED", wrong=True))
    assert not rep.by_level("error")                       # the broken line already finished
    assert rep.completed_skipped == len(pls)
    assert f"{len(pls)} completed" in rep.text() and "--all" in rep.text()


def test_all_flag_audits_completed_placements_too():
    io, pls = _live(UK_PLAN, UK_CID)
    rep = _audit(io, _with_status(pls, "COMPLETED", wrong=True), include_completed=True)
    assert rep.by_level("error") and rep.completed_skipped == 0


def test_active_placements_are_always_audited():
    io, pls = _live(UK_PLAN, UK_CID)
    rep = _audit(io, _with_status(pls, "ACTIVE", wrong=True))
    assert rep.by_level("error") and rep.completed_skipped == 0


# --- IO-level time zone ------------------------------------------------------------------- #

def test_the_io_level_time_zone_is_not_reported_at_all():
    # The tool never sets the IO's time zone and delivery follows each placement's, so a note about
    # the network-default IO zone is pure noise on every order. Placement zones are still checked.
    io, pls = _live(UK_PLAN, UK_CID)
    io = {**io, "schedule": {**(io.get("schedule") or {}), "time_zone": "(GMT-05:00) America - New York"}}
    rep = _audit(io, pls)
    assert not [f for f in rep.findings if f.category == "timezone" and f.placement == "(order)"]
    assert not rep.by_level("warn")


def test_a_wrong_placement_time_zone_is_still_caught():
    io, pls = _live(UK_PLAN, UK_CID)
    pls = copy.deepcopy(pls)
    pls[0]["schedule"]["time_zone"] = "(GMT-05:00) America - New York"
    rep = _audit(io, pls)
    assert [f for f in rep.findings if f.category == "timezone" and f.placement == pls[0]["name"]
            and f.level in ("warn", "error")]


# --- Tier 2 Pluto channel lines ------------------------------------------------------------- #

def test_tier2_pluto_channel_lines_are_not_flagged_for_missing_main_site_groups():
    plan = {**UK_PLAN, "durations": [30, 15], "product_overrides": {"pluto_breakout": True},
            "pluto": {"categories": ["Comedy"], "channels": ["Pluto TV Comedy Movies"]}}
    io, pls = _live(plan, UK_CID)
    t2 = [p for p in pls if "(Tier 2)" in p["name"] and "(Pluto)" in p["name"]]
    assert t2, "expected a Tier 2 Pluto line"
    rep = _audit(io, pls)
    assert not _noisy(rep, lambda f: f.category == "targeting"), \
        [f.line() for f in _noisy(rep, lambda f: f.category == "targeting")]


def test_a_line_with_no_platform_targeting_at_all_is_still_flagged():
    io, pls = _live(UK_PLAN, UK_CID)
    pls = copy.deepcopy(pls)
    t1 = next(p for p in pls if "(Tier 1)" in p["name"] and "(Pluto)" not in p["name"])
    for s in t1["relationship_targeting"]["set"]:           # strip every site group from the line
        s.pop("content_targeting", None)
    rep = _audit(io, pls)
    assert _noisy(rep, lambda f: f.placement == t1["name"] and f.category == "targeting")
