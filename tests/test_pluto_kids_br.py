"""Pluto TV - Kids - BR builds like every other Pluto TV Kids campaign.

It was scaffolded from the Spanish-language US Pluto Kids clone: not flagged kids, so no Older/
Younger choice and the adult advertiser for its Brand, built on the Spanish remnant format with
hand-written targeting sets carrying US-only site groups. It now uses the standard Pluto Kids
setup (same as FR / IT / DK ...); the only things that may differ from France are the market's
own (country, name tokens)."""

from __future__ import annotations

import importlib.util
import json

from promo_ops.config import REPO_ROOT, brands_config, kids_exclude_video_groups
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

_spec = importlib.util.spec_from_file_location(
    "build_plan_form", REPO_ROOT / "scripts" / "build_plan_form.py")
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)

OLDER_X, YOUNGER_X = "165055190", "165056324"


def _plan(region, audience):
    return support_plan_from_dict({
        "promoted_title": "Kung Fu Panda", "region": region,
        "campaign": {"name": f"Pluto TV - Kids - {region}"}, "season_or_messaging": "Manut",
        "durations": [30, 15], "content_type": "show", "kids_audience": audience,
        "exclude_series": ["Kung Fu Panda"],
        "io_brand": f"Kung Fu Panda - Kids (Promo) ({region})"})


def _order(region, audience=("older",)):
    return OrderBuilder().build(_plan(region, list(audience)))


def _shape(order, region):
    """Everything about the build EXCEPT the market's own identity (country, region tokens)."""
    rows = []
    for p in order.placements:
        body = FreeWheelClient._placement_body(p)
        body.pop("geography_targeting", None)
        body.pop("_geo_country_names", None)
        body.pop("name", None)
        body.pop("schedule", None)
        rows.append((p.name.replace(f"- {region}", "- XX").replace(f"({region})", "(XX)"),
                     p.format, p.tier, p.duration, json.dumps(body, sort_keys=True)))
    return sorted(rows)


def test_config_is_a_standard_kids_pluto_campaign_not_the_spanish_clone():
    br, fr = brands_config()["brands"]["pluto_tv_kids_br"], brands_config()["brands"]["pluto_tv_kids_fr"]
    assert br["kids"] is True
    assert br["formats"] == fr["formats"] == ["pplus_kids_remnant"]
    assert br["ad_unit_groups"] == fr["ad_unit_groups"]
    assert br.get("format_overrides") == fr.get("format_overrides")
    assert "relationship_sets" not in br           # no hand-written (US-specific) sets
    assert br["campaign_name"] == "Pluto TV - Kids - BR" and br["template_campaign_id"] == "72285933"


def test_builds_exactly_like_france_apart_from_the_market():
    br, fr = _order("BR", ("older", "younger")), _order("FR", ("older", "younger"))
    assert br.placements, "BR must build placements once a Kids audience is selected"
    assert _shape(br, "BR") == _shape(fr, "FR")


def test_it_still_targets_brazil_and_its_own_name():
    order = _order("BR")
    for p in order.placements:
        body = FreeWheelClient._placement_body(p)
        assert body["geography_targeting"]["include"]["country"] == ["21"]     # Brazil
        assert p.name.endswith("- Kids - BR")


def test_older_and_younger_exclusion_vgs_are_on_every_placement():
    older, younger = _order("BR", ("older",)), _order("BR", ("younger",))
    assert kids_exclude_video_groups(["older"]) == [OLDER_X]
    for order, want, other in ((older, OLDER_X, YOUNGER_X), (younger, YOUNGER_X, OLDER_X)):
        for p in order.placements:
            body = json.dumps(FreeWheelClient._placement_body(p))
            assert want in body, (p.name, want)
            assert other not in body, (p.name, other)


def test_no_kids_audience_builds_nothing_like_every_other_kids_campaign():
    assert _order("BR", ()).placements == []
    assert _order("FR", ()).placements == []


def test_brand_step_treats_it_as_a_kids_order():
    order = _order("BR")
    assert order.io_brand_kids is True and order.io_brand == "Kung Fu Panda - Kids (Promo) (BR)"
    assert order.name.endswith("- Kids - BR")


def test_form_offers_the_older_younger_picker_for_it():
    camps = {c["name"]: c for c in pf.app_data()["campaigns"]}
    assert camps["Pluto TV - Kids - BR"]["kids"] is True
