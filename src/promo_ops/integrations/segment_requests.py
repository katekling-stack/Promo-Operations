"""Submit DDA audience-segment requests to the Ad Ops "Audience Segment Request" tool
(a Google Apps Script web app) so the tool can request missing segments in one step.

IMPORTANT — the deployed web app only exposes the in-page `google.script.run` RPC, which is
NOT callable from outside the served page. To POST from here, the Apps Script needs a small
`doPost(e)` added (see docs/DDA_REQUESTS.md), and the endpoint must be reachable:
  * deployed "Anyone" (no auth), or
  * a Google OAuth bearer token for a paramount.com user via DDA_REQUEST_TOKEN.

Config:
  DDA_REQUEST_URL    the Apps Script /exec URL
  DDA_REQUEST_TOKEN  (optional) OAuth bearer token if the app requires Paramount auth
"""

from __future__ import annotations

import json
import os
from typing import Optional

import requests


def submit_request(payload: dict, url: Optional[str] = None, token: Optional[str] = None,
                   timeout: int = 30) -> dict:
    """POST one request payload to the Apps Script tool. Returns the tool's JSON response
    ({status:'success', rows:[...]}) or raises a clear error."""
    url = url or os.environ.get("DDA_REQUEST_URL")
    if not url:
        raise RuntimeError(
            "No DDA request endpoint. Set DDA_REQUEST_URL to the Apps Script /exec URL "
            "(and add doPost to the script — see docs/DDA_REQUESTS.md).")
    headers = {"Content-Type": "application/json"}
    token = token or os.environ.get("DDA_REQUEST_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(url, data=json.dumps(payload), headers=headers, timeout=timeout,
                         allow_redirects=True)
    resp.raise_for_status()
    # A login redirect returns HTML, not JSON — surface that as an auth hint, not a crash.
    try:
        return resp.json()
    except ValueError:
        if "accounts.google.com" in resp.text or "<html" in resp.text.lower():
            raise RuntimeError(
                "The endpoint returned a login page, not JSON — the web app requires "
                "Paramount auth. Deploy it 'Anyone', or provide DDA_REQUEST_TOKEN.")
        return {"status": "ok", "raw": resp.text[:300]}


def submit_all(payloads: list[dict], url: Optional[str] = None, token: Optional[str] = None
               ) -> list[dict]:
    """Submit many requests; returns a per-request {payload, ok, result/error} list (never
    raises mid-batch — one failure doesn't abort the rest)."""
    out = []
    for p in payloads:
        try:
            out.append({"payload": p, "ok": True, "result": submit_request(p, url, token)})
        except Exception as exc:  # noqa: BLE001 - report per-item, keep going
            out.append({"payload": p, "ok": False, "error": str(exc)})
    return out
