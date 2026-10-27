"""`promo-ops dda-requests` lists the shows that still need a REGIONAL Tier 1 segment requested.
Regression: after segments became region-only, the command crashed on a category that no longer
exists. It now reports two kinds of gap: no segment anywhere, and a segment only in another region."""

from __future__ import annotations

import csv

from promo_ops.audience_segments import AudienceSegmentResolver, classify_families
from promo_ops.cli import main


def _pick(region):
    idx = AudienceSegmentResolver().load().title_families()
    own = next(t for t, f in sorted(idx.items()) if classify_families(f, region)[0] == "own")
    other = next(t for t, f in sorted(idx.items()) if classify_families(f, region)[0] == "elsewhere")
    return own, other


def test_it_lists_both_kinds_of_gap_and_writes_a_csv(tmp_path, capsys):
    own, other = _pick("USA")
    out = tmp_path / "need.csv"
    rc = main(["dda-requests", "--shows", f"{own};{other};Zzz Not A Real Show", "--region", "USA",
               "--out", str(out)])
    text = capsys.readouterr().out
    assert rc == 0
    assert "1 show(s) already have a USA segment" in text
    assert "NO SEGMENT ANYWHERE" in text and "Zzz Not A Real Show" in text
    assert "ONLY IN ANOTHER REGION" in text and other in text
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert {r["show"]: r["status"] for r in rows} == {other: "only in another region",
                                                     "Zzz Not A Real Show": "no segment anywhere"}
    assert all(r["region"] == "USA" for r in rows)


def test_nothing_to_request_says_so(tmp_path, capsys):
    own, _ = _pick("USA")
    rc = main(["dda-requests", "--shows", own, "--region", "USA", "--out", str(tmp_path / "x.csv")])
    text = capsys.readouterr().out
    assert rc == 0 and "0 need one requested" in text
