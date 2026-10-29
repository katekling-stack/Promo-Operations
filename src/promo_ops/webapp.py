"""The hosted team app: paste an IO id -> QA report, plus the campaign form with its Suggest button.

    python -m promo_ops.webapp          # local try-out on http://127.0.0.1:8080/

Version 1 only READS from FreeWheel (the QA auditor's read calls); nothing here can create or change
an order. It runs as a Skydance Pages App (see docs/WEBAPP.md), where the platform handles sign-in
and puts the visitor in the X-Pages-User / X-Pages-Groups headers.

  * one QA run at a time (a QA of a big IO takes minutes) -- the page polls a job
  * every run is logged with who ran it
  * optional PROMO_ALLOWED_GROUPS allow-list on top of the platform's own access setting
  * pages use relative links so they work under any path prefix, and results are only ever shown
    with textContent (never built into HTML)

Settings (environment): FREEWHEEL_* (the QA login), PROMO_ALLOWED_GROUPS (optional, ';'-separated),
PORT / PROMO_WEBAPP_HOST (default 0.0.0.0 on Pages; 127.0.0.1 when run by hand).
"""

from __future__ import annotations

import csv
import html
import json
import os
import queue
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

MAX_IOS = 5                      # IO ids per run
MAX_QUEUED = 4                   # runs waiting + running before we say "busy"
MAX_QA_BODY = 16 * 1024
MAX_SUGGEST_BODY = 512 * 1024
MAX_REVIEW_BODY = 2 * 1024 * 1024
JOB_TTL = 3600                   # seconds a finished result stays available
MAX_JOBS = 200

_IO_ID = re.compile(r"^\d{5,12}$")

_HEADERS_COMMON = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                   "Cache-Control": "no-store"}
_CSP_QA = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
           "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; "
           "frame-ancestors 'self'")
_CSP_FORM = _CSP_QA            # the form is our own single file: inline script/style, posts to /suggest only


# --------------------------------------------------------------------------- #
#  who is calling / logging
# --------------------------------------------------------------------------- #
def groups_from_env(raw: Optional[str]) -> Optional[list[str]]:
    names = [g.strip() for g in (raw or "").split(";") if g.strip()]
    return names or None


def create_enabled_from_env(raw: Optional[str]) -> bool:
    """PROMO_ALLOW_CREATE: only an explicit yes turns on creating orders from the site."""
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def parse_groups(header: Optional[str]) -> list[str]:
    """X-Pages-Groups is a comma-separated list where a name containing a comma is quoted."""
    if not header:
        return []
    try:
        rows = list(csv.reader([header], skipinitialspace=True))
    except csv.Error:
        return []
    return [g.strip() for g in (rows[0] if rows else []) if g.strip()]


def _stdout_log(event: dict) -> None:
    print(json.dumps(event, default=str), flush=True)


# --------------------------------------------------------------------------- #
#  jobs
# --------------------------------------------------------------------------- #
class JobStore:
    """Bounded, expiring record of QA runs. Thread-safe."""

    def __init__(self, ttl: int = JOB_TTL, max_jobs: int = MAX_JOBS, now: Callable[[], float] = time.time):
        self.ttl, self.max_jobs, self._now = ttl, max_jobs, now
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _expire(self) -> None:
        cutoff = self._now() - self.ttl
        for jid in [j for j, v in self._jobs.items() if v["created"] < cutoff]:
            del self._jobs[jid]
        while len(self._jobs) > self.max_jobs:
            del self._jobs[min(self._jobs, key=lambda j: self._jobs[j]["created"])]

    def create(self, ios: list[str], include_completed: bool, user: str, kind: str = "qa") -> dict:
        with self._lock:
            job = {"id": uuid.uuid4().hex, "status": "queued", "io": list(ios), "all": include_completed,
                   "user": user, "created": self._now(), "reports": [], "error": None, "progress": 0,
                   "kind": kind, "result": None}
            self._jobs[job["id"]] = job
            self._expire()
            return job

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            self._expire()
            return self._jobs.get(job_id)

    def pending(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j["status"] in ("queued", "running"))

    def public(self, job: dict) -> dict:
        with self._lock:
            return {k: job[k] for k in ("id", "status", "io", "progress", "reports", "error", "result")}


def _plain(value: Any) -> Any:
    """JSON-safe copy of an expected/actual value."""
    return json.loads(json.dumps(value, default=str))


def report_json(rep) -> dict:
    counts = {lvl: len(rep.by_level(lvl)) for lvl in ("error", "warn", "info", "ok")}
    return {"io_id": rep.io_id, "io_name": rep.io_name, "brand": rep.brand, "region": rep.region,
            "placement_count": rep.placement_count, "completed_skipped": rep.completed_skipped,
            "error": rep.error, "counts": counts,
            "findings": [{"level": f.level, "category": f.category, "placement": f.placement,
                          "message": f.message, "expected": _plain(f.expected), "actual": _plain(f.actual)}
                         for f in rep.findings],
            "markdown": rep.markdown()}


def _xml_text(raw: Any) -> str:
    """FreeWheel's XML error body -> its plain message."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(raw or "")))
    return re.sub(r"\s+", " ", text).strip()[:300]


def summarize_create(res: dict) -> dict:
    """What a create_order() call did, in the few facts the page shows."""
    io = (res or {}).get("insertion_order") or {}
    io_id = (((io.get("data") or {}).get("insertion_order") or {}).get("id")) or io.get("append_to_existing_io")
    placements = [p for p in ((res or {}).get("placements") or []) if isinstance(p, dict)]
    bad = [p for p in placements if p.get("ok") is False or p.get("error")]
    return {"io_id": str(io_id) if io_id else None, "appended": bool(io.get("append_to_existing_io")),
            "placements_total": len(placements), "placements_created": len(placements) - len(bad),
            "placement_errors": [{"status": p.get("status_code"), "message": _xml_text(p.get("error"))} for p in bad],
            "brand": (res or {}).get("brand"), "brand_swapped": (res or {}).get("brand_swapped")}


def _friendly(exc: BaseException) -> str:
    if "Missing required env var" in str(exc):
        return ("The FreeWheel login isn't set up on this app yet. Ask whoever runs the app to add the "
                "FreeWheel login settings (see docs/WEBAPP.md).")
    return "Something went wrong starting the QA. Try again; if it keeps happening, tell the tool owner."


# --------------------------------------------------------------------------- #
#  the server
# --------------------------------------------------------------------------- #
class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, auditor_factory, allowed_groups, log, allow_create=False,
                 creator_factory=None):
        super().__init__(addr, handler)
        self.auditor_factory, self.allowed_groups, self.log = auditor_factory, allowed_groups, log
        self.allow_create, self.creator_factory = allow_create, creator_factory
        self._create_queue: "queue.Queue[str]" = queue.Queue()
        self._create_lock = threading.Lock()
        self._creating = False
        self.created: dict[str, dict] = {}          # plan hash -> {io_id, user, ts}: no second create of the same plan
        self.jobs = JobStore()
        self._auditor = None
        self._queue: "queue.Queue[str]" = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="qa-worker").start()
        threading.Thread(target=self._create_worker, daemon=True, name="create-worker").start()

    # one worker -> one QA at a time
    def _auditor_or_make(self):
        if self._auditor is None:
            self._auditor = self.auditor_factory()
        return self._auditor

    def submit(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _create_worker(self) -> None:
        from .order_builder import OrderBuilder
        from .plan_loader import support_plan_from_dict
        while True:
            job = self.jobs.get(self._create_queue.get())
            if job is None:
                with self._create_lock:
                    self._creating = False
                continue
            job["status"] = "running"
            user = job["user"]
            self.log({"event": "create_start", "user": user, "io_name": job["io"][0], "ts": time.time()})
            try:
                order = OrderBuilder().build(support_plan_from_dict(job["plan"]))
                creator = (self.creator_factory or _default_creator)()
                summary = summarize_create(creator.create_order(order, dry_run=False))
                job["result"], job["status"] = summary, "done"
                if summary["io_id"]:
                    self.created[job["plan_hash"]] = {"io_id": summary["io_id"], "user": user, "ts": time.time()}
                self.log({"event": "create_done", "user": user, "io_name": job["io"][0], "io_id": summary["io_id"],
                          "placements": summary["placements_created"], "of": summary["placements_total"],
                          "ts": time.time()})
            except RuntimeError as exc:            # refusals the tool writes itself (checks, FreeWheel said no)
                job["error"], job["status"] = _xml_text(exc) or "FreeWheel refused the order.", "error"
                self.log({"event": "create_failed", "user": user, "io_name": job["io"][0], "why": "refused"})
            except Exception as exc:  # noqa: BLE001 - never show internals
                job["error"], job["status"] = "Something went wrong creating the order. Nothing more was done; check FreeWheel before trying again.", "error"
                self.log({"event": "create_failed", "user": user, "io_name": job["io"][0], "why": type(exc).__name__})
            finally:
                with self._create_lock:
                    self._creating = False

    def _worker(self) -> None:
        while True:
            job = self.jobs.get(self._queue.get())
            if job is None:
                continue
            job["status"] = "running"
            user, errors, warns = job["user"], 0, 0
            self.log({"event": "qa_start", "user": user, "io": job["io"], "all": job["all"], "ts": time.time()})
            try:
                auditor = self._auditor_or_make()
            except Exception as exc:  # noqa: BLE001 - never show internals to the page
                job["error"], job["status"] = _friendly(exc), "error"
                self.log({"event": "qa_failed", "user": user, "io": job["io"], "why": type(exc).__name__})
                continue
            for io_id in job["io"]:
                try:
                    rep = report_json(auditor.audit_io(io_id, include_completed=job["all"]))
                except Exception as exc:  # noqa: BLE001
                    rep = {"io_id": io_id, "io_name": "", "brand": None, "region": None,
                           "placement_count": 0, "completed_skipped": 0, "findings": [], "markdown": "",
                           "counts": {"error": 0, "warn": 0, "info": 0, "ok": 0},
                           "error": f"Couldn't run QA on IO {io_id}. Check the id, or try again."}
                    self.log({"event": "qa_failed", "user": user, "io": [io_id], "why": type(exc).__name__})
                errors += rep["counts"]["error"]
                warns += rep["counts"]["warn"]
                job["reports"].append(rep)
                job["progress"] = len(job["reports"])
            job["status"] = "done"
            self.log({"event": "qa_done", "user": user, "io": job["io"], "errors": errors,
                      "warnings": warns, "ts": time.time()})


class Handler(BaseHTTPRequestHandler):
    server: _Server

    # -- plumbing --------------------------------------------------------- #
    def _user(self) -> str:
        return (self.headers.get("X-Pages-User") or "").strip() or "anonymous"

    def _send(self, code: int, body, ctype: str = "application/json", csp: Optional[str] = None) -> None:
        data = body if isinstance(body, bytes) else (
            body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in _HEADERS_COMMON.items():
            self.send_header(k, v)
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self) -> bool:
        allowed = self.server.allowed_groups
        if not allowed:
            return True
        got = parse_groups(self.headers.get("X-Pages-Groups"))
        mine = set(got)
        if mine & set(allowed):
            return True
        self.server.log({"event": "denied", "user": self._user(), "path": self.path.split("?")[0],
                         "groups": got, "ts": time.time()})
        self._send(403, {"error": "You're not in a group that can use this tool. Ask the tool owner.",
                         "received_groups": got, "required_groups": list(allowed)})
        return False

    def _read_json(self, limit: int) -> Optional[dict]:
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            n = -1
        if n < 0 or n > limit:
            # read (and discard) a bounded amount first, so the sender sees the 413 instead of a reset
            left = min(max(n, 0), 16 * 1024 * 1024)
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            self.close_connection = True
            self._send(413, {"error": "That request is too large."})
            return None
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "Couldn't read that request."})
            return None
        if not isinstance(body, dict):
            self._send(400, {"error": "Couldn't read that request."})
            return None
        return body

    def log_message(self, *a) -> None:   # the structured log is ours
        pass

    # -- routes ------------------------------------------------------------ #
    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self._send(200, b"ok\n", "text/plain")
        if not self._allowed():
            return
        if path == "/":
            return self._send(200, _home_html(self._user(), parse_groups(self.headers.get("X-Pages-Groups"))), "text/html; charset=utf-8", _CSP_QA)
        if path == "/qa":
            return self._send(200, QA_PAGE, "text/html; charset=utf-8", _CSP_QA)
        if path == "/review":
            return self._send(200, REVIEW_PAGE, "text/html; charset=utf-8", _CSP_QA)
        if path == "/form/":
            self.send_response(302)
            self.send_header("Location", "../form")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in ("/form", "/index.html"):
            from .suggest_server import FORM
            if not FORM.exists():
                return self._send(500, {"error": "The form hasn't been built yet."})
            return self._send(200, FORM.read_bytes(), "text/html; charset=utf-8", _CSP_FORM)
        m = re.fullmatch(r"/api/(?:qa|create)/([0-9a-f]{32}|[\w-]{1,64})", path)
        if m:
            job = self.server.jobs.get(m.group(1))
            if job is None:
                return self._send(404, {"error": "That run has expired. Start it again."})
            return self._send(200, self.server.jobs.public(job))
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/api/qa", "/api/review", "/api/create", "/suggest"):
            return self._send(404, {"error": "not found"})
        if not self._allowed():
            return
        if path == "/api/qa":
            return self._post_qa()
        if path == "/api/review":
            return self._post_review()
        if path == "/api/create":
            return self._post_create()
        return self._post_suggest()

    def _post_create(self) -> None:
        srv = self.server
        if not srv.allow_create:
            return self._send(403, {"error": "Creating orders from the site is switched off right now."})
        user = self._user()
        if user == "anonymous":
            return self._send(403, {"error": "You need to be signed in to create an order."})
        body = self._read_json(MAX_REVIEW_BODY)
        if body is None:
            return
        plan, plan_hash, confirm = body.get("plan"), body.get("plan_hash"), body.get("confirm")
        if not isinstance(plan, dict) or not plan or not isinstance(plan_hash, str):
            return self._send(400, {"error": "Send the plan, its review fingerprint and the typed confirmation."})
        from .review import review_plan
        result = review_plan(plan)
        if not result["ok"]:
            return self._send(409, {"error": "This plan can't be created yet: " + " ".join(result["problems"]),
                                    "problems": result["problems"]})
        if result["plan_hash"] != plan_hash:
            return self._send(409, {"error": "The plan changed since you reviewed it. Review it again, then create."})
        io_name = result["summary"]["io_name"]
        if not isinstance(confirm, str) or confirm != io_name:
            return self._send(400, {"error": f"Type the IO name exactly to confirm: {io_name}"})
        with srv._create_lock:
            prior = srv.created.get(plan_hash)
            if prior:
                return self._send(409, {"error": f"This plan already created IO {prior['io_id']} (by {prior['user']}). "
                                                 "To add lines to it, use 'Add to existing IO' in the form."})
            if srv._creating:
                return self._send(429, {"error": "Another order is being created right now. Try again in a minute."})
            srv._creating = True
        job = srv.jobs.create([io_name], False, user, kind="create")
        job["plan"], job["plan_hash"] = plan, plan_hash
        srv._create_queue.put(job["id"])
        self._send(200, {"job": job["id"]})

    def _post_review(self) -> None:
        body = self._read_json(MAX_REVIEW_BODY)
        if body is None:
            return
        plan = body.get("plan")
        if not isinstance(plan, dict) or not plan:
            return self._send(400, {"error": "Send the plan file's contents as {\"plan\": {...}}."})
        from .review import review_plan
        result = review_plan(plan)
        self.server.log({"event": "review", "user": self._user(), "ok": bool(result["ok"]),
                         "placements": len(result["placements"]), "region": plan.get("region"),
                         "ts": time.time()})
        result["create_enabled"] = bool(self.server.allow_create)
        self._send(200, result)

    def _post_qa(self) -> None:
        body = self._read_json(MAX_QA_BODY)
        if body is None:
            return
        raw = body.get("io")
        if not isinstance(raw, list):
            return self._send(400, {"error": "Give me one or more IO ids."})
        ios: list[str] = []
        for item in raw:
            s = str(item).strip() if isinstance(item, (str, int)) and not isinstance(item, bool) else ""
            if not _IO_ID.match(s):
                return self._send(400, {"error": f"“{str(item)[:20]}” doesn't look like an IO id "
                                                 "(it's the number in the FreeWheel URL, 5 to 12 digits)."})
            if s not in ios:
                ios.append(s)
        if not ios:
            return self._send(400, {"error": "Give me one or more IO ids."})
        if len(ios) > MAX_IOS:
            return self._send(400, {"error": f"That's a lot at once. {MAX_IOS} IOs at a time, please."})
        if self.server.jobs.pending() >= MAX_QUEUED:
            return self._send(429, {"error": "The QA is busy with other runs. Try again in a few minutes."})
        job = self.server.jobs.create(ios, bool(body.get("all")), self._user())
        self.server.submit(job["id"])
        self._send(200, {"job": job["id"]})

    def _post_suggest(self) -> None:
        body = self._read_json(MAX_SUGGEST_BODY)
        if body is None:
            return
        title = str(body.get("title") or "").strip()
        region = str(body.get("region") or "USA").strip() or "USA"
        if not title:
            return self._send(400, {"error": "Enter a promoted title first."})
        from . import suggest as _suggest
        from .suggest_server import _combined_json, _corpus
        self.server.log({"event": "suggest", "user": self._user(), "region": region, "title": title[:120],
                         "ts": time.time()})
        try:
            result = _suggest.combine_targeting(
                title, region, brief_text=str(body.get("brief_text") or "").strip() or None,
                description=str(body.get("description") or "").strip() or None, corpus=_corpus())
        except Exception as exc:  # noqa: BLE001
            self.server.log({"event": "suggest_failed", "user": self._user(), "why": type(exc).__name__})
            return self._send(500, {"error": "The suggester ran into a problem. Try again."})
        self._send(200, _combined_json(result, bool(os.environ.get("ANTHROPIC_API_KEY"))))


def _default_creator():
    from .integrations.freewheel import FreeWheelClient
    return FreeWheelClient()


def make_server(host: str, port: int, auditor_factory: Optional[Callable[[], Any]] = None,
                allowed_groups: Optional[list[str]] = None,
                log: Callable[[dict], None] = _stdout_log, allow_create: bool = False,
                creator_factory: Optional[Callable[[], Any]] = None) -> _Server:
    if auditor_factory is None:
        def auditor_factory():
            from .qa import QAAuditor
            return QAAuditor()
    return _Server((host, port), Handler, auditor_factory, allowed_groups, log, allow_create, creator_factory)


# --------------------------------------------------------------------------- #
#  pages (relative links only; results rendered with textContent only)
# --------------------------------------------------------------------------- #
_STYLE = """
body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#1d2433;background:#f6f7fb}
main{max-width:920px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px} p.sub{color:#5b667a;margin:0 0 22px}
a.card{display:block;background:#fff;border:1px solid #dde2ee;border-radius:10px;padding:16px 18px;margin:0 0 12px;
text-decoration:none;color:inherit} a.card:hover{border-color:#0064ff} a.card b{display:block;font-size:16px;color:#0050cc}
textarea,input[type=text]{width:100%;box-sizing:border-box;border:1px solid #c8cfdf;border-radius:8px;padding:10px;font:inherit}
button{background:#0064ff;color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer}
button[disabled]{opacity:.5;cursor:default} button.ghost{background:#fff;color:#0050cc;border:1px solid #c8cfdf}
.row{display:flex;gap:12px;align-items:center;margin:12px 0} .muted{color:#5b667a;font-size:13px}
.io{background:#fff;border:1px solid #dde2ee;border-radius:10px;padding:16px 18px;margin:16px 0}
.io h2{font-size:17px;margin:0 0 2px} .pill{display:inline-block;border-radius:99px;padding:1px 10px;font-size:12px;margin-right:6px}
.error{background:#fde8e8;color:#9b1c1c}.warn{background:#fff3d6;color:#7a5200}.info{background:#e6efff;color:#1d4ba3}
.ok{background:#e3f6e8;color:#1a6b34} .pl{margin:12px 0 0;font-weight:600;font-size:14px}
.f{margin:3px 0 0 14px;font-size:14px} .f small{color:#5b667a}
.banner{background:#fde8e8;color:#9b1c1c;border-radius:8px;padding:10px 14px;margin:12px 0}
"""


def _home_html(user: str, groups=()) -> str:
    who = ""
    if user != "anonymous":
        grp = ", ".join(html.escape(g) for g in groups) or "none"
        who = f'<p class="muted">Signed in as {html.escape(user)} &middot; groups: {grp}</p>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Promo Ad Ops tools</title>
<style>{_STYLE}</style></head><body><main>
<h1>Promo Ad Ops tools</h1><p class="sub">Check an order, or plan a campaign. Nothing here changes FreeWheel.</p>
{who}
<a class="card" href="form"><b>Campaign plan form: create an order</b>Fill out a plan, review what it will build, and create it in FreeWheel. Start here for a new order.</a>
<a class="card" href="review"><b>Review a plan</b>Check a plan file before anything is created: what it would build, and any Tier 1 audience alerts.</a>
<a class="card" href="qa"><b>QA an order</b>Paste an IO id and get the QA report, same as the command line gives.</a>
</main></body></html>"""


QA_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>QA an order</title>
<style>""" + _STYLE + """</style></head><body><main>
<p class="muted"><a href=".">&larr; All tools</a></p>
<h1>QA an order</h1>
<p class="sub">Paste the IO id (the number in the FreeWheel URL). Up to 5, one per line or separated by commas.
A big order can take a few minutes; leave this page open.</p>
<textarea id="ids" rows="3" placeholder="86085716"></textarea>
<div class="row"><label><input type="checkbox" id="all"> Include placements that already finished</label></div>
<div class="row"><button id="go">Run QA</button><span class="muted" id="status"></span></div>
<div id="out"></div>
<script>
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
let busy = false;
function setStatus(t){ $("status").textContent = t; }
function banner(t){ const b = el("div","banner",t); $("out").prepend(b); }
function render(reports){
  const out = $("out"); out.textContent = "";
  reports.forEach(r => {
    const box = el("div","io");
    box.appendChild(el("h2", null, "IO " + r.io_id + (r.io_name ? " \\u2014 " + r.io_name : "")));
    const meta = [r.brand && ("brand: " + r.brand), r.region && ("region: " + r.region), r.placement_count + " placement(s)"].filter(Boolean).join(" \\u00b7 ");
    box.appendChild(el("div","muted",meta));
    if (r.error){ box.appendChild(el("div","banner",r.error)); out.appendChild(box); return; }
    const pills = el("div"); pills.style.margin = "10px 0";
    [["error","error(s)"],["warn","warning(s)"],["info","note(s)"]].forEach(([k,l]) => pills.appendChild(el("span","pill "+k, r.counts[k]+" "+l)));
    box.appendChild(pills);
    if (!r.counts.error && !r.counts.warn) box.appendChild(el("div","pill ok","Nothing to fix \\u2014 looks good"));
    if (r.completed_skipped) box.appendChild(el("div","muted", r.completed_skipped + " finished placement(s) weren't checked (tick the box above to include them)."));
    const groups = {};
    r.findings.filter(f => f.level !== "ok").forEach(f => { (groups[f.placement] = groups[f.placement] || []).push(f); });
    const rank = {error:0,warn:1,info:2};
    Object.keys(groups).sort((a,b) => Math.min(...groups[a].map(f=>rank[f.level])) - Math.min(...groups[b].map(f=>rank[f.level])) || a.localeCompare(b)).forEach(name => {
      box.appendChild(el("div","pl",name));
      groups[name].sort((a,b)=>rank[a.level]-rank[b.level]).forEach(f => {
        const line = el("div","f"); line.appendChild(el("span","pill "+f.level,f.level));
        let t = "[" + f.category + "] " + f.message;
        if (f.expected !== null || f.actual !== null) t += "  (expected " + JSON.stringify(f.expected) + ", got " + JSON.stringify(f.actual) + ")";
        line.appendChild(document.createTextNode(t)); box.appendChild(line);
      });
    });
    const copy = el("button","ghost","Copy report"); copy.style.marginTop = "14px";
    copy.onclick = () => navigator.clipboard.writeText(r.markdown).then(() => { copy.textContent = "Copied"; });
    box.appendChild(copy); out.appendChild(box);
  });
}
async function poll(job){
  for (;;){
    await new Promise(r => setTimeout(r, 2000));
    let res; try { res = await fetch("api/qa/" + job); } catch(e){ setStatus("Lost the connection, retrying\\u2026"); continue; }
    if (res.status === 404){ setStatus(""); banner("That run expired. Start it again."); return; }
    const d = await res.json();
    if (d.reports && d.reports.length) render(d.reports);
    if (d.status === "done"){ setStatus("Done."); return; }
    if (d.status === "error"){ setStatus(""); banner(d.error || "That run failed."); return; }
    setStatus("Checking\\u2026 " + (d.progress || 0) + " of " + d.io.length + " done");
  }
}
$("go").onclick = async () => {
  if (busy) return;
  const ids = $("ids").value.split(/[\\s,;]+/).filter(Boolean);
  if (!ids.length){ setStatus("Paste an IO id first."); return; }
  busy = true; $("go").disabled = true; $("out").textContent = ""; setStatus("Starting\\u2026");
  try {
    const res = await fetch("api/qa", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({io: ids, all: $("all").checked})});
    const d = await res.json();
    if (!res.ok){ setStatus(""); banner(d.error || ("Error " + res.status)); }
    else await poll(d.job);
  } catch(e){ setStatus(""); banner("Couldn't reach the tool. Are you on the VPN?"); }
  busy = false; $("go").disabled = false;
};
</script></main></body></html>"""


REVIEW_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Review a plan</title>
<style>""" + _STYLE + """
details{margin:8px 0;border:1px solid #e3e7f1;border-radius:8px;padding:8px 12px;background:#fbfcff}
summary{cursor:pointer;font-weight:600} .tier{margin:8px 0 0 10px;font-size:14px}
.dim{margin:2px 0 0 14px;font-size:13px;color:#2b3446}.note{color:#7a5200;margin-left:28px;font-size:13px;white-space:pre-wrap}
</style></head><body><main>
<p class="muted"><a href=".">&larr; All tools</a></p>
<h1>Review a plan</h1>
<p class="sub">This shows what pushing the plan would build and any Tier 1 audience alerts.
<b>Nothing is created in FreeWheel.</b></p>
<div id="src"></div>
<div class="row"><input type="file" id="file" accept=".json,application/json">
<span class="muted">or paste the plan file's contents:</span></div>
<textarea id="paste" rows="3" placeholder='{"promoted_title": ...}'></textarea>
<div class="row"><button id="go">Review</button><span class="muted" id="status"></span></div>
<div id="out"></div>
<script>
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
function setStatus(t){ $("status").textContent = t; }
function banner(t){ $("out").prepend(el("div","banner",t)); }
function render(r){
  const out = $("out"); out.textContent = "";
  if (r.problems && r.problems.length){
    const b = el("div","banner",r.blocked ? "Blocked \\u2014 this plan can't be pushed yet:" : "This plan can't be pushed yet:");
    r.problems.forEach(p => { b.appendChild(el("div", null, "\\u2022 " + p)); }); out.appendChild(b);
    if (!r.summary || !r.summary.io_name) return;
  }
  const s = r.summary, box = el("div","io");
  if (lastPlan){
    const back = el("button","ghost","Back to the form to edit"); back.style.float = "right";
    back.onclick = () => { sessionStorage.setItem("promo_plan_back", JSON.stringify(lastPlan)); location.href = "form"; };
    box.appendChild(back);
  }
  box.appendChild(el("h2", null, s.io_name));
  box.appendChild(el("div","muted",[s.advertiser && ("advertiser: " + s.advertiser), "campaign: " + s.campaign, "brand: " + s.brand, "region: " + s.region, "flight: " + s.flight].filter(Boolean).join(" \\u00b7 ")));
  box.appendChild(el("div",null,s.placements + " placement(s) would be added to " + s.destination + "."));
  const pills = el("div"); pills.style.margin = "10px 0";
  pills.appendChild(el("span","pill " + (r.alerts.length ? "warn" : "ok"), r.alerts.length ? r.alerts.length + " Tier 1 audience alert(s)" : "No Tier 1 audience alerts"));
  box.appendChild(pills);
  r.alerts.forEach(a => box.appendChild(el("div","f","\\u26a0 " + a)));
  if (r.requests && r.requests.length){
    const dl = el("button","ghost","Download request list (" + r.requests.length + " shows)"); dl.style.marginTop = "12px";
    dl.onclick = () => downloadRequests(r.requests);
    box.appendChild(dl);
  }
  out.appendChild(box);
  if (r.ok && r.create_enabled) out.appendChild(createPanel(r));
  r.placements.forEach(p => {
    const d = el("details"); d.appendChild(el("summary", null, p.name));
    const meta = ["format: " + p.format, p.priority != null && ("priority: " + p.priority), p.frequency_cap && ("cap: " + JSON.stringify(p.frequency_cap)), p.guaranteed && "guaranteed", p.exclusions.length && ("excludes: " + p.exclusions.join(", "))].filter(Boolean).join(" \\u00b7 ");
    d.appendChild(el("div","muted",meta));
    p.tiers.forEach(t => {
      const tb = el("div","tier"); tb.appendChild(el("b", null, "Tier " + t.id + " \\u2014 " + t.name));
      t.dimensions.forEach(x => {
        tb.appendChild(el("div","dim", x.key + ": " + x.count + (x.preview.length ? " [" + x.preview.join(", ") + (x.more ? " +" + x.more + " more" : "") + "]" : "")));
        if (x.notes) tb.appendChild(el("div","note",x.notes));
      });
      d.appendChild(tb);
    });
    out.appendChild(d);
  });
}
function createPanel(r){
  const box = el("div","io");
  box.appendChild(el("h2", null, "Create in FreeWheel"));
  box.appendChild(el("div","muted","This creates the IO and its " + r.summary.placements + " placement(s) in FreeWheel for real, as a draft. Check the review above first."));
  const nm = el("div","f", r.summary.io_name); nm.style.fontWeight = "600"; nm.style.margin = "10px 0 6px";
  box.appendChild(nm);
  const inp = document.createElement("input"); inp.type = "text"; inp.placeholder = "Type the IO name exactly, to confirm";
  box.appendChild(inp);
  const row = el("div","row"); const btn = el("button", null, "Create in FreeWheel"); const st = el("span","muted","");
  row.appendChild(btn); row.appendChild(st); box.appendChild(row);
  const res = el("div"); box.appendChild(res);
  btn.onclick = async () => {
    res.textContent = "";
    if (inp.value !== r.summary.io_name){ st.textContent = "Type the IO name exactly as shown above."; return; }
    btn.disabled = true; st.textContent = "Creating\\u2026 this can take a minute.";
    try {
      const resp = await fetch("api/create", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({plan: lastPlan, plan_hash: r.plan_hash, confirm: inp.value})});
      const d = await resp.json();
      if (!resp.ok){ st.textContent = ""; res.appendChild(el("div","banner", d.error || ("Error " + resp.status))); btn.disabled = false; return; }
      for (;;){
        await new Promise(x => setTimeout(x, 2000));
        const pr = await fetch("api/create/" + d.job);
        if (pr.status === 404){ st.textContent = ""; res.appendChild(el("div","banner","That run expired. Check FreeWheel before trying again.")); return; }
        const j = await pr.json();
        if (j.status === "done"){ st.textContent = ""; showCreated(res, j.result); return; }
        if (j.status === "error"){ st.textContent = ""; res.appendChild(el("div","banner", j.error || "That didn't work.")); btn.disabled = false; return; }
      }
    } catch(e){ st.textContent = ""; res.appendChild(el("div","banner","Lost the connection. Check FreeWheel before trying again, so nothing is created twice.")); }
  };
  return box;
}
function showCreated(res, c){
  const ok = c.placements_created === c.placements_total;
  res.appendChild(el("div", "pill " + (ok ? "ok" : "warn"), (c.appended ? "Added to IO " : "Created IO ") + c.io_id + ": " + c.placements_created + " of " + c.placements_total + " placement(s)"));
  (c.placement_errors || []).forEach(x => res.appendChild(el("div","f","\\u26a0 " + (x.status || "") + " " + x.message)));
  if (c.brand && c.brand.created) res.appendChild(el("div","f","Brand created: " + c.brand.name + (c.brand.brand_id ? " (id " + c.brand.brand_id + ")" : "")));
  if (c.brand_swapped) res.appendChild(el("div","f","Brand changed to match the campaign: " + c.brand_swapped.why));
  res.appendChild(el("div","muted","Next: run QA on IO " + c.io_id + " (QA an order, from the home page)."));
}
function csvCell(v){
  let t = String(v == null ? "" : v);
  if (/^[=+\\-@\\t\\r]/.test(t)) t = "'" + t;          // a show name can't run as a spreadsheet formula
  return '"' + t.replace(/"/g, '""') + '"';
}
function downloadRequests(rows){
  const lines = [["show","region","status","exists_as"].map(csvCell).join(",")]
    .concat(rows.map(x => [x.show, x.region, x.status, x.exists_as].map(csvCell).join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\\r\\n") + "\\r\\n"], {type: "text/csv"}));
  a.download = "segments-to-request.csv"; a.click();
}
let lastPlan = null;
async function review(plan){
  lastPlan = plan;
  $("out").textContent = ""; setStatus("Checking\\u2026"); $("go").disabled = true;
  try {
    const res = await fetch("api/review", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({plan})});
    const d = await res.json();
    if (!res.ok) banner(d.error || ("Error " + res.status)); else render(d);
    setStatus("");
  } catch(e){ setStatus(""); banner("Couldn't reach the tool. Are you on the VPN?"); }
  $("go").disabled = false;
}
function fromText(t){
  let plan; try { plan = JSON.parse(t); } catch(e){ banner("That isn't a plan file (it should be the .plan.json from the form)."); return; }
  review(plan);
}
$("file").onchange = () => { const f = $("file").files[0]; if (f) f.text().then(fromText); };
$("go").onclick = () => { const t = $("paste").value.trim(); if (t) fromText(t); else setStatus("Choose a plan file or paste it first."); };
const saved = sessionStorage.getItem("promo_plan");
if (saved){ $("src").appendChild(el("p","muted","Reviewing the plan you just filled out in the form.")); sessionStorage.removeItem("promo_plan"); fromText(saved); }
</script></main></body></html>"""


def main(argv: Optional[list[str]] = None) -> int:
    host = os.environ.get("PROMO_WEBAPP_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    groups = groups_from_env(os.environ.get("PROMO_ALLOWED_GROUPS"))
    allow = create_enabled_from_env(os.environ.get("PROMO_ALLOW_CREATE"))
    srv = make_server(host, port, allowed_groups=groups, allow_create=allow)
    print(f"promo-ops web app on http://{host}:{port}/  (groups: {', '.join(groups) if groups else 'any signed-in user'}; "
          f"creating orders from the site: {'ON' if allow else 'off'})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
