"""Creating a NEW IO is refused when the campaign already has an IO with the same name (from a
double click, a re-run, or a plan pushed twice). Adding lines to an existing IO is unaffected."""

from __future__ import annotations

import pytest

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

PLAN = {"promoted_title": "Frasier", "region": "UK", "campaign": {"name": "Paramount + - UK"},
        "durations": [30], "genres": ["Comedy"], "flight": {"start": "2026-10-01", "end": "2026-11-01"}}


def _client(existing_name_id=None, lookup_error=False):
    c = FreeWheelClient.__new__(FreeWheelClient)
    c.resolve_campaign_id = lambda n: "999"
    c._campaign_advertiser = lambda cid: None
    calls = []

    def find(campaign_id, name, **kw):
        calls.append(("find", campaign_id, name))
        if lookup_error:
            raise ConnectionError("blip")
        return existing_name_id
    c.find_insertion_order_by_name = find

    def inv(tool, **kw):
        calls.append((tool,))
        if "create-an-insertion-order" in tool:
            return {"ok": True, "data": {"insertion_order": {"id": "777"}}}
        return {"ok": True}
    c._invoke = inv
    return c, calls


def test_a_second_io_with_the_same_name_is_refused_before_anything_is_created():
    c, calls = _client(existing_name_id="555")
    order = OrderBuilder().build(support_plan_from_dict(PLAN))
    with pytest.raises(RuntimeError, match="already exists") as e:
        c.create_order(order, dry_run=False)
    assert "555" in str(e.value) and "Add to existing IO" in str(e.value)
    assert not [x for x in calls if x[0] != "find"]


def test_no_clash_goes_ahead():
    c, calls = _client(existing_name_id=None)
    order = OrderBuilder().build(support_plan_from_dict(PLAN))
    c.create_order(order, dry_run=False)
    assert any("create-an-insertion-order" in x[0] for x in calls)


def test_adding_to_an_existing_io_skips_the_check():
    c, calls = _client(existing_name_id="555")
    c._validate_append_io = lambda *a, **k: None
    order = OrderBuilder().build(support_plan_from_dict({**PLAN, "existing_io_id": "98378317"}))
    c.create_order(order, dry_run=False)
    assert not [x for x in calls if x[0] == "find"]


def test_a_lookup_that_cannot_be_made_does_not_block():
    c, calls = _client(lookup_error=True)
    order = OrderBuilder().build(support_plan_from_dict(PLAN))
    c.create_order(order, dry_run=False)
    assert any("create-an-insertion-order" in x[0] for x in calls)


def test_a_dry_run_never_looks():
    c, calls = _client(existing_name_id="555")
    order = OrderBuilder().build(support_plan_from_dict(PLAN))
    c.create_order(order, dry_run=True)
    assert calls == []
