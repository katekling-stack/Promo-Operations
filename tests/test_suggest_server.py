"""The local helper server: serves the form and a POST /suggest that runs combine_targeting
server-side (key never in the browser), layering brief + AI + historicals. Uses a stubbed
model so it runs without a real key."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from promo_ops import suggest as _suggest
from promo_ops import suggest_server as srv


@pytest.fixture
def server(monkeypatch):
    inv = _suggest.inventory_for("USA")
    def stub(system, user):
        return json.dumps({"genres": [inv["genres"][0]], "pluto_categories": [inv["pluto_categories"][0]],
                           "pluto_channels": [inv["pluto_channels"][0], "Zzzq Invented Channel"],
                           "comp_shows": ["NCIS", "Zzzq Invented Series"]})
    monkeypatch.setattr(_suggest, "_anthropic_llm", stub)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_serves_the_form(server):
    with urllib.request.urlopen(server + "/") as r:
        html = r.read().decode()
    assert r.status == 200 and "Campaign Plan" in html and "Suggest targeting" in html


def test_suggest_grounds_and_returns_fields(server):
    code, data = _post(server, "/suggest",
                       {"title": "A Crime Drama", "description": "gritty detective serial killer", "region": "USA"})
    assert code == 200
    f = data["fields"]
    assert f["genres"]["matched"] and f["pluto_channels"]["matched"]
    # ungrounded (invented) values are silently dropped — never surfaced as a suggestion
    assert "Zzzq Invented Channel" not in f["pluto_channels"]["matched"]
    assert not any("Zzzq Invented Series" in m for m in f["showlist"]["matched"])
    assert any("NCIS" in m for m in f["showlist"]["matched"])
    # combine_targeting contract: provenance + degrade-mode reported
    assert "provenance" in data and data["mode"] in ("historicals", "ai+historicals")
    assert isinstance(data.get("notes"), list) and data["notes"]


def test_missing_title_400(server):
    code, data = _post(server, "/suggest", {"title": "", "description": ""})
    assert code == 400 and "error" in data


def test_title_only_ok_without_description(server):
    # No description and no brief: still valid — historicals(+AI stub) can work from title alone
    code, data = _post(server, "/suggest", {"title": "A Crime Drama", "region": "USA"})
    assert code == 200 and "fields" in data
