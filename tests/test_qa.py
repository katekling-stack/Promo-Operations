"""Pre-launch QA auditor (promo_ops.qa). Builds a real, correct order with the tool, feeds its
own output back as the "live" IO (the read shape mirrors what we write), and asserts the auditor
passes it — then mutates placements to confirm each check catches the mistake."""

from __future__ import annotations

import copy

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.qa import QAAuditor, PlacementView, _parse_duration, _parse_tier


def _live(plan_dict, campaign_id):
    """Build a correct order and return (io_body, placement_bodies) as a live payload would."""
    order = OrderBuilder().build(support_plan_from_dict(plan_dict))
    fw = FreeWheelClient.to_freewheel_plan(order)
    io = dict(fw["insertion_order_body"])
    io["campaign_id"] = campaign_id
    return io, fw["placement_bodies"]


class _Mock:
    def __init__(self, io, placements):
        self._io, self._pls = io, placements

    def get_insertion_order(self, io_id):
        return {"data": {"insertion_order": self._io}}

    def list_placements(self, io_id):
        return self._pls


AU_PLAN = {
    "promoted_title": "UFC 300", "region": "AU", "campaign": {"name": "Paramount + - AU"},
    "content_type": "show", "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Sports"],
    "flight": {"start": "2026-10-01", "end": "2026-11-01"},
}


def _audit(io, pls):
    return QAAuditor(client=_Mock(io, pls)).audit_io("80271357")


# --- parsing --------------------------------------------------------------- #
def test_parse_duration_ignores_title_numbers():
    assert _parse_duration("UFC 300 - 15 (Tier 1) - AU") == 15
    assert _parse_duration("UFC 300 - 30 (Tier 4) - AU") == 30
    assert _parse_duration("Frasier - 15 (Pluto) - UK") == 15
    assert _parse_duration("Paramount + - Bumper - Basic Plan - UFC 300 - AU") is None


def test_parse_tier():
    assert _parse_tier("X - 30 (Tier 3) - AU") == 3
    assert _parse_tier("X - Bumper - AU") is None


# --- a correct order passes ------------------------------------------------ #
def test_correct_order_has_no_errors_or_warnings():
    io, pls = _live(AU_PLAN, "73850057")
    rep = _audit(io, pls)
    assert rep.brand == "paramount_plus_au"
    assert rep.region == "AU"
    assert rep.ok()
    assert not rep.by_level("error")
    assert not rep.by_level("warn")


# --- each mutation is caught ---------------------------------------------- #
def test_wrong_timezone_is_flagged():
    io, pls = _live(AU_PLAN, "73850057")
    pls = copy.deepcopy(pls)
    pls[0].setdefault("schedule", {})["time_zone"] = "(GMT-05:00) America - New York"
    rep = _audit(io, pls)
    assert any(f.category == "timezone" and f.level == "error" for f in rep.findings)


def test_empty_ad_units_is_error():
    io, pls = _live(AU_PLAN, "73850057")
    pls = copy.deepcopy(pls)
    pls[0]["ad_product"] = {"ad_unit_node": []}
    rep = _audit(io, pls)
    assert any(f.category == "ad_units" and f.level == "error" for f in rep.findings)


def test_missing_ufc_tier4_set_is_error():
    io, pls = _live(AU_PLAN, "73850057")
    pls = copy.deepcopy(pls)
    for b in pls:
        if "(Tier 4)" in b["name"] and "relationship_targeting" in b:
            b["relationship_targeting"]["set"] = [
                s for s in b["relationship_targeting"]["set"]
                if s.get("set_name") != "Franchise: UFC"]
    rep = _audit(io, pls)
    assert any(f.category == "targeting" and f.level == "error" and "UFC" in f.message
               for f in rep.findings)


def test_wrong_order_level_freq_cap_is_error():
    io, pls = _live(AU_PLAN, "73850057")
    io = copy.deepcopy(io)
    # AU should be 1/15 (period 15); inject 1/30 to simulate the old default.
    io["delivery"] = {"frequency_cap": [{"value": "1", "type": "IMPRESSION", "period": "30"}]}
    rep = _audit(io, pls)
    assert any(f.category == "freq_cap" and f.level == "error" and f.placement == "(order)"
               for f in rep.findings)


def test_recommended_show_on_non_pplus_is_flagged():
    # A Partner (Pluto-only) order must not carry a Recommended Show set.
    io, pls = _live({
        "promoted_title": "UFC", "region": "SE", "campaign": {"name": "Partner - SE"},
        "durations": [30], "showlist": ["NCIS"], "genres": ["Drama"],
        "flight": {"start": "2026-10-01", "end": "2026-11-01"}}, "72910060")
    pls = copy.deepcopy(pls)
    pls[0].setdefault("relationship_targeting", {}).setdefault("set", []).append(
        {"set_name": "Recommended Show",
         "custom_targeting": {"include": {"key_value": "recommended_show=123"}}})
    rep = _audit(io, pls)
    assert any(f.category == "targeting" and f.level == "error"
               and "Recommended Show" in f.message for f in rep.findings)


def test_freq_cap_units_are_normalized_no_false_positive():
    # '1 per 2 hrs' (config) vs period '120' (live) must be treated as equal.
    io, pls = _live(AU_PLAN, "73850057")
    rep = _audit(io, pls)
    assert not any(f.category == "freq_cap" and f.level in ("error", "warn") for f in rep.findings)


def test_creative_duration_match_and_mismatch():
    io, pls = _live(AU_PLAN, "73850057")
    pls = copy.deepcopy(pls)
    # attach a correct creative to the :30 line and a wrong one to a :15 line
    for b in pls:
        if "30 (Tier 1)" in b["name"]:
            b["creatives"] = [{"duration": 30}]
        if "15 (Tier 2)" in b["name"]:
            b["creatives"] = [{"duration": 30}]   # wrong length
    rep = _audit(io, pls)
    ok = [f for f in rep.findings if f.category == "creative_duration" and f.level == "ok"]
    err = [f for f in rep.findings if f.category == "creative_duration" and f.level == "error"]
    assert any("30 (Tier 1)" in f.placement for f in ok)
    assert any("15 (Tier 2)" in f.placement for f in err)


def test_report_text_and_markdown_render():
    io, pls = _live(AU_PLAN, "73850057")
    rep = _audit(io, pls)
    assert "QA — IO 80271357" in rep.text()
    assert "IO 80271357" in rep.markdown()


def test_unknown_brand_is_a_warning_not_a_crash():
    io, pls = _live(AU_PLAN, "73850057")
    io = copy.deepcopy(io)
    io["campaign_id"] = "99999999"   # not in config
    io["name"] = "Something - ZZ"
    rep = _audit(io, pls)
    assert rep.brand is None
    assert any(f.category == "brand" for f in rep.findings)
