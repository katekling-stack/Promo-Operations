"""Create in FreeWheel from the site. Off unless PROMO_ALLOW_CREATE is on. The server re-checks the
plan itself (the browser can't skip Review), needs the IO name typed back, refuses duplicates, runs
one create at a time, and logs who did what (never the plan). All offline with a fake creator."""

from __future__ import annotations

import json
import threading
import time

import pytest

from promo_ops import webapp
from test_qa_noise import UK_PLAN
from test_webapp import FakeAuditor, call

USER = {"X-Pages-User": "kate.kling@paramount.com"}


class FakeCreator:
    def __init__(self, delay=0.0, result=None, error=None, existing=None):
        self.calls, self.delay, self.error, self.existing = [], delay, error, existing
        self.result = result or {
            "campaign_id": "999",
            "insertion_order": {"ok": True, "data": {"insertion_order": {"id": "777"}}},
            "placements": [{"ok": True, "data": {"placement": {"id": "1"}}},
                           {"ok": False, "status_code": 422,
                            "error": "<?xml version=\"1.0\"?><errors><error>Asset item [1] doesn't exist;</error></errors>"}],
            "brand": {"name": "X (Promo) (UK)", "created": True, "brand_id": "5"}}

    def create_order(self, order, dry_run=True):
        self.calls.append((order.name, dry_run))
        time.sleep(self.delay)
        if self.error:
            raise RuntimeError(self.error)
        return self.result


@pytest.fixture
def make_create():
    servers = []

    def _make(creator=None, allow=True, **kw):
        events = []
        cr = creator or FakeCreator()
        srv = webapp.make_server("127.0.0.1", 0, auditor_factory=lambda: FakeAuditor(), allow_create=allow,
                                 creator_factory=lambda: cr, log=events.append, **kw)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv, cr, events
    yield _make
    for s in servers:
        s.shutdown()
        s.server_close()


def reviewed(srv, plan=None):
    plan = plan or dict(UK_PLAN)
    data = json.loads(call(srv, "POST", "/api/review", {"plan": plan}, USER)[2])
    return plan, data


def create(srv, plan, data, confirm=None, headers=USER):
    body = {"plan": plan, "plan_hash": data["plan_hash"], "confirm": data["summary"]["io_name"] if confirm is None else confirm}
    return call(srv, "POST", "/api/create", body, headers)


def finish(srv, job, wait=10):
    end = time.time() + wait
    while time.time() < end:
        d = json.loads(call(srv, "GET", f"/api/create/{job}", headers=USER)[2])
        if d["status"] in ("done", "error"):
            return d
        time.sleep(0.05)
    raise AssertionError("create job did not finish")


def test_it_is_off_by_default_and_the_review_says_so(make_create):
    srv, cr, _ = make_create(allow=False)
    plan, data = reviewed(srv)
    assert data["create_enabled"] is False
    st, _, body = create(srv, plan, data)
    assert st == 403 and "switched off" in json.loads(body)["error"] and cr.calls == []


def test_the_review_reports_when_creating_is_on(make_create):
    srv, _, _ = make_create()
    assert reviewed(srv)[1]["create_enabled"] is True


def test_a_confirmed_plan_is_created_and_the_result_is_summarised(make_create):
    srv, cr, events = make_create()
    plan, data = reviewed(srv)
    st, _, body = create(srv, plan, data)
    assert st == 200
    res = finish(srv, json.loads(body)["job"])
    assert res["status"] == "done" and res["result"]["io_id"] == "777"
    assert res["result"]["placements_total"] == 2 and res["result"]["placements_created"] == 1
    assert res["result"]["placement_errors"] == [{"status": 422, "message": "Asset item [1] doesn't exist;"}]
    assert res["result"]["brand"]["created"] is True
    assert cr.calls == [(data["summary"]["io_name"], False)]
    start = next(e for e in events if e["event"] == "create_start")
    done = next(e for e in events if e["event"] == "create_done")
    assert start["user"] == done["user"] == "kate.kling@paramount.com" and done["io_id"] == "777"
    blob = json.dumps(events)
    assert "Frasier - UK" in blob                                # who created which IO is recorded...
    assert '"showlist"' not in blob and "Comedy" not in blob and '"plan"' not in blob   # ...the plan's contents are not


def test_the_io_name_must_be_typed_back_exactly(make_create):
    srv, cr, _ = make_create()
    plan, data = reviewed(srv)
    for bad in ("", "wrong name", data["summary"]["io_name"].upper()):
        st, _, body = create(srv, plan, data, confirm=bad)
        assert st == 400 and "type" in json.loads(body)["error"].lower()
    assert cr.calls == []


def test_a_plan_that_changed_since_review_is_refused(make_create):
    srv, cr, _ = make_create()
    plan, data = reviewed(srv)
    changed = {**plan, "promoted_title": "Something Else"}
    st, _, body = call(srv, "POST", "/api/create", {"plan": changed, "plan_hash": data["plan_hash"],
                                                    "confirm": data["summary"]["io_name"]}, USER)
    assert st == 409 and "changed" in json.loads(body)["error"].lower() and cr.calls == []


def test_a_blocked_or_invalid_plan_cannot_be_created_even_with_a_matching_hash(make_create):
    srv, cr, _ = make_create()
    plan = {**UK_PLAN, "promoted_title": ""}
    data = json.loads(call(srv, "POST", "/api/review", {"plan": plan}, USER)[2])
    st, _, body = call(srv, "POST", "/api/create", {"plan": plan, "plan_hash": data["plan_hash"], "confirm": "x"}, USER)
    assert st == 409 and cr.calls == []


def test_someone_not_signed_in_cannot_create(make_create):
    srv, cr, _ = make_create()
    plan, data = reviewed(srv)
    assert create(srv, plan, data, headers={})[0] == 403 and cr.calls == []


def test_the_same_plan_is_not_created_twice(make_create):
    srv, cr, _ = make_create()
    plan, data = reviewed(srv)
    finish(srv, json.loads(create(srv, plan, data)[2])["job"])
    st, _, body = create(srv, plan, data)
    assert st == 409 and "already created" in json.loads(body)["error"].lower() and "777" in json.loads(body)["error"]
    assert len(cr.calls) == 1


def test_only_one_create_runs_at_a_time(make_create):
    srv, cr, _ = make_create(creator=FakeCreator(delay=0.4))
    plan, data = reviewed(srv)
    other = {**plan, "promoted_title": "Another Title"}
    data2 = json.loads(call(srv, "POST", "/api/review", {"plan": other}, USER)[2])
    first = create(srv, plan, data)
    assert first[0] == 200
    st, _, body = create(srv, other, data2)
    assert st == 429 and "another order" in json.loads(body)["error"].lower()
    finish(srv, json.loads(first[2])["job"])


def test_a_refusal_from_the_create_call_is_shown_plainly_and_can_be_retried(make_create):
    cr = FakeCreator(error="Nothing was created. These 'Exclude videos' ids don't exist in FreeWheel: 1.")
    srv, _, events = make_create(creator=cr)
    plan, data = reviewed(srv)
    job = json.loads(create(srv, plan, data)[2])["job"]
    res = finish(srv, job)
    assert res["status"] == "error" and "Exclude videos" in res["error"]
    assert any(e["event"] == "create_failed" for e in events)
    cr.error = None                                          # fixed; a failed create is not recorded as created
    retry = create(srv, plan, data)
    assert retry[0] == 200
    assert finish(srv, json.loads(retry[2])["job"])["status"] == "done"


def test_an_unexpected_failure_hides_internals(make_create):
    class Boom(FakeCreator):
        def create_order(self, order, dry_run=True):
            raise ValueError("/Users/x/secret/path boom")
    srv, _, _ = make_create(creator=Boom())
    plan, data = reviewed(srv)
    res = finish(srv, json.loads(create(srv, plan, data)[2])["job"])
    assert res["status"] == "error" and "/Users/x" not in json.dumps(res)


def test_the_review_page_has_a_create_panel_driven_by_the_server_flag():
    html = webapp.REVIEW_PAGE
    assert "create_enabled" in html and 'fetch("api/create"' in html and "Create in FreeWheel" in html
    assert "innerHTML" not in html and "api/create/" in html


@pytest.mark.parametrize("raw,expected", [("1", True), ("true", True), ("YES", True), ("on", True),
                                          ("", False), (None, False), ("0", False), ("false", False), ("off", False),
                                          ("maybe", False)])
def test_the_create_switch_reads_the_app_setting(raw, expected):
    assert webapp.create_enabled_from_env(raw) is expected
