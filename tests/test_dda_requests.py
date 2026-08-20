"""DDA-request output: for a showlist, split shows into those that already have a DDA
audience segment vs. those that need one requested (with the canonical GL-DDA-1P name)."""

from __future__ import annotations

from promo_ops.audience_segments import AudienceSegmentResolver, dda_request_name


def test_request_name_format():
    assert dda_request_name("Tulsa King") == "GL-DDA-1P-SHOW-Tulsa_King"
    assert dda_request_name("  The Royals ") == "GL-DDA-1P-SHOW-The_Royals"


def test_missing_dda_splits_have_vs_need():
    r = AudienceSegmentResolver().load()
    have, need = r.missing_dda(
        ["The Young and the Restless", "Tulsa King", "Zzzq Nonexistent Show 999"], "USA")
    have_shows = {h["show"] for h in have}
    need_shows = {n["show"] for n in need}
    # known P+ titles resolve to a real segment id; the invented one needs a request
    assert "The Young and the Restless" in have_shows
    assert "Zzzq Nonexistent Show 999" in need_shows
    assert all(h.get("segment_id") for h in have)
    assert all(n["request_name"].startswith("GL-DDA-1P-SHOW-") for n in need)


def test_missing_dda_dedupes():
    r = AudienceSegmentResolver().load()
    have, need = r.missing_dda(["Tulsa King", "tulsa king", "Tulsa King"], "USA")
    assert len(have) + len(need) == 1        # the same title only appears once
