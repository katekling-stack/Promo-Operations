"""Older seasons on a live IO name the Network 10 lines "(10Play)" rather than "(10 Streaming)".
The auditor must still recognise them as Network 10 lines -- otherwise they're held to the
standard P+ rules (P+ ad units / main site groups / the P+-only UFC set) and flagged falsely."""

from __future__ import annotations

import copy

from test_qa import AU_PLAN, _audit, _live


def _rename(pls, old, new):
    out = copy.deepcopy(pls)
    for p in out:
        p["name"] = p["name"].replace(old, new)
    return out


def test_10play_legacy_name_is_treated_as_a_network_10_line():
    plan = dict(AU_PLAN)
    plan["product_overrides"] = {"network_10": True}
    io, pls = _live(plan, "73850057")
    assert not _audit(io, pls).by_level("error") and not _audit(io, pls).by_level("warn")
    legacy = _audit(io, _rename(pls, "(10 Streaming)", "(10Play)"))
    assert not legacy.by_level("error"), [f.message for f in legacy.by_level("error")]
    assert not legacy.by_level("warn"), [f.message for f in legacy.by_level("warn")]
