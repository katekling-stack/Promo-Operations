"""Assemble an Order with one Placement per format from a SupportPlan.

Combines three inputs:
  * the support plan (what to promote, where, to whom),
  * the brand config (which VCBS advertiser / template campaign to clone), and
  * the placement templates (format defaults: caps, endpoints, durations),
running each format's targeting through the TargetingEngine.

The result is a fully-populated Order dataclass — pure data, ready to serialize for
dry-run review or to hand to integrations/freewheel.py for creation.
"""

from __future__ import annotations

from typing import Optional

from .config import brands_config, placement_templates_config
from .models import Order, Placement, SupportPlan
from .targeting import TargetingEngine


class OrderBuilder:
    def __init__(self, engine: Optional[TargetingEngine] = None):
        self.engine = engine or TargetingEngine()
        self._brands = brands_config()
        self._templates = placement_templates_config()

    def _brand_cfg(self, brand: str) -> dict:
        brands = self._brands.get("brands", {})
        if brand not in brands:
            raise KeyError(
                f"Unknown brand {brand!r}. Known brands: {', '.join(brands)}"
            )
        return brands[brand]

    def _placement(self, plan: SupportPlan, fmt: str, brand_cfg: dict) -> Placement:
        fmt_templates = self._templates.get("formats", {})
        if fmt not in fmt_templates:
            raise KeyError(
                f"Unknown format {fmt!r}. Known formats: {', '.join(fmt_templates)}"
            )
        tmpl = fmt_templates[fmt]
        defaults = self._templates.get("defaults", {})

        name = tmpl["naming"].format(
            promoted_title=plan.promoted_title,
            region=plan.region,
            format_code=tmpl["format_code"],
            brand=brand_cfg["display_name"],
            flight_code=plan.flight.code or "",
        ).strip()

        targeting = self.engine.build(plan, fmt)

        extra = {
            k: tmpl[k]
            for k in ("spec", "standard_sizes", "salesforce_asset_field")
            if k in tmpl
        }

        return Placement(
            name=name,
            format=fmt,
            format_code=tmpl["format_code"],
            region=plan.region,
            targeting=targeting,
            frequency_cap=defaults.get("frequency_cap"),
            endpoints=list(tmpl.get("endpoints", [])),
            platforms=list(tmpl.get("platforms", [])),
            creative_durations_priority=list(tmpl.get("creative_durations_priority", [])),
            extra=extra,
        )

    def build(self, plan: SupportPlan) -> Order:
        brand_cfg = self._brand_cfg(plan.brand)

        campaign = dict(plan.campaign)
        campaign.setdefault("name", f"{plan.promoted_title} - {plan.region}")

        order = Order(
            name=f"{plan.promoted_title} - {plan.region}",
            promoted_title=plan.promoted_title,
            brand=plan.brand,
            region=plan.region,
            network_id=str(self._brands.get("network_id")) if self._brands.get("network_id") else None,
            advertiser=dict(plan.advertiser),
            campaign=campaign,
            flight=plan.flight,
            template_ref={
                "template_campaign_id": brand_cfg.get("template_campaign_id"),
                "template_io_id": brand_cfg.get("template_io_id"),
                "advertiser_name_contains": brand_cfg.get("advertiser_name_contains"),
            },
        )

        for fmt in plan.formats:
            order.placements.append(self._placement(plan, fmt, brand_cfg))

        return order
