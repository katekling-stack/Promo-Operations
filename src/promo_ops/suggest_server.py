"""Local (or shared-host) helper so the campaign form's "✨ Suggest targeting" button can
build grounded targeting WITHOUT ever putting an API key in the browser.

    python -m promo_ops.suggest_server        # then open http://127.0.0.1:8770/

It serves the form itself (so the page origin matches the helper and the button can POST
same-origin — no CORS / mixed-content issues) plus a POST /suggest endpoint that runs
combine_targeting() server-side: it layers every available signal — an optional pasted
brief, the AI engine (when a key is set), and the historicals corpus — and ranks by
agreement across them. It DEGRADES GRACEFULLY: with no ANTHROPIC_API_KEY it simply runs in
historicals(+brief)-only mode instead of failing, so the whole team can use it before/without
an API key. Point the whole team at ONE hosted instance (set PROMO_SUGGEST_HOST) and nobody
needs a local clone, Python, or key.

Config via env:

    ANTHROPIC_API_KEY    optional — enables the AI layer; absent -> historicals-only mode
    AFFINITY_MODEL       optional model override (default claude-sonnet-5)
    PROMO_SUGGEST_HOST   optional bind address (default 127.0.0.1; set 0.0.0.0 to host for a team)
    PROMO_SUGGEST_PORT   optional port (default 8770)
    PROMO_HISTORY_CORPUS optional corpus path (default data/history/corpus.jsonl)
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import REPO_ROOT
from . import suggest as _suggest

FORM = REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html"

_SRC_LABEL = {"brief": "brief", "history": "historicals", "ai": "AI"}

_CORPUS_CACHE = None


def _corpus() -> list:
    """Load (and cache) the historicals corpus the suggester learns from."""
    global _CORPUS_CACHE
    if _CORPUS_CACHE is None:
        from .history import load_corpus
        path = os.environ.get("PROMO_HISTORY_CORPUS") or (REPO_ROOT / "data" / "history" / "corpus.jsonl")
        _CORPUS_CACHE = load_corpus(path)
    return _CORPUS_CACHE


def _combined_json(result: dict, ai_on: bool) -> dict:
    """Map combine_targeting()'s {fields, provenance} into the shape the form renders,
    surfacing provenance so the CM can see WHY each value was suggested."""
    fields = {f: {"matched": vals, "review": [], "missed": []}
              for f, vals in result["fields"].items()}
    used = sorted({s for pv in result["provenance"].values()
                   for srcs in pv.values() for s in srcs},
                  key=lambda s: -_SRC_PRIORITY.get(s, 0))
    notes: list[str] = []
    if used:
        notes.append("Grounded from: " + ", ".join(_SRC_LABEL[s] for s in used) + ".")
    else:
        notes.append("No grounded matches for this title in this region yet.")
    if not ai_on:
        notes.append("AI layer off (no ANTHROPIC_API_KEY set on the helper) — suggestions "
                     "are from historicals" + (" + your brief" if "brief" in used else "") + ".")
    strong = []
    for pv in result["provenance"].values():
        for v, srcs in pv.items():
            if len(srcs) >= 2:
                strong.append(f"{v} ({'+'.join(_SRC_LABEL[s] for s in sorted(srcs))})")
    if strong:
        notes.append("Multiple sources agree on: " + ", ".join(strong[:12])
                     + ("…" if len(strong) > 12 else "") + ".")
    return {"source": "combined", "mode": "ai+historicals" if ai_on else "historicals",
            "fields": fields, "notes": notes, "provenance": result["provenance"]}


_SRC_PRIORITY = {"brief": 3, "history": 2, "ai": 1}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.split("?")[0] in ("/", "/index.html", "/form"):
            if FORM.exists():
                self._send(200, FORM.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(500, {"error": "form not built — run scripts/build_plan_form.py"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.split("?")[0].rstrip("/") != "/suggest":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, TypeError):
            return self._send(400, {"error": "bad JSON"})
        title = (req.get("title") or "").strip()
        desc = (req.get("description") or "").strip()
        brief = (req.get("brief_text") or "").strip()
        region = (req.get("region") or "USA").strip() or "USA"
        if not title:
            return self._send(400, {"error": "Enter a promoted title first."})
        ai_on = bool(os.environ.get("ANTHROPIC_API_KEY"))
        try:
            result = _suggest.combine_targeting(title, region, brief_text=brief or None,
                                                description=desc or None, corpus=_corpus())
        except Exception as exc:  # noqa: BLE001 - unexpected failure -> report, don't crash the helper
            return self._send(500, {"error": f"Suggester failed: {exc}"})
        self._send(200, _combined_json(result, ai_on))

    def log_message(self, *a) -> None:   # quiet
        pass


def main(argv=None) -> int:
    host = os.environ.get("PROMO_SUGGEST_HOST", "127.0.0.1")
    port = int(os.environ.get("PROMO_SUGGEST_PORT", "8770"))
    srv = ThreadingHTTPServer((host, port), Handler)
    ai = "on" if os.environ.get("ANTHROPIC_API_KEY") else "OFF — historicals-only mode"
    n = len(_corpus())
    shown = host if host != "0.0.0.0" else "<this-host>"
    print(f"✨ Suggest helper on http://{shown}:{port}/  (AI: {ai}; corpus: {n} plans)")
    if host == "0.0.0.0":
        print("   Bound on all interfaces — team can reach it at this host's address. "
              "Put it behind your VPN/SSO.")
    print("   Open that URL, fill title (+ description and/or paste a brief), click ✨ Suggest "
          "targeting. Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
