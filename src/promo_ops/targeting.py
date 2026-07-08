"""The targeting engine.

Takes a SupportPlan and a format, and produces the TieredTargeting for that format
by applying config/tiers.yaml. This is the deterministic core of the tool: given the
same plan it always produces the same tier stack, so the mapping can be reviewed and
diffed before anything is pushed to FreeWheel.

Tier rules (from the Inventory & Targeting Strategy deck, Slide 5):
  * Tier 1 is region-gated (USA, AU, CA, LATAM, BR). Its audience_segments dimension
    resolves the showlist to FreeWheel audience segments via AudienceSegmentResolver.
  * Tiers 2-4 apply globally.
  * Which tiers a format uses comes from the plan (formats[].tiers) or, failing that,
    config/tiers.yaml `format_tier_defaults`.
"""

from __future__ import annotations

from typing import Optional

from .audience_segments import AudienceSegmentResolver
from .config import regions_config, tiers_config
from .models import SupportPlan, Tier, TargetingDimension, TieredTargeting
from .standard_attributes import DIMENSION_ATTRIBUTE_TYPE, StandardAttributeResolver


class TargetingEngine:
    def __init__(self, resolver: Optional[AudienceSegmentResolver] = None,
                 attr_resolver: Optional[StandardAttributeResolver] = None):
        self._tiers_cfg = tiers_config()
        self._regions_cfg = regions_config()
        self.resolver = (resolver or AudienceSegmentResolver()).load()
        self.attr_resolver = (attr_resolver or StandardAttributeResolver()).load()

    # --- tier selection -------------------------------------------------- #

    def tiers_for_format(self, plan: SupportPlan, fmt: str,
                         override: Optional[list[int]] = None) -> list[int]:
        if override:
            return override
        defaults = self._tiers_cfg.get("format_tier_defaults", {})
        return defaults.get(fmt, [1, 2, 3, 4])

    def _region_is_tier1_eligible(self, region: str) -> bool:
        region_cfg = self._regions_cfg.get("regions", {}).get(region, {})
        return bool(region_cfg.get("tier1_eligible", False))

    def _tier_applies_in_region(self, tier_cfg: dict, region: str) -> bool:
        applies = tier_cfg.get("applies_to_regions", "global")
        if applies == "global":
            return True
        return region in applies

    # --- dimension building ---------------------------------------------- #

    def _build_dimension(self, plan: SupportPlan, dim_cfg: dict) -> TargetingDimension:
        source = dim_cfg["source"]
        dim = TargetingDimension(
            key=dim_cfg["key"],
            label=dim_cfg["label"],
            source=source,
        )

        if dim_cfg["key"] == "audience_segments":
            resolved: list[dict] = []
            # 1. Segments named directly in the plan/sheet (Tier 1 section).
            for seg in plan.audience_segments:
                resolved.append({
                    "segment_name": seg,
                    "segment_id": None,
                    "platform": None,
                    "region": plan.region,
                    "source": "manual (sheet/plan)",
                })
            # 2. Segments auto-resolved from the showlist via the Audience Segments doc.
            matches = self.resolver.resolve_all(plan.showlist, region=plan.region)
            unresolved = []
            for m in matches:
                if m.matched:
                    resolved.extend(m.to_dict()["segments"])
                else:
                    unresolved.append(m.show)
            dim.resolved = resolved
            dim.values = [s["segment_name"] for s in resolved]
            if unresolved:
                dim.notes = (
                    f"{len(unresolved)} show(s) have no auto-matched FreeWheel audience "
                    f"segment — add them to the Tier 1 Audience Segments section of the "
                    f"sheet, or request/add them to the Audience Segments doc: "
                    f"{', '.join(unresolved)}"
                )
            return dim

        if dim_cfg["key"] == "run_of_network_except_promoted":
            dim.values = [f"EXCLUDE: {plan.promoted_title}"]
            return dim

        value = plan.source_value(source)
        if isinstance(value, list):
            dim.values = list(value)
        elif value is not None:
            dim.values = [value]

        # Resolve content dimensions (genre / network / Pluto category+channel) to
        # FreeWheel Standard Attribute IDs. Unmatched names are surfaced, not guessed.
        if dim_cfg["key"] in DIMENSION_ATTRIBUTE_TYPE and dim.values:
            matches = self.attr_resolver.resolve_dimension(dim_cfg["key"], dim.values)
            dim.resolved = [
                {"name": m.name, "id": m.id, "type": m.type, "matched": m.matched}
                for m in matches if m.matched
            ]
            unmatched = [m.name for m in matches if not m.matched]
            if unmatched:
                dim.notes = (
                    f"{len(unmatched)} value(s) have no FreeWheel Standard Attribute "
                    f"match (check spelling vs FreeWheel, or sync): {', '.join(unmatched)}"
                )

        # Sensible defaults for optional inputs.
        if dim_cfg["key"] == "pplus_user_state" and not dim.values:
            dim.values = ["New", "Light", "Medium", "Heavy"]
            dim.notes = "defaulted (no pplus_user_states in plan)"
        if dim_cfg["key"] == "geo" and not dim.values:
            geo = self._regions_cfg.get("regions", {}).get(plan.region, {}).get("geo_codes", [])
            dim.values = list(geo)

        return dim

    # --- public API ------------------------------------------------------ #

    def build(self, plan: SupportPlan, fmt: str,
              tier_override: Optional[list[int]] = None) -> TieredTargeting:
        selected = set(self.tiers_for_format(plan, fmt, tier_override))
        result = TieredTargeting(format=fmt)

        for tier_cfg in self._tiers_cfg.get("tiers", []):
            tid = tier_cfg["id"]
            if tid not in selected:
                continue
            # Tier 1 is region-gated.
            if tid == 1 and not self._region_is_tier1_eligible(plan.region):
                continue
            if not self._tier_applies_in_region(tier_cfg, plan.region):
                continue

            tier = Tier(id=tid, name=tier_cfg["name"])
            for dim_cfg in tier_cfg.get("dimensions", []):
                dim = self._build_dimension(plan, dim_cfg)
                # Keep audience_segments even when empty so its "needs to be added"
                # note always surfaces — that surfacing is the point of Tier 1.
                if not dim.is_empty or dim.key == "audience_segments":
                    tier.dimensions.append(dim)
            if tier.dimensions:
                result.tiers.append(tier)

        return result
