"""QA must audit what is actually in FreeWheel. The placement LIST call returns only
id/name/status, so the auditor fetches each placement's full body (show=all) -- without it
every targeting/cap/ad-unit check reads nothing and the UFC check reports a false error.
Listing also pages, so an IO with more than one page of placements is audited in full."""

from __future__ import annotations

import copy

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.qa import QAAuditor
from test_qa import AU_PLAN, _live


class _SummaryMock:
    """Like the live API: list returns summary rows only; full bodies come from get_placement."""

    def __init__(self, io, bodies, broken=()):
        self._io = io
        self._bodies = {1000 + i: b for i, b in enumerate(bodies)}
        self._broken = set(broken)
        self.fetched = []

    def get_insertion_order(self, io_id):
        return {"data": {"insertion_order": self._io}}

    def list_placements(self, io_id):
        return [{"id": i, "name": b["name"], "status": "INACTIVE"} for i, b in self._bodies.items()]

    def get_placement(self, pid):
        self.fetched.append(int(pid))
        if int(pid) in self._broken:
            raise RuntimeError("boom")
        return copy.deepcopy(self._bodies[int(pid)])


def _audit(mock):
    return QAAuditor(client=mock).audit_io("80271357")


def test_summary_rows_are_enriched_so_a_correct_order_passes_cleanly():
    io, pls = _live(AU_PLAN, "73850057")
    mock = _SummaryMock(io, pls)
    rep = _audit(mock)
    assert len(mock.fetched) == len(pls)
    assert not rep.by_level("error"), [f.message for f in rep.by_level("error")]
    assert not rep.by_level("warn"), [f.message for f in rep.by_level("warn")]
    # and the checks genuinely ran on real data (not "couldn't read" for everything)
    assert any(f.level == "ok" and f.category == "targeting" for f in rep.findings)


def test_a_real_problem_is_caught_through_the_fetched_body():
    io, pls = _live(AU_PLAN, "73850057")
    pls = copy.deepcopy(pls)
    for b in pls:
        if "(Tier 4)" in b["name"] and "relationship_targeting" in b:
            b["relationship_targeting"]["set"] = [
                s for s in b["relationship_targeting"]["set"] if s.get("set_name") != "Franchise: UFC"]
    rep = _audit(_SummaryMock(io, pls))
    assert any(f.category == "targeting" and f.level == "error" and "UFC" in f.message
               for f in rep.findings)


def test_one_unreadable_placement_is_reported_not_fatal():
    io, pls = _live(AU_PLAN, "73850057")
    rep = _audit(_SummaryMock(io, pls, broken=[1000]))
    assert rep.error is None
    assert any(f.level == "info" and "couldn't fetch" in f.message.lower() for f in rep.findings)
    assert len(rep.findings) > 10      # the other placements were still audited


def test_full_bodies_are_not_refetched():
    # Rows that already carry their body (as in the other QA tests) are used as-is.
    io, pls = _live(AU_PLAN, "73850057")

    class _Full(_SummaryMock):
        def list_placements(self, io_id):
            return [dict(b, id=1000 + i) for i, b in enumerate(pls)]

    mock = _Full(io, pls)
    _audit(mock)
    assert mock.fetched == []


# --- paging --------------------------------------------------------------------------- #
def _fw(monkeypatch):
    for k in ("FREEWHEEL_NETWORK_ID", "FREEWHEEL_USERNAME", "FREEWHEEL_PASSWORD"):
        monkeypatch.setenv(k, "x")
    return FreeWheelClient()


def _payload(rows):
    return {"data": {"placements": {"placement": rows}}}


def test_list_placements_pages_until_a_short_page(monkeypatch):
    c = _fw(monkeypatch)
    pages = {1: [{"id": i} for i in range(50)], 2: [{"id": i} for i in range(50, 62)]}
    seen = []

    def fake(tool, **kw):
        seen.append(kw["page"])
        return _payload(pages.get(kw["page"], []))

    monkeypatch.setattr(c, "_invoke", fake)
    rows = c.list_placements("1")
    assert len(rows) == 62 and seen == [1, 2]


def test_list_placements_stops_if_the_server_ignores_page(monkeypatch):
    c = _fw(monkeypatch)
    same = [{"id": i} for i in range(50)]
    monkeypatch.setattr(c, "_invoke", lambda tool, **kw: _payload(same))
    assert len(c.list_placements("1")) == 50       # no infinite loop, no duplicates


def test_list_placements_single_small_page_is_one_call(monkeypatch):
    c = _fw(monkeypatch)
    calls = []
    monkeypatch.setattr(c, "_invoke", lambda tool, **kw: (calls.append(kw), _payload([{"id": 1}]))[1])
    assert len(c.list_placements("1")) == 1 and len(calls) == 1


def test_get_placement_asks_for_everything(monkeypatch):
    c = _fw(monkeypatch)
    got = {}

    def fake(tool, **kw):
        got.update(tool=tool, **kw)
        return {"ok": True, "data": {"placement": {"id": 7, "name": "X"}}}

    monkeypatch.setattr(c, "_invoke", fake)
    body = c.get_placement(7)
    assert body == {"id": 7, "name": "X"}
    assert got["tool"] == "sh_1_0_show-a-placement" and got["show"] == "all"
    assert got["placement_id"] == 7
