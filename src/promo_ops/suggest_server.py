"""Local helper so the campaign form's "✨ Suggest targeting" button can call the AI
affinity engine WITHOUT ever putting an API key in the browser.

    python -m promo_ops.suggest_server        # then open http://127.0.0.1:8770/

It serves the form itself (so the page origin is http://127.0.0.1 and the button can POST
same-origin — no CORS / mixed-content issues) plus a small POST /suggest endpoint that runs
suggest_ai server-side with the key. Mirrors the FreeWheel Order Builder tool's server.py
pattern (static file + one POST endpoint). Config via env:

    ANTHROPIC_API_KEY   required for the AI engine
    AFFINITY_MODEL      optional model override (default claude-sonnet-5)
    PROMO_SUGGEST_PORT  optional port (default 8770)
    PROMO_PAST_PLANS    optional folder of *.plan.json to also blend in the history engine
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import REPO_ROOT
from . import suggest as _suggest

FORM = REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html"


def _suggestion_json(sug) -> dict:
    return {"source": sug.source, "notes": sug.notes,
            "fields": {f: {"matched": fp.matched, "review": fp.review, "missed": fp.missed}
                       for f, fp in sug.fields.items()}}


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
        region = (req.get("region") or "USA").strip() or "USA"
        if not title or not desc:
            return self._send(400, {"error": "Enter a promoted title and a short description first."})
        try:
            sug = _suggest.suggest_ai(title, desc, region)
        except Exception as exc:  # noqa: BLE001 - missing key/SDK or API error -> friendly 503
            return self._send(503, {"error": f"AI suggester unavailable: {exc}",
                                    "hint": "Set ANTHROPIC_API_KEY (and `pip install anthropic`) "
                                            "where this helper runs, then retry."})
        payload = _suggestion_json(sug)
        past = os.environ.get("PROMO_PAST_PLANS")
        if past and Path(past).exists():
            genres = payload["fields"].get("genres", {}).get("matched", [])
            hist = _suggest.suggest_history(title, genres, _suggest.load_past_plans(past))
            payload["history"] = _suggestion_json(hist)
        self._send(200, payload)

    def log_message(self, *a) -> None:   # quiet
        pass


def main(argv=None) -> int:
    port = int(os.environ.get("PROMO_SUGGEST_PORT", "8770"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    key = "set" if os.environ.get("ANTHROPIC_API_KEY") else "NOT set (AI calls will 503)"
    print(f"✨ Suggest helper on http://127.0.0.1:{port}/  (ANTHROPIC_API_KEY: {key})")
    print("   Open that URL, fill title + description, click ✨ Suggest targeting. Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
