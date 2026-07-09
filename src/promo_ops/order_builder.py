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

from .config import (ad_units_config, brands_config, placement_templates_config,
                     priorities_config, regions_config)
from .ad_units import AdUnitResolver
from .geo import CountryResolver
from .models import Order, Placement, SupportPlan, TieredTargeting
from .targeting import TargetingEngine


class OrderBuilder:
    def __init__(self, engine: Optional[TargetingEngine] = None,
                 countries: Optional[CountryResolver] = None,
                 ad_unit_resolver: Optional[AdUnitResolver] = None):
        self.engine = engine or TargetingEngine()
        self.countries = (countries or CountryResolver()).load()
        self.ad_unit_resolver = (ad_unit_resolver or AdUnitResolver()).load()
        self._brands = brands_config()
        self._templates = placement_templates_config()
        self._priorities = priorities_config()
        self._regions = regions_config()
        self._ad_units = ad_units_config()

    def _geo_country_names(self, region: str) -> list:
        """Country NAMES the team selects in FreeWheel for this region."""
        return list(self._regions.get("regions", {}).get(region, {}).get("countries", []))

    def _geo_country_ids(self, names: list) -> list:
        """Resolve country names -> FW country IDs (via data/geo table)."""
        return self.countries.ids_for(names)

    def _ad_unit_names(self, fmt: str) -> list:
        group = self._ad_units.get("format_ad_unit_group", {}).get(fmt)
        return list(self._ad_units.get("ad_units", {}).get(group, [])) if group else []

    def _ad_unit_ids(self, fmt: str) -> list:
        # Resolve the format's ad-unit NAMES -> FW ad-unit IDs (data/ad_units table).
        return self.ad_unit_resolver.ids_for(self._ad_unit_names(fmt))

    def _brand_cfg(self, brand: Optional[str]) -> dict:
        # `brand` is an optional legacy grouping; the exact Advertiser + Campaign in
        # the plan are authoritative. Return {} when absent/unknown (no error).
        return self._brands.get("brands", {}).get(brand or "", {})

    # --- naming ---------------------------------------------------------- #

    @staticmethod
    def _tier_name(title, season, duration, tier, region, token=None) -> str:
        # {title} - {season} - {duration|token} - Tier N - {region}, skipping blanks.
        # Video uses the duration; formats without a duration (e.g. Pause Ad) use token.
        slot = str(duration) if duration else token
        parts = [title, season, slot, f"Tier {tier}", region]
        return " - ".join(p for p in parts if p)

    def _guaranteed_name(self, plan: SupportPlan, tmpl: dict) -> str:
        # "Paramount + - {unit_label} - {plan_label} - {title} - {region} - [ShowID:{id}]"
        # (mirrors the Dutton Ranch guaranteed placements).
        label = "MovieID" if (plan.content_type or "show").lower() == "movie" else "ShowID"
        unit = tmpl.get("unit_label", "")
        plan_label = tmpl.get("plan_label", "")
        parts = ["Paramount +", unit, plan_label, plan.promoted_title, plan.region]
        return " - ".join(p for p in parts if p) + f" - [{label}:{plan.content_id or ''}]"

    # --- caps / priority ------------------------------------------------- #

    def _freq_cap(self, tier_id: Optional[int], fmt: str) -> str:
        caps = self._priorities.get("frequency_caps", {})
        by_fmt = caps.get("by_format", {}).get(fmt)
        if by_fmt:
            return by_fmt
        if tier_id is not None:
            per_tier = caps.get("by_tier", {}).get(tier_id)
            if per_tier:
                return per_tier
        return caps.get("default")

    def _priority(self, tier_id: int, duration: Optional[int]):
        """Priority number = tier base + duration offset (Tier 4 = flat)."""
        if tier_id == 4:
            return self._priorities.get("tier4_priority", 10)
        base = self._priorities.get("priority_base_by_tier", {}).get(tier_id)
        if base is None:
            return None
        offsets = self._priorities.get("duration_offsets", {})
        offset = offsets.get(str(duration), self._priorities.get("default_duration_offset", 0))
        return base + offset

    def _guaranteed_priority(self):
        return self._priorities.get("guaranteed_priority", "SPONSORSHIP")

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

        geo_names = self._geo_country_names(plan.region)
        geo_ids = self._geo_country_ids(geo_names)
        ad_unit_names = self._ad_unit_names(fmt)
        ad_unit_ids = self._ad_unit_ids(fmt)

        def base(name, targeting, **kw) -> Placement:
            return Placement(
                name=name, format=fmt, format_code=tmpl["format_code"], region=plan.region,
                targeting=targeting, endpoints=list(tmpl.get("endpoints", [])),
                platforms=list(tmpl.get("platforms", [])), exclusions=[exclude],
                geo_country_names=geo_names, geo_country_ids=geo_ids,
                ad_unit_names=ad_unit_names, ad_unit_ids=ad_unit_ids,
                nests_in=tmpl.get("nests_in", "new_insertion_order"), extra=extra, **kw)

        # Guaranteed formats: one placement, content-named, built from args.
        if tmpl.get("guaranteed"):
            return [base(
                self._guaranteed_name(plan, tmpl),
                TieredTargeting(format=fmt),
                guaranteed=True,
                arguments={"genre": list(plan.genres), "recommended_show": recommended},
                priority_level=self._guaranteed_priority(),
                frequency_cap=self._freq_cap(None, fmt),
            )]

        targeting = self.engine.build(plan, fmt)
        uses_durations = bool(tmpl.get("uses_durations"))
        durations = self._durations(plan) if uses_durations else [None]
        name_token = tmpl.get("name_token")   # e.g. "Pause Ad" for non-duration formats

        placements: list[Placement] = []
        for tier in targeting.tiers:
            for dur in durations:
                name = self._tier_name(plan.promoted_title, plan.season_or_messaging,
                                       dur, tier.id, plan.region, token=name_token)
                placements.append(base(
                    name,
                    TieredTargeting(format=fmt, tiers=[tier]),   # one tier per placement
                    tier=tier.id,
                    duration=dur,
                    season_or_messaging=plan.season_or_messaging,
                    priority_level=self._priority(tier.id, dur),
                    frequency_cap=self._freq_cap(tier.id, fmt),
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
