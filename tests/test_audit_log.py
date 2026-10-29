"""A permanent record of who created what, on a shared Volume (the app's own disk vanishes on restart).
One JSON line per create event in <volume>/audit-YYYY-MM.jsonl. Only create events, never plan contents,
and a Volume problem can never break the app."""

from __future__ import annotations

import json
import time

from promo_ops import webapp


def _lines(d):
    out = []
    for f in sorted(d.glob("audit-*.jsonl")):
        out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def test_create_events_are_written_with_who_what_and_when(tmp_path):
    seen = []
    log = webapp.tee_audit(seen.append, tmp_path)
    log({"event": "create_start", "user": "kate@x.com", "io_name": "Frasier - UK", "ts": time.time()})
    log({"event": "create_done", "user": "kate@x.com", "io_name": "Frasier - UK", "io_id": "777",
         "placements": 6, "of": 6, "ts": time.time()})
    rows = _lines(tmp_path)
    assert [r["event"] for r in rows] == ["create_start", "create_done"]
    assert rows[1]["io_id"] == "777" and rows[1]["user"] == "kate@x.com" and "at" in rows[1]   # ISO timestamp added
    assert len(seen) == 2                                    # still goes to the normal log too


def test_other_events_are_not_written_to_the_record(tmp_path):
    log = webapp.tee_audit(lambda e: None, tmp_path)
    for ev in ("qa_start", "review", "suggest", "denied", "qa_done"):
        log({"event": ev, "user": "x"})
    assert _lines(tmp_path) == []


def test_a_failed_create_is_recorded_too(tmp_path):
    log = webapp.tee_audit(lambda e: None, tmp_path)
    log({"event": "create_failed", "user": "kate@x.com", "io_name": "X", "why": "refused"})
    assert _lines(tmp_path)[0]["why"] == "refused"


def test_a_volume_problem_never_breaks_the_app(tmp_path):
    seen = []
    log = webapp.tee_audit(seen.append, tmp_path / "does" / "not" / "exist" / "and" / "cannot")
    ro = tmp_path / "file"
    ro.write_text("i am a file, not a folder")
    log2 = webapp.tee_audit(seen.append, ro)
    log({"event": "create_done", "user": "u"})
    log2({"event": "create_done", "user": "u"})
    assert len(seen) == 2                                    # no exception; the normal log still got both


def test_no_volume_means_no_extra_writing():
    seen = []
    log = webapp.tee_audit(seen.append, None)
    log({"event": "create_done", "user": "u"})
    assert seen == [{"event": "create_done", "user": "u"}]


def test_the_app_reads_the_volume_path_from_the_environment():
    assert webapp.audit_dir_from_env(None) is None and webapp.audit_dir_from_env("  ") is None
    assert str(webapp.audit_dir_from_env("/data/promo-audit")) == "/data/promo-audit"
