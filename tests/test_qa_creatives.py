"""QA reads the creatives attached to each line: placement -> its Ad (FreeWheel gives the Ad the
placement's id + 1) -> the creatives on that Ad -> each creative's length and status. A line named
for :30 needs an ACTIVE :30 creative. If the Ad can't be found it says so, never guesses."""

from __future__ import annotations

import copy

from promo_ops.qa import QAAuditor
from test_qa_noise import UK_CID, UK_PLAN, _audit  # noqa: F401
from test_qa import _live


class _Client:
    """A client that also answers the two creative reads. instances: {ad_id: [instance dicts]};
    creatives: {creative_id: creative dict}."""

    def __init__(self, io, pls, instances, creatives):
        self._io, self._pls, self.instances, self.creatives = io, pls, instances, creatives
        self.reads = []

    def get_insertion_order(self, io_id):
        return {"data": {"insertion_order": self._io}}

    def list_placements(self, io_id):
        return self._pls

    def list_creative_instances(self, ad_id):
        self.reads.append(("instances", ad_id))
        return self.instances.get(int(ad_id), [])

    def get_creative(self, creative_id):
        self.reads.append(("creative", creative_id))
        return self.creatives[int(creative_id)]


def _lines():
    io, pls = _live(UK_PLAN, UK_CID)
    pls = copy.deepcopy(pls)
    for i, p in enumerate(pls):
        p["id"] = str(1000 + i * 10)
    return io, pls


def _dur(name):
    import re
    m = re.search(r"- (\d+)(?: \(| -|$)", name)
    return int(m.group(1)) if m else None


def _full_client(io, pls, status="ACTIVE", length=None, inst_status="ACTIVE"):
    instances, creatives, cid = {}, {}, 5000
    for p in pls:
        d = length or _dur(p["name"]) or 30
        cid += 1
        creatives[cid] = {"id": cid, "name": f"c{cid}", "duration": d, "status": status}
        instances[int(p["id"]) + 1] = [{"ad_id": str(int(p["id"]) + 1), "creative_id": str(cid),
                                        "placement_id": p["id"], "status": inst_status}]
    return _Client(io, pls, instances, creatives)


def _creative_findings(rep, level=None):
    return [f for f in rep.findings if f.category == "creative_duration"
            and (level is None or f.level == level)]


def test_matching_active_creatives_pass_and_the_info_note_goes_away():
    io, pls = _lines()
    rep = QAAuditor(client=_full_client(io, pls)).audit_io("1")
    fs = _creative_findings(rep)
    assert fs and all(f.level == "ok" for f in fs), [f.line() for f in fs if f.level != "ok"]


def test_a_creative_of_the_wrong_length_is_an_error():
    io, pls = _lines()
    rep = QAAuditor(client=_full_client(io, pls, length=45)).audit_io("1")
    errs = _creative_findings(rep, "error")
    assert errs and "no matching creative length" in errs[0].message and errs[0].actual == [45]


def test_a_line_with_no_creatives_is_flagged_not_skipped():
    io, pls = _lines()
    rep = QAAuditor(client=_Client(io, pls, {}, {})).audit_io("1")
    warns = _creative_findings(rep, "warn")
    assert warns and "no active creatives" in warns[0].message.lower()


def test_inactive_creatives_do_not_count():
    io, pls = _lines()
    rep = QAAuditor(client=_full_client(io, pls, status="INACTIVE")).audit_io("1")
    assert _creative_findings(rep, "warn") and not _creative_findings(rep, "ok")
    rep2 = QAAuditor(client=_full_client(io, pls, inst_status="INACTIVE")).audit_io("1")
    assert _creative_findings(rep2, "warn") and not _creative_findings(rep2, "ok")


def test_an_ad_that_belongs_to_another_placement_is_never_used():
    io, pls = _lines()
    client = _full_client(io, pls)
    for ad, insts in client.instances.items():
        for i in insts:
            i["placement_id"] = "999999"          # the id+1 guess landed on someone else's ad
    rep = QAAuditor(client=client).audit_io("1")
    assert not _creative_findings(rep, "ok") and _creative_findings(rep, "warn")


def test_a_creative_used_on_many_lines_is_read_once():
    io, pls = _lines()
    client = _full_client(io, pls)
    shared = {"id": 7, "name": "shared", "duration": 30, "status": "ACTIVE"}
    client.creatives = {7: shared}
    client.instances = {int(p["id"]) + 1: [{"ad_id": "x", "creative_id": "7", "placement_id": p["id"],
                                            "status": "ACTIVE"}] for p in pls}
    QAAuditor(client=client).audit_io("1")
    assert client.reads.count(("creative", "7")) == 1


def test_a_failed_creative_read_falls_back_to_the_old_note():
    io, pls = _lines()
    client = _full_client(io, pls)

    def boom(ad_id):
        raise RuntimeError("503")
    client.list_creative_instances = boom
    rep = QAAuditor(client=client).audit_io("1")
    infos = _creative_findings(rep, "info")
    assert infos and "couldn't read" in infos[0].message and not _creative_findings(rep, "error")


def test_clients_without_creative_reads_behave_as_before():
    io, pls = _lines()
    rep = _audit(io, pls)                         # the plain mock has no creative methods
    assert _creative_findings(rep, "info") and not _creative_findings(rep, "error")
