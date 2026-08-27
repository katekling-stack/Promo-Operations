"""AU Tier-1 audience segments: AU resolves the regular global GL-DDA-1P segment when a
show/movie has one, AND its DWH "Summit" segments ("AU - DWH - <src> - ID - Summit - …").
The AU Summit taxonomy never leaks into non-AU regions (they use GL-DDA-1P only).
Deactivated segments are never targeted."""

from __future__ import annotations

import csv

from promo_ops.audience_segments import AudienceSegmentResolver


def _resolver(tmp_path):
    rows = [
        ["show", "segment_name", "segment_id", "platform", "region", "source"],
        ["", "GL-DDA-1P-SHOW_Tulsa_King", "1437993", "DDA", "USA", "t"],
        ["", "AU - DWH - PP - ID - Summit - Content - Tulsa King watchers APAC",
         "1478745", "DDA", "", "t"],
        ["", "AU - DWH - PP - ID - Summit - Content - Tulsa King Watchers deactivated at X",
         "1476542", "DDA", "", "t"],
        ["", "AU - DWH - SMRTR - ID - Summit - Auto - Auto Buyers APAC",
         "1414079", "DDA", "", "t"],
    ]
    p = tmp_path / "segs.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return AudienceSegmentResolver(data_dir=tmp_path).load()


def test_au_uses_gl_and_summit(tmp_path):
    r = _resolver(tmp_path)
    # AU resolves the regular GL-DDA-1P segment AND its DWH Summit segment (active only —
    # the deactivated one is dropped).
    au = r.resolve("Tulsa King", region="AU")
    ids = {rec.segment_id for rec in au.records}
    assert ids == {"1437993", "1478745"}      # GL global + AU Summit
    assert "1476542" not in ids               # deactivated Summit never targeted


def test_non_au_uses_gl_dda_not_summit(tmp_path):
    r = _resolver(tmp_path)
    us = r.resolve("Tulsa King", region="USA")
    assert [rec.segment_id for rec in us.records] == ["1437993"]
    # The AU Summit taxonomy never leaks into a non-AU region.
    assert r.resolve("Auto Buyers APAC", region="USA").records == []
    assert r.resolve("Auto Buyers APAC", region="AU").matched
