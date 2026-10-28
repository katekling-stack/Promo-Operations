"""Every video id the plan excludes is checked against FreeWheel BEFORE anything is created.
Regression: a mistyped 'Exclude videos' id (84808864) let the IO get created, then all six placements
failed with "Asset item doesn't exist", leaving an empty IO behind."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(videos):
    return OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Frasier", "region": "UK", "campaign": {"name": "Paramount + - UK"},
        "durations": [30], "genres": ["Comedy"], "exclude_videos": videos,
        "flight": {"start": "2026-10-01", "end": "2026-11-01"}}))


def _client(known):
    c = FreeWheelClient.__new__(FreeWheelClient)
    c.resolve_campaign_id = lambda n: "999"
    c._campaign_advertiser = lambda cid: None
    calls = []

    def inv(tool, **kw):
        calls.append((tool, kw))
        if tool == "sh_1_0_show-a-video":
            if kw["video_id"] in known:
                return {"ok": True, "data": {"video": {"id": kw["video_id"]}}}
            return {"ok": False, "status_code": 404, "error": "<errors>VIDEO doesn't exist</errors>"}
        if "create-an-insertion-order" in tool:
            return {"ok": True, "data": {"insertion_order": {"id": "777"}}}
        return {"ok": True}
    c._invoke = inv
    return c, calls


def test_a_missing_video_stops_the_push_before_anything_is_created():
    c, calls = _client(known={111})
    with pytest.raises(RuntimeError, match="84808864") as e:
        c.create_order(_order(["111", "84808864"]), dry_run=False)
    assert "Exclude videos" in str(e.value) and "nothing was created" in str(e.value).lower()
    assert not [t for t, _ in calls if "create" in t]


def test_existing_videos_pass_and_the_push_goes_ahead():
    c, calls = _client(known={111, 222})
    c.create_order(_order(["111", "222"]), dry_run=False)
    assert any("create-an-insertion-order" in t for t, _ in calls)


def test_no_excluded_videos_means_no_lookups():
    c, calls = _client(known=set())
    c.create_order(_order([]), dry_run=False)
    assert not [t for t, _ in calls if t == "sh_1_0_show-a-video"]


def test_a_dry_run_never_calls_freewheel():
    c, calls = _client(known=set())
    c.create_order(_order(["84808864"]), dry_run=True)
    assert calls == []


def test_a_lookup_that_fails_to_connect_does_not_block_the_push():
    c, calls = _client(known={111})
    orig = c._invoke

    def flaky(tool, **kw):
        if tool == "sh_1_0_show-a-video":
            raise ConnectionError("network blip")
        return orig(tool, **kw)
    c._invoke = flaky
    c.create_order(_order(["111"]), dry_run=False)           # can't prove it's missing -> don't block
