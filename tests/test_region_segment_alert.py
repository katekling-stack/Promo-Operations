"""Tier 1 audience segments are REGION-ONLY (team policy), and the tool ALERTS when a show has no
segment in the plan's own region: either only a standard / other-region segment exists (it is
NOT used; a regional one must be requested), or there is none at all.

The coverage rule lives in ONE place (audience_segments.classify_families); the builder note,
the `promo-ops dda` list and the form's flag all read it, so they can't drift apart."""

from __future__ import annotations

import importlib.util

import pytest

from promo_ops.audience_segments import (AudienceSegmentResolver, classify_families,
                                         REGION_BUCKET_CONVENTION)
from promo_ops.config import REPO_ROOT
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

_spec = importlib.util.spec_from_file_location(
    "build_plan_form", REPO_ROOT / "scripts" / "build_plan_form.py")
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


# --- the one rule ------------------------------------------------------------------------ #

@pytest.mark.parametrize("region,fams,expect", [
    ("UK",  {"eu"},            ("own", None)),
    ("UK",  {"eu", "gl"},      ("own", None)),            # own bucket exists -> used, no alert
    ("UK",  {"gl"},            ("elsewhere", "GL-DDA-1P")),
    ("UK",  {"us"},            ("elsewhere", "US-DDA-1P")),
    ("UK",  {"gl", "us"},      ("elsewhere", "GL-DDA-1P")),  # GL beats another region's bucket
    ("USA", {"us"},            ("own", None)),
    ("BR",  {"us"},            ("own", None)),             # Americas share the US bucket
    ("BR",  {"eu"},            ("elsewhere", "EU/UK-DDA-1P")),
    ("AU",  {"apac"},          ("own", None)),
    ("AU",  {"au"},            ("own", None)),             # AU Summit PP counts as AU's own
    ("AU",  {"gl"},            ("elsewhere", "GL-DDA-1P")),
    ("AU",  {"au_10"},         ("none", None)),            # Network 10 segs never used on main lines
    ("UK",  {"au"},            ("none", None)),            # AU Summit never leaks to other regions
    ("UK",  set(),             ("none", None)),
])
def test_classification(region, fams, expect):
    assert classify_families(fams, region) == expect


def test_every_mapped_region_has_a_bucket_and_an_unmapped_one_never_alerts():
    assert set(REGION_BUCKET_CONVENTION) >= {"USA", "CA", "BR", "LATAM", "AU", "UK", "IE", "FR",
                                             "IT", "GSA", "ES", "FI", "DK", "NO", "SE"}
    assert classify_families({"gl"}, "ZZ") == ("own", None)       # no region concept -> no alert


# --- the resolver agrees with the rule, on the real data, for every region ------------------ #

def test_coverage_matches_the_builders_actual_choice_for_every_region():
    res = AudienceSegmentResolver().load()
    idx = res.title_families()
    assert idx, "expected a non-empty title index from the synced segments"
    sample = [t for t, fams in idx.items() if len(fams) >= 2][:60] + list(idx)[:60]
    for region in REGION_BUCKET_CONVENTION:
        for title in sample:
            kind, using = classify_families(idx[title], region)
            m = res.resolve_exact(title, region, prefer_region=True)
            assert m.matched == (kind == "own"), (region, title, kind)   # only OWN is ever targeted


def test_region_coverage_groups_shows():
    res = AudienceSegmentResolver().load()
    idx = res.title_families()
    own_uk = next(t for t, f in idx.items() if "eu" in f)
    gl_only = next(t for t, f in idx.items() if f == {"gl"})
    cov = res.region_coverage([own_uk, gl_only, "Zzzq Nonexistent Show 999"], "UK")
    assert own_uk in cov["own"]
    assert {"show": gl_only, "using": "GL-DDA-1P"} in cov["elsewhere"]
    assert "Zzzq Nonexistent Show 999" in cov["none"]


# --- the builder alerts ------------------------------------------------------------------ #

def _t1_note(region, showlist, campaign):
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Zeta", "region": region, "campaign": {"name": campaign},
        "content_type": "show", "content_id": "1", "durations": [30], "showlist": showlist,
        "genres": ["Drama"]}))
    t1 = next(p for p in order.placements if p.tier == 1)
    return next(d.notes for d in t1.targeting.tiers[0].dimensions if d.key == "audience_segments")


def test_builder_note_names_the_shows_missing_a_regional_segment():
    idx = AudienceSegmentResolver().load().title_families()
    gl_only = next(t for t, f in idx.items() if f == {"gl"})
    own = next(t for t, f in idx.items() if "eu" in f)
    note = _t1_note("UK", [own, gl_only], "Paramount + - UK")
    assert gl_only in note and "UK" in note and "GL-DDA-1P" in note
    assert "NOT targeted" in note and "request a UK segment" in note.lower().replace("request a uk", "request a UK")


def test_builder_note_still_flags_shows_with_no_segment_at_all():
    note = _t1_note("UK", ["Zzzq Nonexistent Show 999"], "Paramount + - UK")
    assert "Zzzq Nonexistent Show 999" in note and "need" in note.lower()


def test_no_note_when_every_show_has_its_own_regional_segment():
    idx = AudienceSegmentResolver().load().title_families()
    own = [t for t, f in idx.items() if "eu" in f][:3]
    assert not _t1_note("UK", own, "Paramount + - UK")


# --- the form reads the same index ------------------------------------------------------- #

def test_form_ships_the_families_index_and_region_buckets():
    data = pf.app_data()
    assert data["ddaFamilies"] and data["ddaRegionBucket"]["AU"] == "apac"
    assert data["ddaRegionBucket"]["UK"] == "eu" and data["ddaRegionBucket"]["USA"] == "us"
    # only shows that actually have a segment are shipped (keeps the form small)
    assert len(data["ddaFamilies"]) < 20000
    assert all(isinstance(v, list) and v for v in data["ddaFamilies"].values())


# --- the alert is printed at push time (push output otherwise hides the builder's notes) ------ #

def test_push_prints_the_audience_alerts_up_front(tmp_path, monkeypatch, capsys):
    import json
    from promo_ops import cli
    idx = AudienceSegmentResolver().load().title_families()
    gl_only = next(t for t, f in idx.items() if f == {"gl"})
    plan = tmp_path / "p.plan.json"
    plan.write_text(json.dumps({
        "promoted_title": "Zeta", "region": "UK", "campaign": {"name": "Paramount + - UK"},
        "content_type": "show", "content_id": "1", "durations": [30], "showlist": [gl_only],
        "genres": ["Drama"]}))
    monkeypatch.setattr(cli, "_push_target", lambda order, target, live: {"dry_run": True})
    cli._cmd_push(type("A", (), {"plan": str(plan), "target": "freewheel", "live": False})())
    err = capsys.readouterr().err
    assert "Tier 1 audience alerts" in err and gl_only in err and "NOT targeted" in err
    assert "NO audience targeting" in err                  # nothing regional -> platform-wide warning


def test_push_prints_nothing_extra_when_every_show_is_covered(tmp_path, monkeypatch, capsys):
    import json
    from promo_ops import cli
    idx = AudienceSegmentResolver().load().title_families()
    own = sorted(t for t, f in idx.items() if "eu" in f)[:2]
    plan = tmp_path / "p.plan.json"
    plan.write_text(json.dumps({
        "promoted_title": "Zeta", "region": "UK", "campaign": {"name": "Paramount + - UK"},
        "content_type": "show", "content_id": "1", "durations": [30], "showlist": own,
        "genres": ["Drama"]}))
    monkeypatch.setattr(cli, "_push_target", lambda order, target, live: {"dry_run": True})
    cli._cmd_push(type("A", (), {"plan": str(plan), "target": "freewheel", "live": False})())
    assert "Tier 1 audience alerts" not in capsys.readouterr().err
