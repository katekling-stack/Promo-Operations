"""sync_series (and the sibling sync_* exporters) must write atomically: a sync that
fails partway through (auth/network blip, API error) must never truncate a previously
synced snapshot to a partial/empty file -- that silently breaks every resolver reading
from it (Tier 2 showlist targeting, Tier 1 DDA segments, etc.) until the next successful
sync, with no visible error at the point of failure."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient


def _fw_client(monkeypatch):
    for k in ("FREEWHEEL_NETWORK_ID", "FREEWHEEL_USERNAME", "FREEWHEEL_PASSWORD"):
        monkeypatch.setenv(k, "x")
    c = FreeWheelClient()
    c._retry_base_delay = 0.01
    return c


def test_sync_series_failure_does_not_clobber_existing_snapshot(tmp_path, monkeypatch):
    c = _fw_client(monkeypatch)
    existing = tmp_path / "synced_series.csv"
    original = "id,name,status\n1,Real Show,ACTIVE\n2,Another Show,ACTIVE\n"
    existing.write_text(original, encoding="utf-8")

    def boom(*a, **kw):
        raise ConnectionError("DNS resolution failure")

    monkeypatch.setattr(c, "_invoke", boom)
    monkeypatch.setattr(c, "authenticate", boom)   # re-auth retry also fails, same as the real outage

    with pytest.raises(ConnectionError):
        c.sync_series(out_dir=str(tmp_path))

    # The previously-synced catalog must survive a failed sync untouched.
    assert existing.read_text(encoding="utf-8") == original


def test_sync_series_success_replaces_snapshot(tmp_path, monkeypatch):
    c = _fw_client(monkeypatch)
    (tmp_path / "synced_series.csv").write_text("id,name,status\n1,Old Show,ACTIVE\n", encoding="utf-8")

    page1 = {"data": {"serieses": {"@total_page": "1",
             "series": [{"id": "10", "name": "New Show", "status": "ACTIVE"}]}}}
    monkeypatch.setattr(c, "_invoke", lambda *a, **kw: page1)

    path = c.sync_series(out_dir=str(tmp_path))
    text = (tmp_path / "synced_series.csv").read_text(encoding="utf-8")
    assert "New Show" in text and "Old Show" not in text
    assert path == str(tmp_path / "synced_series.csv")
