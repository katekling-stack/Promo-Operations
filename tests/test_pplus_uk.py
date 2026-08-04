"""Paramount+ UK (adult) — standard tiered model, UK P+/Pluto split."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _order(include_pluto: bool = True):
    plan = support_plan_from_dict({
        "promoted_title": "The Agency", "region": "UK",
        "campaign": {"name": "Paramount + - UK"}, "content_type": "show",
        "content_id": "943970057", "season_or_messaging": "Season 2",
        "durations": [15, 30], "showlist": ["NCIS"], "genres": ["Drama"],
        "pluto": {"channels": ["Westerns"], "categories": ["Movies - Action"]},
        "product_overrides": {"pluto_breakout": include_pluto} if include_pluto else {},
    })
    return plan, OrderBuilder().build(plan)


def test_include_pluto_checkbox_gates_the_breakout():
    # Off by default: P+ lines + pause + guaranteed, no Pluto breakout.
    _, off = _order(include_pluto=False)
    assert not any("(Pluto)" in p.name for p in off.placements)
    # Checkbox on: adds the Pluto breakout lines.
    _, on = _order(include_pluto=True)
    assert sum("(Pluto)" in p.name for p in on.placements) == 6


def test_pplus_uk_split_and_naming():
    plan, order = _order(include_pluto=True)
    assert plan.brand == "paramount_plus_uk"
    names = [p.name for p in order.placements]
    # tier always in parens; Pluto lines carry the "(Pluto)" infix after the tier.
    # Paramount+ campaigns stamp [ShowID:<id>] on EVERY placement (all tiers).
    assert "The Agency - Season 2 - 15 (Tier 2) - UK - [ShowID:943970057]" in names
    assert "The Agency - Season 2 - 15 (Tier 2) (Pluto) - UK - [ShowID:943970057]" in names
    assert "The Agency - Season 2 - Pause Ad (Tier 4) - UK - [ShowID:943970057]" in names
    assert ("Paramount + - Bumper - Basic Plan - The Agency - UK - [ShowID:943970057]"
            in names)
    assert all(n.endswith("[ShowID:943970057]") for n in names)   # every placement
    assert all(p.geo_country_ids == ["56"] for p in order.placements)


def test_pplus_uk_line_ad_units_and_main_sgs():
    _, order = _order(include_pluto=True)

    def main_sgs(p):
        body = FreeWheelClient._placement_body(p)
        sets = body["relationship_targeting"]["set"]
        inc = sets[-1]["content_targeting"]["network_items"]["include"]  # tier-4 RON set
        subs = inc.get("set", [inc])
        return set(next((s.get("site_group") for s in subs if s.get("site_group")), []))

    pplus_t4 = next(p for p in order.placements
                    if p.name == "The Agency - Season 2 - 15 (Tier 4) - UK - [ShowID:943970057]")
    assert set(pplus_t4.ad_unit_ids) == {"69304", "71999", "72000", "72001"}  # INTL + house
    assert main_sgs(pplus_t4) == {"932583", "932591", "932592"}

    pluto_t4 = next(p for p in order.placements
                    if p.name == "The Agency - Season 2 - 15 (Tier 4) (Pluto) - UK - [ShowID:943970057]")
    assert "69304" not in pluto_t4.ad_unit_ids            # no INTL pre-roll on Pluto line
    assert main_sgs(pluto_t4) == {"929392"}
