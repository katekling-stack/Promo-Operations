"""Every campaign called 'Kids' must carry the kids flag: it drives the kids order-level frequency
cap (1 per 15 min), the Older/Younger Kids video-group exclusions, and the Kids audience gate.
Regression: six Kids campaigns (Pluto ES/French CA/LATAM Kids, three MTVE Kids) were built as adult."""

from __future__ import annotations

from promo_ops.config import brands_config
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def test_every_kids_named_campaign_is_flagged_kids():
    missing = [k for k, v in brands_config()["brands"].items()
               if "kids" in str(v.get("campaign_name") or "").lower() and not v.get("kids")]
    assert missing == []


def test_the_six_now_get_the_kids_order_cap():
    for camp, region in [("Pluto TV - Kids - En Espanol - USA", "USA"), ("MTVE - Kids - GSA", "GSA"),
                         ("MTVE - Kids - ES", "ES"), ("MTVE - Kids - LATAM", "LATAM"),
                         ("Pluto TV - Kids - French - CA", "CA"), ("Pluto TV - Kids - LATAM", "LATAM")]:
        order = OrderBuilder().build(support_plan_from_dict({
            "promoted_title": "Frasier", "region": region, "campaign": {"name": camp},
            "durations": [30], "genres": ["Comedy"], "kids_audience": ["younger"],
            "flight": {"start": "2026-10-01", "end": "2026-11-01"}}))
        assert order.frequency_caps == ["1 per 15 min"], camp
