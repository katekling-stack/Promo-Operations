"""The hosted team app (promo_ops.webapp): paste an IO id -> QA report, plus the campaign form with
its Suggest button, served from one place. v1 only READS from FreeWheel.

What these tests protect:
  * it never changes anything in FreeWheel (the only FreeWheel calls are the auditor's reads)
  * inputs are validated, output is never built as HTML from FreeWheel text
  * every run is logged with WHO ran it (the Pages X-Pages-User header)
  * an optional group allow-list backs up the platform's own access setting
  * long QA runs are jobs the page polls, one at a time (a QA of a big IO takes minutes)
All of it runs against a fake auditor on a local port -- no FreeWheel, no network."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

import pytest

from promo_ops import webapp
from promo_ops.qa import Finding, QAReport


class FakeAuditor:
    """Stands in for QAAuditor: canned reports, and a record of how many ran at once."""

    def __init__(self, delay=0.0):
        self.delay, self.calls, self.running, self.max_running = delay, [], 0, 0
        self._lock = threading.Lock()

    def audit_io(self, io_id, include_completed=False):
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            time.sleep(self.delay)
            self.calls.append((io_id, include_completed))
            rep = QAReport(io_id=str(io_id), io_name="Demo - UK", brand="paramount_plus_uk",
                           region="UK", placement_count=3, completed_skipped=1)
            rep.findings = [
                Finding("error", "ad_units", "Demo - 30 (Tier 1) - UK", "bad unit", ["1"], ["2"]),
                Finding("warn", "priority", "<script>alert(1)</script> - UK", "off by one", -4, -3),
                Finding("info", "timezone", "(order)", "just so you know"),
                Finding("ok", "naming", "Demo - 30 (Tier 1) - UK", "fine"),
            ]
            return rep
        finally:
            with self._lock:
                self.running -= 1


@pytest.fixture
def make(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    servers = []

    def _make(auditor=None, allowed_groups=None, factory=None):
        events = []
        aud = auditor or FakeAuditor()
        srv = webapp.make_server("127.0.0.1", 0, auditor_factory=factory or (lambda: aud),
                                 allowed_groups=allowed_groups, log=events.append)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv, aud, events

    yield _make
    for s in servers:
        s.shutdown()
        s.server_close()


def call(srv, method, path, body=None, headers=None):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if isinstance(body, (dict, list)):
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def run_job(srv, ios, headers=None, all_=False, wait=10):
    st, _, b = call(srv, "POST", "/api/qa", {"io": ios, "all": all_}, headers)
    assert st == 200, b
    job = json.loads(b)["job"]
    end = time.time() + wait
    while time.time() < end:
        st, _, b = call(srv, "GET", f"/api/qa/{job}", headers=headers)
        data = json.loads(b)
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.05)
    raise AssertionError("job did not finish")


# --- basics ------------------------------------------------------------------------------- #

def test_health_check_answers_200_without_any_identity(make):
    srv, _, _ = make(allowed_groups=["Promo Ad Ops"])
    st, _, body = call(srv, "GET", "/healthz")
    assert st == 200 and body.strip() == b"ok"


def test_home_and_qa_pages_use_relative_links_so_they_work_under_a_path_prefix(make):
    srv, _, _ = make()
    for path in ("/", "/qa"):
        st, hdr, body = call(srv, "GET", path)
        html = body.decode()
        assert st == 200 and "text/html" in hdr["Content-Type"]
        assert not re.search(r'(?:href|src|action)="/', html), path
        assert 'fetch("/' not in html and "fetch('/" not in html, path
    assert 'href="qa"' in call(srv, "GET", "/")[2].decode()
    assert 'href="form"' in call(srv, "GET", "/")[2].decode()


def test_qa_page_never_builds_html_from_results_and_sets_a_strict_policy(make):
    srv, _, _ = make()
    st, hdr, body = call(srv, "GET", "/qa")
    html = body.decode()
    assert "innerHTML" not in html and "document.write" not in html and "eval(" not in html
    assert "textContent" in html
    assert "Content-Security-Policy" in hdr and "default-src 'none'" in hdr["Content-Security-Policy"]
    assert hdr.get("X-Content-Type-Options") == "nosniff"


def test_the_campaign_form_is_served(make):
    srv, _, _ = make()
    st, hdr, body = call(srv, "GET", "/form")
    assert st == 200 and b"Campaign Plan" in body and "text/html" in hdr["Content-Type"]


def test_the_form_asks_for_suggestions_with_a_relative_url():
    # an absolute "/suggest" breaks the moment the app is shown under a path of another site
    from promo_ops.config import REPO_ROOT
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    assert 'fetch("suggest"' in form and 'fetch("/suggest"' not in form


def test_unknown_paths_and_wrong_methods(make):
    srv, _, _ = make()
    assert call(srv, "GET", "/nope")[0] == 404
    assert call(srv, "GET", "/api/qa/doesnotexist")[0] == 404
    assert call(srv, "POST", "/qa", {})[0] == 404
    assert call(srv, "DELETE", "/api/qa/x")[0] in (404, 405, 501)


# --- the QA job -------------------------------------------------------------------------------- #

def test_a_qa_run_returns_a_report_per_io_with_every_finding(make):
    srv, aud, _ = make()
    data = run_job(srv, ["86085716", "82847472"])
    assert data["status"] == "done" and [r["io_id"] for r in data["reports"]] == ["86085716", "82847472"]
    r = data["reports"][0]
    assert r["io_name"] == "Demo - UK" and r["region"] == "UK" and r["completed_skipped"] == 1
    assert {f["level"] for f in r["findings"]} == {"error", "warn", "info", "ok"}
    assert r["counts"] == {"error": 1, "warn": 1, "info": 1, "ok": 1}
    assert "QA report" in r["markdown"]
    assert aud.calls == [("86085716", False), ("82847472", False)]


def test_the_include_completed_switch_reaches_the_auditor(make):
    srv, aud, _ = make()
    run_job(srv, ["86085716"], all_=True)
    assert aud.calls == [("86085716", True)]


def test_findings_are_returned_as_plain_text_never_as_markup(make):
    srv, _, _ = make()
    data = run_job(srv, ["86085716"])
    names = [f["placement"] for f in data["reports"][0]["findings"]]
    assert "<script>alert(1)</script> - UK" in names          # carried verbatim as DATA (the page uses textContent)


@pytest.mark.parametrize("bad", [
    [], ["abc"], ["123"], ["12345678901234"], ["86085716; rm -rf /"], ["86085716", ""],
    ["1000001", "1000002", "1000003", "1000004", "1000005", "1000006"], "86085716", None,
])
def test_io_ids_are_validated(make, bad):
    srv, aud, _ = make()
    st, _, body = call(srv, "POST", "/api/qa", {"io": bad})
    assert st == 400 and "error" in json.loads(body) and aud.calls == []


def test_oversized_and_malformed_bodies_are_refused(make):
    srv, aud, _ = make()
    assert call(srv, "POST", "/api/qa", b"x" * 100_000, {"Content-Type": "application/json"})[0] == 413
    assert call(srv, "POST", "/api/qa", b"{not json", {"Content-Type": "application/json"})[0] == 400
    assert aud.calls == []


def test_runs_are_one_at_a_time_even_if_several_are_submitted(make):
    aud = FakeAuditor(delay=0.15)
    srv, _, _ = make(auditor=aud)
    jobs = [json.loads(call(srv, "POST", "/api/qa", {"io": [str(1000000 + i)]})[2])["job"] for i in range(3)]
    end = time.time() + 15
    while time.time() < end:
        done = [json.loads(call(srv, "GET", f"/api/qa/{j}")[2])["status"] for j in jobs]
        if all(s == "done" for s in done):
            break
        time.sleep(0.05)
    assert all(s == "done" for s in done) and aud.max_running == 1


def test_too_many_queued_jobs_are_refused_with_429(make):
    aud = FakeAuditor(delay=0.4)
    srv, _, _ = make(auditor=aud)
    codes = [call(srv, "POST", "/api/qa", {"io": [str(1000000 + i)]})[0] for i in range(webapp.MAX_QUEUED + 3)]
    assert 429 in codes and codes[0] == 200


def test_a_missing_freewheel_login_is_a_friendly_message_not_a_stack_trace(make):
    def factory():
        raise RuntimeError("Missing required env var FREEWHEEL_USERNAME")
    srv, _, events = make(factory=factory)
    data = run_job(srv, ["86085716"])
    assert data["status"] == "error"
    assert "isn't set up" in data["error"] and "FREEWHEEL" not in data["error"]
    assert "Traceback" not in json.dumps(data)
    assert any(e["event"] == "qa_failed" for e in events)


def test_an_unexpected_failure_is_reported_without_internals(make):
    class Boom:
        def audit_io(self, *a, **k):
            raise ValueError("secret-ish internal detail /Users/x/.env")
    srv, _, _ = make(auditor=Boom())
    data = run_job(srv, ["86085716"])
    assert data["status"] == "done"                        # one IO failing doesn't sink the job
    assert data["reports"][0]["error"] and "/Users/x" not in json.dumps(data)


def test_job_results_expire():
    clock = [1000.0]
    store = webapp.JobStore(ttl=60, max_jobs=10, now=lambda: clock[0])
    j = store.create(["1"], False, "kate@x")
    assert store.get(j["id"]) is not None
    clock[0] += 61
    assert store.get(j["id"]) is None


def test_the_job_store_is_bounded():
    store = webapp.JobStore(ttl=3600, max_jobs=3)
    ids = [store.create(["1"], False, "u")["id"] for _ in range(6)]
    assert store.get(ids[0]) is None and store.get(ids[-1]) is not None


# --- who ran it ---------------------------------------------------------------------------------- #

def test_every_run_is_logged_with_who_ran_it(make):
    srv, _, events = make()
    run_job(srv, ["86085716"], headers={"X-Pages-User": "kate.kling@paramount.com",
                                        "X-Pages-Groups": '"Promo Ad Ops"'})
    start = next(e for e in events if e["event"] == "qa_start")
    done = next(e for e in events if e["event"] == "qa_done")
    assert start["user"] == "kate.kling@paramount.com" and start["io"] == ["86085716"]
    assert done["user"] == "kate.kling@paramount.com" and done["errors"] == 1 and done["warnings"] == 1
    assert "password" not in json.dumps(events).lower() and "token" not in json.dumps(events).lower()


def test_a_request_with_no_identity_is_logged_as_anonymous(make):
    srv, _, events = make()
    run_job(srv, ["86085716"])
    assert next(e for e in events if e["event"] == "qa_start")["user"] == "anonymous"


# --- optional group allow-list ----------------------------------------------------------------- #

def test_the_group_allow_list_backs_up_the_platforms_access_setting(make):
    srv, aud, events = make(allowed_groups=["Promo Ad Ops"])
    assert call(srv, "GET", "/qa")[0] == 403
    assert call(srv, "GET", "/")[0] == 403
    assert call(srv, "POST", "/api/qa", {"io": ["86085716"]})[0] == 403
    other = {"X-Pages-User": "x@y", "X-Pages-Groups": '"Finance", "Sales, EMEA"'}
    assert call(srv, "GET", "/qa", headers=other)[0] == 403
    ok = {"X-Pages-User": "k@y", "X-Pages-Groups": '"Finance", "Promo Ad Ops"'}
    assert call(srv, "GET", "/qa", headers=ok)[0] == 200
    assert run_job(srv, ["86085716"], headers=ok)["status"] == "done"
    assert any(e["event"] == "denied" for e in events)
    assert aud.calls == [("86085716", False)]


def test_a_group_name_with_a_comma_is_one_group(make):
    srv, _, _ = make(allowed_groups=["Sales, EMEA"])
    assert call(srv, "GET", "/qa", headers={"X-Pages-Groups": '"Sales, EMEA"'})[0] == 200
    assert call(srv, "GET", "/qa", headers={"X-Pages-Groups": '"Sales", "EMEA"'})[0] == 403


def test_group_names_from_the_environment_are_parsed():
    assert webapp.groups_from_env("Promo Ad Ops; Finance ;  ") == ["Promo Ad Ops", "Finance"]
    assert webapp.groups_from_env("") is None and webapp.groups_from_env(None) is None


# --- suggest ----------------------------------------------------------------------------------- #

def test_suggest_needs_a_title(make):
    srv, _, _ = make()
    st, _, body = call(srv, "POST", "/suggest", {"title": "  ", "region": "UK"})
    assert st == 400 and "title" in json.loads(body)["error"].lower()


def test_suggest_answers_in_the_shape_the_form_expects(make):
    srv, _, events = make()
    st, _, body = call(srv, "POST", "/suggest", {"title": "Frasier", "region": "UK"},
                       {"X-Pages-User": "kate.kling@paramount.com"})
    data = json.loads(body)
    assert st == 200 and data["source"] == "combined" and "fields" in data and "notes" in data
    ev = next(e for e in events if e["event"] == "suggest")
    assert ev["user"] == "kate.kling@paramount.com" and ev["region"] == "UK"
    assert "brief" not in ev                                  # the pasted brief itself is never logged


# --- the Review step ----------------------------------------------------------------------------- #

def _plan():
    from test_qa_noise import UK_PLAN
    return dict(UK_PLAN)


def test_review_page_is_relative_safe_and_never_builds_html(make):
    srv, _, _ = make()
    st, hdr, body = call(srv, "GET", "/review")
    html = body.decode()
    assert st == 200 and "text/html" in hdr["Content-Type"]
    assert not re.search(r'(?:href|src|action)="/', html) and 'fetch("/' not in html
    assert "innerHTML" not in html and "document.write" not in html and "eval(" not in html
    assert 'fetch("api/review"' in html and "sessionStorage" in html
    assert "default-src 'none'" in hdr["Content-Security-Policy"]


def test_the_home_page_links_to_review(make):
    srv, _, _ = make()
    assert 'href="review"' in call(srv, "GET", "/")[2].decode()


def test_review_returns_the_preview_and_never_calls_freewheel(make, monkeypatch):
    from promo_ops.integrations.freewheel import FreeWheelClient

    def boom(*a, **k):
        raise AssertionError("review must not touch FreeWheel")
    monkeypatch.setattr(FreeWheelClient, "__init__", boom)
    srv, aud, events = make()
    st, _, body = call(srv, "POST", "/api/review", {"plan": _plan()},
                       {"X-Pages-User": "kate.kling@paramount.com"})
    data = json.loads(body)
    assert st == 200 and data["ok"] and data["summary"]["brand"] == "paramount_plus_uk" and data["placements"]
    assert aud.calls == []
    ev = next(e for e in events if e["event"] == "review")
    assert ev["user"] == "kate.kling@paramount.com" and ev["ok"] is True and ev["placements"] > 0
    assert "Frasier" not in json.dumps(events) and "showlist" not in json.dumps(events)   # no plan content logged


def test_review_reports_plan_problems_as_data_not_errors(make):
    srv, _, _ = make()
    st, _, body = call(srv, "POST", "/api/review", {"plan": {**_plan(), "promoted_title": ""}})
    data = json.loads(body)
    assert st == 200 and data["ok"] is False and any("Promoted Title" in p for p in data["problems"])


@pytest.mark.parametrize("payload", [{}, {"plan": "x"}, {"plan": [1]}, {"plan": None}])
def test_review_needs_a_plan_object(make, payload):
    srv, _, _ = make()
    st, _, body = call(srv, "POST", "/api/review", payload)
    assert st == 400 and "plan" in json.loads(body)["error"].lower()


def test_review_refuses_oversized_and_malformed_bodies(make):
    srv, _, _ = make()
    assert call(srv, "POST", "/api/review", b"x" * (webapp.MAX_REVIEW_BODY + 10),
                {"Content-Type": "application/json"})[0] == 413
    assert call(srv, "POST", "/api/review", b"{nope", {"Content-Type": "application/json"})[0] == 400


def test_review_respects_the_group_allow_list(make):
    srv, _, _ = make(allowed_groups=["Promo Operations Team"])
    assert call(srv, "POST", "/api/review", {"plan": _plan()})[0] == 403
    assert call(srv, "GET", "/review")[0] == 403
    ok = {"X-Pages-Groups": '"Promo Operations Team"'}
    assert call(srv, "POST", "/api/review", {"plan": _plan()}, ok)[0] == 200


def test_home_shows_who_you_are_and_your_groups_so_the_group_name_can_be_checked(make):
    srv, _, _ = make()
    st, _, body = call(srv, "GET", "/", headers={"X-Pages-User": "kate@x.com",
                                                 "X-Pages-Groups": '"Promo Operations Team", "<b>x</b>"'})
    html = body.decode()
    assert "kate@x.com" in html and "Promo Operations Team" in html
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_the_form_offers_review_only_when_served_by_the_app():
    from promo_ops.config import REPO_ROOT
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    assert 'id="reviewBtn"' in form and 'sessionStorage.setItem("promo_plan"' in form
    assert r"/\/form$/" in form                      # hidden everywhere except the app's /form


# --- request list + block, as the site shows them -------------------------------------------------- #

def test_review_carries_the_request_list_for_shows_without_a_regional_segment(make):
    from test_qa_noise import UK_PLAN
    srv, _, _ = make()
    plan = {**UK_PLAN, "showlist": ["Zzz Not A Real Show"]}
    data = json.loads(call(srv, "POST", "/api/review", {"plan": plan})[2])
    assert data["blocked"] is True and data["ok"] is False
    assert data["requests"] == [{"show": "Zzz Not A Real Show", "region": "UK",
                                 "status": "no segment anywhere", "exists_as": ""}]
    assert data["placements"] and data["summary"]["io_name"]        # still shows the whole plan


def test_a_fully_covered_plan_has_an_empty_request_list(make):
    srv, _, _ = make()
    data = json.loads(call(srv, "POST", "/api/review", {"plan": _plan()})[2])
    assert data["ok"] is True and data["blocked"] is False and data["requests"] == []


def test_review_page_offers_the_csv_and_neutralises_spreadsheet_formulas(make):
    srv, _, _ = make()
    html = call(srv, "GET", "/review")[2].decode()
    assert "Download request list" in html and "text/csv" in html
    assert "innerHTML" not in html
    assert r"/^[=+\-@\t\r]/" in html          # a show name starting with = + - @ can't run as a formula


def test_the_denied_page_says_which_groups_the_app_actually_received(make):
    srv, _, events = make(allowed_groups=["Promo Operations Team"])
    st, _, body = call(srv, "GET", "/qa", headers={"X-Pages-User": "kate@x.com",
                                                   "X-Pages-Groups": '"Promo Ops", "<i>x</i>"'})
    data = json.loads(body)
    assert st == 403
    assert data["received_groups"] == ["Promo Ops", "<i>x</i>"] and data["required_groups"] == ["Promo Operations Team"]
    denied = next(e for e in events if e["event"] == "denied")
    assert denied["groups"] == ["Promo Ops", "<i>x</i>"]
    assert call(srv, "GET", "/qa")[0] == 403           # no header at all: still denied, with an empty list


def test_the_form_button_says_it_can_create_and_the_review_can_go_back_to_edit(make):
    from promo_ops.config import REPO_ROOT
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    assert "Review &amp; create in tool" in form
    assert 'sessionStorage.getItem("promo_plan_back")' in form and "loadPlan(JSON.parse(back))" in form
    srv, _, _ = make()
    html = call(srv, "GET", "/review")[2].decode()
    assert 'sessionStorage.setItem("promo_plan_back"' in html and 'location.href = "form"' in html


def test_on_the_app_the_review_and_create_button_replaces_the_download_and_slack_buttons():
    from promo_ops.config import REPO_ROOT
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    block = form[form.index('if(/\\/form$/.test(location.pathname))'):][:700]
    assert '$("#dlBtn").hidden=true' in block and '$("#slackBtn").hidden=true' in block
    assert 'id="dlBtn"' in form and 'id="slackBtn"' in form          # still there for the standalone copy


def test_a_standalone_copy_of_the_form_tells_people_where_the_real_tool_is():
    from promo_ops.config import REPO_ROOT
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    assert "https://promo-ops-tools.skydancepages.cloud/form" in form
    i = form.index('if(/\\/form$/.test(location.pathname))')
    assert "else{" in form[i:i + 1500] and "document.body.prepend" in form[i:i + 1500]
    assert "innerHTML" not in form[i:i + 1500]


def test_the_form_address_with_a_trailing_slash_goes_to_the_form(make):
    import http.client
    srv, _, _ = make()
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    conn.request("GET", "/form/")
    resp = conn.getresponse()
    assert resp.status == 302 and resp.getheader("Location") == "../form" or resp.getheader("Location") == "/form"


def test_the_home_page_leads_with_the_form_where_orders_are_created(make):
    srv, _, _ = make()
    html = call(srv, "GET", "/")[2].decode()
    assert html.index('href="form"') < html.index('href="review"') < html.index('href="qa"')
    assert "create" in html[html.index('href="form"'):html.index('href="review"')].lower()
