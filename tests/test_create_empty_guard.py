"""Guard: a plan that builds 0 placements must NOT create an empty Insertion Order — the
push stops before touching FreeWheel with a clear reason. (Regression: kids campaign with no
Kids audience, or a campaign whose brand isn't configured, would create an IO and nothing else.)"""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _zero_placement_order():
    # A kids campaign with NO kids_audience builds 0 placements (kids lines are gated on it).
    order = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="T", region="UK", campaign={"name": "5 - Kids - UK"},
        durations=[15, 30], genres=["Drama"])))
    assert len(order.placements) == 0
    return order


def test_live_push_refuses_to_create_empty_io():
    order = _zero_placement_order()
    c = FreeWheelClient.__new__(FreeWheelClient)          # bypass __init__ (no env/network)
    c._ensure_io_brand = lambda o, campaign_id=None: None
    c.resolve_campaign_id = lambda n: "999"
    touched = {"api": False}
    c._invoke = lambda *a, **k: touched.__setitem__("api", True) or {}

    with pytest.raises(RuntimeError, match="0 placements"):
        c.create_order(order, dry_run=False)
    assert touched["api"] is False                        # never created an IO or anything else


def test_dry_run_still_returns_plan_even_if_empty():
    # Dry-run just reports the (empty) plan — the guard only blocks the LIVE create.
    order = _zero_placement_order()
    c = FreeWheelClient.__new__(FreeWheelClient)
    out = c.create_order(order, dry_run=True)
    assert out["dry_run"] is True and out["planned_calls"]["placement_bodies"] == []


def test_live_push_stops_when_freewheel_refuses_to_create_the_io():
    # Regression: FreeWheel answered the create-IO call with a 400, io id came back empty, and the
    # tool carried on creating every placement against "Insertion Order id 0".
    order = OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="Frasier", region="UK", campaign={"name": "Paramount + - UK"},
        durations=[30], genres=["Comedy"], showlist=[], flight={"start": "2026-10-01", "end": "2026-11-01"})))
    assert order.placements
    c = FreeWheelClient.__new__(FreeWheelClient)
    c._ensure_io_brand = lambda o, campaign_id=None: None
    c.resolve_campaign_id = lambda n: "999"
    calls = []

    def fake_invoke(tool, **kw):
        calls.append(tool)
        return {"ok": False, "status_code": 400,
                "error": "<errors><error>expected element type &lt;insertion_order&gt; but have &lt;IO&gt;</error></errors>"}
    c._invoke = fake_invoke

    with pytest.raises(RuntimeError, match="couldn't create the Insertion Order") as exc:
        c.create_order(order, dry_run=False)
    assert "expected element type" in str(exc.value)
    assert calls == ["sh_1_1_create-an-insertion-order"]       # no placement was attempted
