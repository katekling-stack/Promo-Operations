"""FreeWheel auth resilience: a transient gateway status (e.g. a 502 'Bad Gateway' HTML
page during a FreeWheel outage) must surface as a clear, retryable TransientAPIError —
never a raw JSONDecodeError on the HTML body."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.retry import TransientAPIError


class _FakeResp:
    def __init__(self, status_code, text='', payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON object could be decoded")
        return self._payload


def test_502_html_becomes_retryable_transient_error():
    resp = _FakeResp(502, text="<html><head><title>502 Bad Gateway</title></head></html>")
    with pytest.raises(TransientAPIError) as ei:
        FreeWheelClient._auth_json(resp, "register")
    assert ei.value.status == 502
    assert "temporarily unavailable" in str(ei.value)


@pytest.mark.parametrize("code", [429, 500, 503, 504])
def test_other_transient_statuses_retryable(code):
    with pytest.raises(TransientAPIError):
        FreeWheelClient._auth_json(_FakeResp(code, text="oops"), "token")


def test_200_non_json_raises_clear_runtime_error():
    with pytest.raises(RuntimeError) as ei:
        FreeWheelClient._auth_json(_FakeResp(200, text="not json"), "register")
    assert "non-JSON" in str(ei.value)


def test_200_json_passes_through():
    assert FreeWheelClient._auth_json(_FakeResp(200, payload={"client_id": "abc"}), "register") \
        == {"client_id": "abc"}
