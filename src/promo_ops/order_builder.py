"""Assemble an Order (Insertion Order) with per-tier placements from a SupportPlan.

Combines:
  * the support plan (what to promote, where, to whom, durations, season/messaging),
  * the brand config (VCBS advertiser / template campaign), and
  * the placement templates + priorities config (naming, caps, priority per tier),
running each format's targeting through the TargetingEngine.

Placement model matches the live FreeWheel structure: one placement per TIER (and,
for video, per DURATION), named:

    {title} - {season_or_messaging} - {duration} - Tier N - {region}

Guaranteed P+ formats (Premium Pre-Roll, Essential Bumper) are named by content:

    {title} [ShowID:{id}]     (show)      {title} [MovieID:{id}]   (movie)

The result is a pure-data Order, ready for dry-run review or the FreeWheel client.
"""

from __future__ import annotations

from typing import Optional

from .config import brands_config, placement_templates_config, priorities_config
from .models import Order, Placement, SupportPlan, TieredTargeting
from .targeting import TargetingEngine


class OrderBuilder:
    def __init__(self, engine: Optional[TargetingEngine] = None):
        self.engine = engine or TargetingEngine()
        self._brands = brands_config()
        self._templates = placement_templates_config()
        self._priorities = priorities_config()

    def _brand_cfg(self, brand: Optional[str]) -> dict:
        # `brand` is an optional legacy grouping; the exact Advertiser + Campaign in
        # the plan are authoritative. Return {} when absent/unknown (no error).
        return self._brands.get("brands", {}).get(brand or "", {})

    # --- naming ---------------------------------------------------------- #

    @staticmethod
    def _tier_name(title, season, duration, tier, region) -> str:
        # {title} - {season} - {duration} - Tier N - {region}, skipping blanks.
        parts = [title, season, (str(duration) if duration else None), f"Tier {tier}", region]
        return " - ".join(p for p in parts if p)

    @staticmethod
    def _guaranteed_name(plan: SupportPlan) -> str:
        label = "MovieID" if (plan.content_type or "show").lower() == "movie" else "ShowID"
        return f"{plan.promoted_title} [{label}:{plan.content_id or ''}]"

    # --- caps / priority ------------------------------------------------- #

    def _freq_cap(self, fmt: str) -> str:
        caps = self._priorities.get("frequency_caps", {})
        return caps.get("by_format", {}).get(fmt) or caps.get("default")

    def _priority_for_tier(self, tier_id: int):
        return self._priorities.get("priority_by_tier", {}).get(tier_id)

    def _priority_for_format(self, fmt: str):
        return self._priorities.get("priority_by_format", {}).get(fmt)

    def _durations(self, plan: SupportPlan) -> list[int]:
        return plan.durations or list(self._priorities.get("default_durations", [30]))

    # --- placement building ---------------------------------------------- #

    def _placements_for_format(self, plan: SupportPlan, fmt: str) -> list[Placement]:
        fmt_templates = self._templates.get("formats", {})
        if fmt not in fmt_templates:
            raise KeyError(f"Unknown format {fmt!r}. Known formats: {', '.join(fmt_templates)}")
        tmpl = fmt_templates[fmt]
        exclude = plan.exclude_show or plan.promoted_title
        recommended = plan.recommended_show or plan.promoted_title
        extra = {k: tmpl[k] for k in ("spec", "standard_sizes", "salesforce_asset_field") if k in tmpl}

        def base(name, targeting, **kw) -> Placement:
            return Placement(
                name=name, format=fmt, format_code=tmpl["format_code"], region=plan.region,
                targeting=targeting, endpoints=list(tmpl.get("endpoints", [])),
                platforms=list(tmpl.get("platforms", [])), exclusions=[exclude],
                nests_in=tmpl.get("nests_in", "new_insertion_order"), extra=extra, **kw)

        # Guaranteed formats: one placement, content-named, built from args.
        if tmpl.get("guaranteed"):
            return [base(
                self._guaranteed_name(plan),
                TieredTargeting(format=fmt),
                guaranteed=True,
                arguments={"genre": list(plan.genres), "recommended_show": recommended},
                priority_level=self._priority_for_format(fmt),
                frequency_cap=self._freq_cap(fmt),
            )]

        targeting = self.engine.build(plan, fmt)
        uses_durations = bool(tmpl.get("uses_durations"))
        durations = self._durations(plan) if uses_durations else [None]

        placements: list[Placement] = []
        for tier in targeting.tiers:
            for dur in durations:
                name = self._tier_name(plan.promoted_title, plan.season_or_messaging,
                                       dur, tier.id, plan.region)
                placements.append(base(
                    name,
                    TieredTargeting(format=fmt, tiers=[tier]),   # one tier per placement
                    tier=tier.id,
                    duration=dur,
                    season_or_messaging=plan.season_or_messaging,
                    priority_level=self._priority_for_tier(tier.id),
                    frequency_cap=self._freq_cap(fmt),
                    creative_durations_priority=list(tmpl.get("creative_durations_priority", [])),
                ))
        return placements

    def build(self, plan: SupportPlan) -> Order:
        brand_cfg = self._brand_cfg(plan.brand)
        io_name = plan.insertion_order_name or f"{plan.promoted_title} - {plan.region}"

        order = Order(
            name=io_name,
            promoted_title=plan.promoted_title,
            brand=plan.brand,
            region=plan.region,
            network_id=str(self._brands.get("network_id")) if self._brands.get("network_id") else None,
            advertiser=dict(plan.advertiser),
            campaign=dict(plan.campaign),
            flight=plan.flight,
            template_ref={
                # Exact advertiser/campaign come from the plan; brand_cfg is fallback.
                "advertiser_id": plan.advertiser.get("resolved_id"),
                "campaign_id": plan.campaign.get("resolved_id"),
                "template_io_id": plan.template_io_id or brand_cfg.get("template_io_id"),
                "brand_id": plan.brand_id,
            },
        )
        for fmt in plan.formats:
            order.placements.extend(self._placements_for_format(plan, fmt))
        return order
