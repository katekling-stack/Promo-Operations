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


def test_tool_request_maps_region_bucket_and_name():
    from promo_ops.audience_segments import tool_request
    r = tool_request("Ben Fogle", "UK", "show", io="Ben Fogle - UK", requester="Kate")
    assert r["region"] == "EU/UK" and r["type"] == "Series"
    assert r["generated_name"] == "EU/UK-DDA-1P-SERIES-Ben_Fogle"
    us = tool_request("Some Movie", "USA", "movie")
    assert us["region"] == "Americas" and us["type"] == "Movie"
    assert us["generated_name"] == "US-DDA-1P-MOVIE-Some_Movie"


def test_guess_genre_tab():
    from promo_ops.audience_segments import guess_genre_tab
    assert guess_genre_tab(["Crime Drama"]) == "Crime"
    assert guess_genre_tab(["Anime", "Action"]) == "Anime/Gaming"
    assert guess_genre_tab(["Nonsense"]) == ""


def test_resolver_recognizes_new_and_legacy_conventions():
    from promo_ops.audience_segments import AudienceSegmentResolver, SegmentRecord, _dda_tokens
    r = AudienceSegmentResolver()
    r._records = [
        SegmentRecord(show="", segment_name="EU/UK-DDA-1P-SERIES-Ben_Fogle", segment_id="999"),
        SegmentRecord(show="", segment_name="GL-DDA-1P-SHOW-NCIS", segment_id="111"),
        SegmentRecord(show="", segment_name="US-DDA-1P-MOVIE-Some_Film", segment_id="222"),
    ]
    r._norm = [_dda_tokens(x.segment_name) for x in r._records]
    r._conv = ["eu uk dda 1p", "gl dda 1p", "us dda 1p"]
    r._loaded = True
    assert [x.segment_id for x in r.resolve_exact("Ben Fogle", "UK").records] == ["999"]
    assert [x.segment_id for x in r.resolve_exact("NCIS", "USA").records] == ["111"]   # legacy still works
    assert [x.segment_id for x in r.resolve_exact("Some Film", "USA").records] == ["222"]
    assert r.resolve_exact("Some Film", "UK").records == []   # region isolation (US bucket not in UK)


def test_submit_all_reports_per_item(monkeypatch):
    from promo_ops.integrations import segment_requests as sr
    calls = {"n": 0}
    def fake(payload, url=None, token=None, timeout=30):
        calls["n"] += 1
        if payload["title"] == "boom":
            raise RuntimeError("nope")
        return {"status": "success"}
    monkeypatch.setattr(sr, "submit_request", fake)
    out = sr.submit_all([{"title": "ok"}, {"title": "boom"}])
    assert out[0]["ok"] is True and out[1]["ok"] is False and "nope" in out[1]["error"]
    assert calls["n"] == 2
