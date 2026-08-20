"""DDA flag: for a showlist, split shows into those that already have a DDA audience segment
vs. those that need one generated (a heads-up flag, not a submission). Recognizes both the
legacy GL-DDA-1P-SHOW naming and the new region-bucketed US/EU-UK/APAC-DDA-1P names."""

from __future__ import annotations

from promo_ops.audience_segments import AudienceSegmentResolver, SegmentRecord, _dda_tokens


def test_missing_dda_splits_have_vs_need():
    r = AudienceSegmentResolver().load()
    have, need = r.missing_dda(
        ["The Young and the Restless", "Tulsa King", "Zzzq Nonexistent Show 999"], "USA")
    have_shows = {h["show"] for h in have}
    need_shows = {n["show"] for n in need}
    assert "The Young and the Restless" in have_shows       # known P+ title -> has a segment
    assert "Zzzq Nonexistent Show 999" in need_shows        # invented -> needs one generated
    assert all(h.get("segment_id") for h in have)
    assert all(set(n) == {"show"} for n in need)            # need rows are a plain flag, no payload


def test_missing_dda_dedupes():
    r = AudienceSegmentResolver().load()
    have, need = r.missing_dda(["Tulsa King", "tulsa king", "Tulsa King"], "USA")
    assert len(have) + len(need) == 1                        # same title only counted once


def test_recognizes_new_and_legacy_conventions():
    r = AudienceSegmentResolver()
    r._records = [
        SegmentRecord(show="", segment_name="EU/UK-DDA-1P_INTL___The_Man_in_the_White_Van_eu", segment_id="999"),
        SegmentRecord(show="", segment_name="GL-DDA-1P-SHOW-NCIS", segment_id="111"),
        SegmentRecord(show="", segment_name="US-DDA-1P_The_Impossible", segment_id="222"),
    ]
    r._norm = [_dda_tokens(x.segment_name) for x in r._records]
    r._conv = ["eu uk dda 1p", "gl dda 1p", "us dda 1p"]
    r._loaded = True
    # real, messy names resolve by region + title (existence check uses the same logic)
    have, _ = r.missing_dda(["The Man in the White Van"], "UK")
    assert have and have[0]["segment_id"] == "999"
    have2, _ = r.missing_dda(["NCIS"], "USA")               # legacy GL still works
    assert have2 and have2[0]["segment_id"] == "111"
    _, need = r.missing_dda(["The Impossible"], "UK")       # region isolation: US-bucket not in UK
    assert need and need[0]["show"] == "The Impossible"
