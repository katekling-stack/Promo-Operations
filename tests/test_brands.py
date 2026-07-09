"""Per-brand nuances (ad units + always-exclude), verified vs the reference IOs."""

from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.order_builder import OrderBuilder
from promo_ops.integrations.freewheel import FreeWheelClient


def _cbs_news_order():
    plan = support_plan_from_dict({
        "promoted_title": "Money Moves", "region": "USA", "brand": "cbs_news",
        "formats": ["remnant_video"], "durations": [30],
        "campaign": {"name": "CBS News - USA", "resolved_id": "54413662"},
        "genres": ["News"], "showlist": ["FBI"],
        "pluto": {"channels": ["Westerns"], "categories": ["News + Opinion"]},
    })
    return OrderBuilder().build(plan)


def test_cbs_news_uses_mid_and_post_only_no_preroll():
    t1 = next(p for p in _cbs_news_order().placements if p.tier == 1)
    assert t1.ad_unit_ids == ["72000", "72001"]        # Midroll + Postroll, no Preroll


def test_cbs_news_always_excludes_pluto_news_sgs():
    order = _cbs_news_order()
    news_sgs = {"1037683", "1038397", "1038398", "1038399", "1038400"}
    for p in order.placements:
        assert news_sgs.issubset(set(p.extra_exclude_site_groups))
    # and they land in the written exclude (with the shared DNR) on every set
    t3 = next(p for p in order.placements if p.tier == 3)
    body = FreeWheelClient._placement_body(t3)
    for s in body["relationship_targeting"]["set"]:
        exc = s["content_targeting"]["network_items"].get("exclude", {})
        assert news_sgs.issubset(set(exc.get("site_group", [])))
        assert "951172" in exc["site_group"]           # shared DNR still there


def _cbs_network_order():
    plan = support_plan_from_dict({
        "promoted_title": "Marshals", "region": "USA", "brand": "cbs_network",
        "formats": ["cbs_preroll", "cbs_after_midroll_bumper", "cbs_1z_lockdown",
                    "cbs_2z_lockdown"],
        "genres": ["Crime"], "campaign": {"resolved_id": "54407793"},
    })
    return OrderBuilder().build(plan)


def test_cbs_network_guaranteed_lines_are_bare_highest_sponsorship():
    order = _cbs_network_order()
    by_name = {p.name: p for p in order.placements}
    pre = FreeWheelClient._placement_body(by_name["Marshals - CBS Pre-Roll - USA"])
    assert pre["budget"]["budget_model"] == "ALL_IMPRESSION"
    assert pre["override"] == {"precedence_level": "HIGHEST"}
    assert pre["ad_product"]["ad_unit_node"][0]["ad_unit_id"] == "66704"
    assert pre["delivery"]["frequency_cap"] == {"value": "2", "type": "IMPRESSION",
                                                "period": "1440"}
    assert "relationship_targeting" not in pre        # bare sponsorship line
    bumper = FreeWheelClient._placement_body(by_name["Marshals - CBS After Mid-Roll Bumper - USA"])
    assert "frequency_cap" not in bumper["delivery"]  # no cap on the bumper
    assert {"Marshals - 1Z Lockdown - USA", "Marshals - 2Z Lockdown - USA"} <= set(by_name)


def test_cbs_sports_psa_flat_lines():
    plan = support_plan_from_dict({
        "promoted_title": "PGA Tour", "region": "USA", "brand": "cbs_sports",
        "formats": ["psa"], "durations": [30, 10],
        "campaign": {"resolved_id": "54413703"},
    })
    order = OrderBuilder().build(plan)
    names = [p.name for p in order.placements]
    assert names == ["PGA Tour - PSA - 30 - USA", "PGA Tour - PSA - 10 - USA"]
    body = FreeWheelClient._placement_body(order.placements[0])
    assert body["override"] == {"mode": "BELOW_PAYING_ADS", "value": -10}   # Tier-4
    inc = body["relationship_targeting"]["set"][0]["content_targeting"]["network_items"]["include"]
    assert inc["site_group"] == ["929392", "932583", "932591", "932592"]    # main SGs only


def test_default_brand_falls_back_to_paramount_house_units():
    # No brand -> global default ad-unit group (Paramount house Pre/Mid/Post).
    plan = support_plan_from_dict({
        "promoted_title": "X", "region": "USA", "formats": ["remnant_video"],
        "durations": [30], "showlist": ["FBI"],
    })
    t1 = next(p for p in OrderBuilder().build(plan).placements if p.tier == 1)
    assert t1.ad_unit_ids == ["71999", "72000", "72001"]
