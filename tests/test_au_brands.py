"""Australia — no Pluto: P+ AU is tiered, main SGs exclude Pluto (929392), geo 10."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def test_pplus_au_tiered_no_pluto():
    plan = support_plan_from_dict({
        "promoted_title": "UFC", "region": "AU",
        "campaign": {"name": "Paramount + - AU"}, "content_type": "show",
        "content_id": "956519957", "season_or_messaging": "Fight Night",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Sports"],
    })
    order = OrderBuilder().build(plan)
    assert plan.brand == "paramount_plus_au"
    assert all(p.geo_country_ids == ["10"] for p in order.placements)      # Australia
    assert any("- 15 (Tier 1) - AU" in p.name for p in order.placements)   # tiered, parens
    assert any("Bumper - Basic Plan" in p.name for p in order.placements)
    # main SGs have NO Pluto (929392); AU has no Pluto and no Samsung exclude
    t4 = next(p for p in order.placements if p.tier == 4)
    body = FreeWheelClient._placement_body(t4)
    main = set(body["relationship_targeting"]["set"][0]["content_targeting"]
               ["network_items"]["include"]["site_group"])
    assert main == {"932583", "932591", "932592"}
    assert "929392" not in main
    assert not any(FreeWheelClient._placement_body(p).get("content_targeting")
                   for p in order.placements)   # no Samsung/content exclude (non-Pluto)
    # INTL pre-roll kept, house pre-roll drops at 30s
    p15 = next(p for p in order.placements if p.tier == 1 and p.duration == 15)
    p30 = next(p for p in order.placements if p.tier == 1 and p.duration == 30)
    assert "69304" in p15.ad_unit_ids and "71999" in p15.ad_unit_ids
    assert "69304" in p30.ad_unit_ids and "71999" not in p30.ad_unit_ids
