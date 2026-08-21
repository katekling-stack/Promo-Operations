"""Guard: 'Add to existing IO' must be a REAL Insertion Order, not the campaign id.

Regression: pasting the CAMPAIGN id into 'Add to existing IO' made the push route to
append-to-existing-IO, create a Brand, then 422 on every placement ("Insertion Order not
found") — nothing usable created. The guard now fails cleanly BEFORE any Brand/placement
write, for both the campaign-id slip and any non-existent IO id."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(existing_io_id):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="Pluto TV Arte - IT", region="IT", campaign={"name": "Pluto TV - IT"},
        durations=[30], genres=["Film Noir"], existing_io_id=existing_io_id)))


def _client(campaign_id, io_exists):
    c = FreeWheelClient.__new__(FreeWheelClient)              # bypass __init__ (no env/network)
    brand = {"n": 0}
    c._ensure_io_brand = lambda o: brand.__setitem__("n", brand["n"] + 1) or None
    c.resolve_campaign_id = lambda n: campaign_id
    c.get_insertion_order = lambda io: ({"data": {"insertion_order": {"id": str(io)}}}
                                        if io_exists else {"ok": False})
    touched = {"api": False}
    c._invoke = lambda *a, **k: touched.__setitem__("api", True) or {}
    return c, brand, touched


def test_append_io_equal_to_campaign_id_raises_before_any_write():
    order = _order("72285925")                               # == the campaign id below
    c, brand, touched = _client("72285925", io_exists=True)
    with pytest.raises(RuntimeError, match="CAMPAIGN id"):
        c.create_order(order, dry_run=False)
    assert brand["n"] == 0 and touched["api"] is False        # no Brand, no placements


def test_append_io_not_found_raises_before_any_write():
    order = _order("93584432")
    c, brand, touched = _client("72285925", io_exists=False)  # IO doesn't exist
    with pytest.raises(RuntimeError, match="not found"):
        c.create_order(order, dry_run=False)
    assert brand["n"] == 0 and touched["api"] is False


def test_valid_existing_io_passes_the_guard():
    order = _order("93584432")
    c, brand, touched = _client("72285925", io_exists=True)   # real IO, != campaign
    c.create_order(order, dry_run=False)                      # must not raise from the guard
    assert touched["api"] is True                             # proceeded to create placements
