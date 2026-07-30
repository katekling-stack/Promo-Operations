"""Retry/backoff helper + its wiring into the FreeWheel client."""

from __future__ import annotations

import json

import pytest

from promo_ops.retry import TransientAPIError, is_transient_status, with_retries


def test_with_retries_succeeds_after_transient_failures():
    calls = {"n": 0}
    slept: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientAPIError(503, "blip")
        return "ok"

    out = with_retries(flaky, attempts=4, base_delay=2, sleep=slept.append)
    assert out == "ok" and calls["n"] == 3
    assert slept == [2, 4]                        # exponential backoff between tries


def test_with_retries_does_not_retry_permanent_errors():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        with_retries(boom, attempts=4, retry_on=lambda e: isinstance(e, TransientAPIError),
                     sleep=lambda s: None)
    assert calls["n"] == 1                        # not retried


def test_with_retries_exhausts_then_raises():
    slept: list[float] = []
    with pytest.raises(TransientAPIError):
        with_retries(lambda: (_ for _ in ()).throw(TransientAPIError(500)),
                     attempts=3, base_delay=1, sleep=slept.append)
    assert slept == [1, 2]                        # attempts-1 sleeps


def test_is_transient_status():
    assert is_transient_status(503) and is_transient_status("429")
    assert not is_transient_status(422) and not is_transient_status(None)


def _fw_client(monkeypatch):
    for k in ("FREEWHEEL_NETWORK_ID", "FREEWHEEL_USERNAME", "FREEWHEEL_PASSWORD"):
        monkeypatch.setenv(k, "x")
    from promo_ops.integrations.freewheel import FreeWheelClient
    c = FreeWheelClient()
    c._retry_base_delay = 0.01
    monkeypatch.setattr(c, "_ensure_auth", lambda: None)
    return c


def _mcp_response(payload: dict) -> dict:
    return {"result": {"content": [{"text": json.dumps(payload)}]}}


def test_freewheel_invoke_retries_transient_then_succeeds(monkeypatch):
    c = _fw_client(monkeypatch)
    slept: list[float] = []
    c._sleep = slept.append
    seq = [_mcp_response({"ok": False, "status_code": 503, "error": "blip"}),
           _mcp_response({"ok": True, "data": {"ok": 1}})]
    calls = {"n": 0}

    def fake_mcp(method, params, id_=1):
        r = seq[calls["n"]]
        calls["n"] += 1
        return r

    monkeypatch.setattr(c, "_mcp", fake_mcp)
    out = c._invoke("sh_1_1_list-campaigns")
    assert out == {"ok": True, "data": {"ok": 1}} and calls["n"] == 2 and len(slept) == 1


def test_freewheel_invoke_does_not_retry_422(monkeypatch):
    c = _fw_client(monkeypatch)
    slept: list[float] = []
    c._sleep = slept.append
    calls = {"n": 0}

    def fake_mcp(method, params, id_=1):
        calls["n"] += 1
        return _mcp_response({"ok": False, "status_code": 422, "error": "validation"})

    monkeypatch.setattr(c, "_mcp", fake_mcp)
    out = c._invoke("sh_1_0_create-a-placement", body={})
    assert out["status_code"] == 422 and calls["n"] == 1 and slept == []   # returned, not retried
