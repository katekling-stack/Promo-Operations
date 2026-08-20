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
from .config import pluto_config, regions_config, tiers_config
from .models import SupportPlan, Tier, TargetingDimension, TieredTargeting
from .series import SeriesResolver
from .site_groups import SiteGroupResolver
from .standard_attributes import DIMENSION_ATTRIBUTE_TYPE, StandardAttributeResolver


class TargetingEngine:
    def __init__(self, resolver: Optional[AudienceSegmentResolver] = None,
                 attr_resolver: Optional[StandardAttributeResolver] = None,
                 series_resolver: Optional[SeriesResolver] = None,
                 site_group_resolver: Optional[SiteGroupResolver] = None):
        self._tiers_cfg = tiers_config()
        self._regions_cfg = regions_config()
        self._pluto_cfg = pluto_config()
        self.resolver = (resolver or AudienceSegmentResolver()).load()
        self.attr_resolver = (attr_resolver or StandardAttributeResolver()).load()
        self.series_resolver = (series_resolver or SeriesResolver()).load()
        self.site_group_resolver = (site_group_resolver or SiteGroupResolver()).load()
        # Genre TARGETS via VG:Genre video groups (not Standard Attributes), so genre
        # validity is judged against this resolver.
        from .video_groups import GenreVideoGroupResolver
        self._genre_vg = GenreVideoGroupResolver().load()

    def _region_code(self, region: str) -> str:
        return self._regions_cfg.get("regions", {}).get(region, {}).get("code", region)

    def _is_domestic(self, region: str) -> bool:
        return bool(self._regions_cfg.get("regions", {}).get(region, {}).get("domestic", False))

    # --- tier selection -------------------------------------------------- #

    def tiers_for_format(self, plan: SupportPlan, fmt: str,
                         override: Optional[list[int]] = None) -> list[int]:
        if override:
            return override
        defaults = self._tiers_cfg.get("format_tier_defaults", {})
        return defaults.get(fmt, [1, 2, 3, 4])

    def _region_is_tier1_eligible(self, region: str) -> bool:
        # All adult campaigns support Tier 1-4 REGARDLESS of a market's historical setup,
        # so Tier 1 is on by default (every region in regions.yaml also sets it explicitly).
        # A region must opt OUT with `tier1_eligible: false` to drop Tier 1.
        region_cfg = self._regions_cfg.get("regions", {}).get(region, {})
        return bool(region_cfg.get("tier1_eligible", True))

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
            # 1. Segments named directly in the plan/sheet (Tier 1 section). Resolve to
            #    an ID via the segment doc where possible (e.g. P+ groupings).
            for seg in plan.audience_segments:
                m = self.resolver.resolve(seg, region=plan.region)
                if m.matched:
                    resolved.extend(m.to_dict()["segments"])
                else:
                    resolved.append({
                        "segment_name": seg, "segment_id": None,
                        "region": plan.region, "source": "manual (sheet/plan)",
                    })
            # 2. Segments auto-resolved from the showlist via the Audience Segments doc.
            #    EXACT per show (like the Tier-2 series affinity): 'CSI Miami' resolves only
            #    to its own segment, never the franchise family ('The Real CSI Miami').
            matches = self.resolver.resolve_all_exact(plan.showlist, region=plan.region)
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
                    f"{len(unresolved)} show(s) need their Tier 1 DDA audience item "
                    f"(convention 'GL-DDA-1P-SHOW_<Show>'; search 'DDA + show' in FreeWheel "
                    f"Audience Items or run sync-audience-items): {', '.join(unresolved)}"
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

        # Tier 2 content-affinity showlist -> FreeWheel Video Series IDs. EXACT-name
        # match only: picking "Scream" targets the "Scream" series, not the whole
        # "Scream 2/3/4" family (what you select in the picklist is what you get).
        if dim_cfg["key"] == "content_affinity_showlist" and dim.values:
            matches = self.series_resolver.resolve_all_exact(dim.values)
            dim.resolved = [
                {"show": m.show, "id": s["id"], "series_name": s["name"]}
                for m in matches for s in m.series
            ]
            unmatched = [m.show for m in matches if not m.matched]
            if unmatched:
                dim.notes = (
                    f"{len(unmatched)} show(s) matched no FreeWheel Video Series "
                    f"(check the title or sync series): {', '.join(unmatched)}"
                )

        # Pluto channels/categories -> FreeWheel Site Groups (config/pluto.yaml naming).
        # Tier 2 = channels, Tier 3 = promo categories. Each keyword is a select-all
        # within its Pluto section (prefix..suffix) — the team's search-and-select-all
        # workflow. Unmatched keywords are surfaced, not guessed.
        naming = self._pluto_cfg.get("naming", {})
        pattern = None
        if dim_cfg["key"] in ("pluto_channel_list", "pluto_channel"):
            pattern = naming["channel"]
        elif dim_cfg["key"] == "pluto_category":
            pattern = naming["category_domestic"] if self._is_domestic(plan.region) \
                else naming["category_international"]
        if pattern and dim.values:
            code = self._region_code(plan.region)
            resolved: list[dict] = []
            unmatched: list[str] = []
            for v in dim.values:
                full = pattern.format(region_code=code, name=v)     # canonical SG name
                prefix, _, suffix = pattern.format(region_code=code, name="\x00").partition("\x00")
                # EXACT NAME match — selecting "Top Gear" targets ONLY the "Top Gear"
                # channel(s), not "Top Gear Challenge". A channel can have multiple real
                # versions under the same name (e.g. two "Gunsmoke" SGs) — include ALL of
                # them; we only drop the substring bloat, never same-name versions.
                m = self.site_group_resolver.select_exact(v, prefix=prefix, suffix=suffix)
                if m.matched:
                    for sg in m.site_groups:
                        resolved.append({"segment_name": sg["name"], "id": sg["id"],
                                         "keyword": v, "source": "pluto_site_group"})
                else:
                    resolved.append({"segment_name": full, "id": None,
                                     "keyword": v, "source": "pluto_site_group"})
                    unmatched.append(v)
            dim.resolved = resolved
            if unmatched:
                dim.notes = (
                    f"{len(unmatched)} Pluto keyword(s) matched no Site Group under "
                    f"'{pattern.format(region_code=code, name='…')}' "
                    f"(check the name or sync site groups): {', '.join(unmatched)}"
                )

        # Resolve content dimensions (genre / network) to FreeWheel Standard Attribute
        # IDs. Unmatched names are surfaced, not guessed.
        if dim_cfg["key"] in DIMENSION_ATTRIBUTE_TYPE and dim.values:
            matches = self.attr_resolver.resolve_dimension(dim_cfg["key"], dim.values)
            dim.resolved = [
                {"name": m.name, "id": m.id, "type": m.type, "matched": m.matched}
                for m in matches if m.matched
            ]
            unmatched = [m.name for m in matches if not m.matched]
            # Genre actually targets via VG:Genre video groups — so a genre that resolves
            # as a video group is valid even if it has no Standard Attribute. Don't warn on
            # those (prevents false alarms like "Mobster" that target fine).
            if dim_cfg["key"] == "genre" and unmatched:
                unmatched = [g for g in unmatched if not self._genre_vg.ids_for([g])]
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
              tier_override: Optional[list[int]] = None,
              skip_dimensions: Optional[set] = None) -> TieredTargeting:
        selected = set(self.tiers_for_format(plan, fmt, tier_override))
        skip = skip_dimensions or set()
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
                if dim_cfg["key"] in skip:            # e.g. My5 drops pplus_user_state
                    continue
                dim = self._build_dimension(plan, dim_cfg)
                # Keep audience_segments even when empty so its "needs to be added"
                # note always surfaces — that surfacing is the point of Tier 1.
                if not dim.is_empty or dim.key == "audience_segments":
                    tier.dimensions.append(dim)
            if tier.dimensions:
                result.tiers.append(tier)

        return result
