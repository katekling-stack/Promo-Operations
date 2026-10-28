"""The IO-level frequency cap lives in the IO's `delivery` block, which FreeWheel only returns when
asked for the full record (show=all) -- the plain read omits it, so QA said 'couldn't read the
order-level frequency cap' on every order. A one-cap IO comes back as a single object, not a list."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.qa import QAAuditor
from test_qa_noise import UK_CID, UK_PLAN, _Mock
from test_qa import _live


def test_the_io_read_asks_for_the_full_record():
    c = FreeWheelClient.__new__(FreeWheelClient)
    seen = {}
    c._invoke = lambda tool, **kw: seen.update(tool=tool, **kw) or {"data": {"insertion_order": {}}}
    c.get_insertion_order("98337963")
    assert seen["tool"] == "sh_1_1_get-a-insertion-order" and seen["show"] == "all" \
        and seen["insertion_order_id"] == 98337963


def _cap_findings(rep):
    return [f for f in rep.findings if f.category == "freq_cap" and f.placement == "(order)"]


def test_a_single_cap_object_is_read_and_compared():
    io, pls = _live(UK_PLAN, UK_CID)
    io = {**io, "delivery": {"frequency_cap": {"value": "1", "type": "IMPRESSION", "period": "30"}}}
    fs = _cap_findings(QAAuditor(client=_Mock(io, pls)).audit_io("1"))
    assert fs and all(f.level in ("ok", "error") for f in fs) and not [f for f in fs if f.level == "info"]


def test_a_missing_delivery_block_is_still_just_a_note():
    io, pls = _live(UK_PLAN, UK_CID)
    io = {k: v for k, v in io.items() if k != "delivery"}
    fs = _cap_findings(QAAuditor(client=_Mock(io, pls)).audit_io("1"))
    assert fs and fs[0].level == "info"
