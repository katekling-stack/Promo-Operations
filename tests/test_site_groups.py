"""Pluto Site Group resolution (Tier 2 channels + Tier 3 categories)."""

from promo_ops.site_groups import SiteGroupResolver, _norm
from promo_ops.order_builder import OrderBuilder
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.plan_loader import load_plan
from promo_ops.config import REPO_ROOT

CH = "SG: PlutoTV Channels: US: "


def test_norm_treats_and_ampersand_plus_equivalently():
    assert _norm("Law & Order") == _norm("Law and Order") == "law order"
    assert _norm("History & Science") == _norm("History + Science")
    assert _norm("S.W.A.T.") == "swat"


def test_channel_keyword_selects_all_matches():
    r = SiteGroupResolver().load()
    m = r.select_all("Westerns", prefix=CH)
    # keyword select-all: multiple Westerns channels, all under the US channels scope.
    assert len(m.site_groups) >= 2
    assert all("channels: us" in sg["name"].lower() for sg in m.site_groups)


def test_scope_prefix_and_suffix_are_enforced():
    r = SiteGroupResolver().load()
    # Category scope pins region to the ": US" suffix (domestic promo categories).
    m = r.select_all("Drama", prefix="SG: PlutoTV Promo Category: ", suffix=": US")
    assert m.matched
    assert all(sg["name"].startswith("SG: PlutoTV Promo Category:") for sg in m.site_groups)


def test_do_not_use_entries_are_skipped():
    r = SiteGroupResolver().load()
    m = r.select_all("Food", prefix="SG: PlutoTV Promo Category: ", suffix=": US")
    assert all("do not use" not in sg["name"].lower() for sg in m.site_groups)


def test_frisco_king_pluto_fully_resolves_into_placement_body():
    plan = load_plan(str(REPO_ROOT / "plans" / "frisco-king-usa.yaml"))
    order = OrderBuilder().build(plan)
    t2 = next(p for p in order.placements
              if "(Tier 2) - USA" in p.name and p.duration == 30)
    body = FreeWheelClient._placement_body(t2)
    # Tier 2 mirrors Dutton: "Affinity Shows" (Video Series AND main platform SGs) +
    # "Channels" (Pluto channel SGs).
    sets = {s["set_name"]: s for s in body["relationship_targeting"]["set"]}
    channels = sets["Channels"]["content_targeting"]["network_items"]["include"]["site_group"]
    assert len(channels) > 50
    # Affinity Shows = AND of {series} and {main SGs}
    affinity_inc = sets["Affinity Shows"]["content_targeting"]["network_items"]["include"]
    assert affinity_inc["relation_between_sets"] == ["AND"]   # N-1 relations for N sets
    subs = {tuple(sorted(k for k in s if k != "relation_in_set")): s for s in affinity_inc["set"]}
    series = subs[("series",)]["series"]
    assert series and all(s.isdigit() for s in series)
    assert subs[("site_group",)]["site_group"]   # main platform SGs AND-ed in
