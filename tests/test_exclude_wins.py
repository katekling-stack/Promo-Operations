"""A site group must never be in both include and exclude on a FreeWheel placement
(the API rejects it, 422). _exclude_wins drops the conflict — exclude always wins."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.order_builder import OrderBuilder


def test_excluded_sg_removed_from_include_keeps_other_targeting():
    body = {"relationship_targeting": {"set": [
        {"set_name": "Affinity", "content_targeting": {"network_items": {
            "include": {"relation_between_sets": ["AND"], "set": [
                {"series": ["S1"], "relation_in_set": "OR"},
                {"site_group": ["929392", "111"], "relation_in_set": "OR"}]},
            "exclude": {"site_group": ["111"]}}}}]}}
    FreeWheelClient._exclude_wins(body)
    inc = body["relationship_targeting"]["set"][0]["content_targeting"]["network_items"]["include"]
    sgs = [sub.get("site_group") for sub in inc["set"] if "site_group" in sub][0]
    assert "111" not in sgs and "929392" in sgs           # conflict dropped, rest kept


def test_set_dropped_when_include_fully_excluded():
    body = {"relationship_targeting": {"set": [
        {"set_name": "Channels", "content_targeting": {"network_items": {
            "include": {"site_group": ["111", "222"]},
            "exclude": {"site_group": ["111", "222"]}}}},
        {"set_name": "Keep", "content_targeting": {"network_items": {
            "include": {"site_group": ["333"]}, "exclude": {"site_group": ["999"]}}}}]}}
    FreeWheelClient._exclude_wins(body)
    names = [s["set_name"] for s in body["relationship_targeting"]["set"]]
    assert names == ["Keep"]                              # self-cancelled set removed


def test_no_placement_has_a_site_group_in_both_include_and_exclude():
    # End-to-end: a plan that targets AND excludes the same channel must still produce
    # bodies with disjoint include/exclude site groups on every placement.
    plan = support_plan_from_dict({
        "promoted_title": "Yellowstone", "region": "USA",
        "campaign": {"name": "Paramount + - USA"}, "durations": [30],
        "showlist": ["NCIS"], "genres": ["Drama"],
        "pluto": {"channels": ["Westerns"]}, "exclude_channels": ["Westerns"]})
    order = OrderBuilder().build(plan)
    bodies = FreeWheelClient.to_freewheel_plan(order)["placement_bodies"]

    def sgs(node, which):
        n = node.get(which) or {}
        out = set(n.get("site_group") or [])
        for sub in (n.get("set") or []):
            out |= set(sub.get("site_group") or [])
        return out

    for b in bodies:
        for st in (b.get("relationship_targeting") or {}).get("set", []):
            node = (st.get("content_targeting") or {}).get("network_items") or {}
            assert not (sgs(node, "include") & sgs(node, "exclude")), b["name"]
