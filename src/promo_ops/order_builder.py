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

from .config import (ad_units_config, brands_config, kids_targeting_config,
                     kids_video_groups, placement_templates_config,
                     priorities_config, regions_config)
from .ad_units import AdUnitResolver
from .geo import CountryResolver
from .models import Order, Placement, SupportPlan, TieredTargeting
from .series import SeriesResolver
from .targeting import TargetingEngine
from .video_groups import GenreVideoGroupResolver


class OrderBuilder:
    def __init__(self, engine: Optional[TargetingEngine] = None,
                 countries: Optional[CountryResolver] = None,
                 ad_unit_resolver: Optional[AdUnitResolver] = None,
                 genre_resolver: Optional[GenreVideoGroupResolver] = None):
        self.engine = engine or TargetingEngine()
        self.countries = (countries or CountryResolver()).load()
        self.ad_unit_resolver = (ad_unit_resolver or AdUnitResolver()).load()
        self.genre_resolver = (genre_resolver or GenreVideoGroupResolver()).load()
        self._brands = brands_config()
        self._templates = placement_templates_config()
        self._priorities = priorities_config()
        self._regions = regions_config()
        self._ad_units = ad_units_config()

    @staticmethod
    def _ids_from_tier(tier) -> dict:
        """Extract resolved FW IDs from a tier's dimensions, by kind."""
        out: dict[str, list] = {}
        for d in tier.dimensions:
            if d.key == "audience_segments":
                out.setdefault("dda", []).extend(
                    r["segment_id"] for r in d.resolved if r.get("segment_id"))
            elif d.key == "content_affinity_showlist":
                out.setdefault("series", []).extend(r["id"] for r in d.resolved if r.get("id"))
            elif d.key == "pluto_channel_list":
                out.setdefault("channels", []).extend(r["id"] for r in d.resolved if r.get("id"))
            elif d.key == "pluto_category":
                out.setdefault("categories", []).extend(r["id"] for r in d.resolved if r.get("id"))
        return out

    def _targeting_ids(self, plan: SupportPlan, tier) -> dict:
        ids = self._ids_from_tier(tier)
        # Genre (Tier 3) -> genre Video Groups. Resolve from the plan genres when the
        # tier carries a genre dimension.
        if any(d.key == "genre" for d in tier.dimensions) and plan.genres:
            vgs = self.genre_resolver.ids_for(list(plan.genres))
            if vgs:
                ids["genre_vgs"] = vgs
        return ids

    def _geo_country_names(self, region: str) -> list:
        """Country NAMES the team selects in FreeWheel for this region."""
        return list(self._regions.get("regions", {}).get(region, {}).get("countries", []))

    def _geo_country_ids(self, names: list) -> list:
        """Resolve country names -> FW country IDs (via data/geo table)."""
        return self.countries.ids_for(names)

    def _ad_unit_group(self, brand_cfg: dict, fmt: str) -> Optional[str]:
        # Per-brand ad-unit group override wins over the global default.
        override = (brand_cfg.get("ad_unit_groups") or {}).get(fmt)
        return override or self._ad_units.get("format_ad_unit_group", {}).get(fmt)

    def _ad_unit_names(self, brand_cfg: dict, fmt: str) -> list:
        group = self._ad_unit_group(brand_cfg, fmt)
        return list(self._ad_units.get("ad_units", {}).get(group, [])) if group else []

    def _ad_unit_ids(self, brand_cfg: dict, fmt: str) -> list:
        # Resolve the format's ad-unit NAMES -> FW ad-unit IDs (data/ad_units table).
        return self.ad_unit_resolver.ids_for(self._ad_unit_names(brand_cfg, fmt))

    def _ad_units_for_duration(self, brand_cfg: dict, fmt: str, tmpl: dict,
                               duration) -> tuple[list, list]:
        """Ad-unit (names, ids) for a duration. House Pre-Roll runs on short creatives
        only — it drops at `drop_preroll_at_duration` (e.g. 30s: mid+post only)."""
        names = self._ad_unit_names(brand_cfg, fmt)
        drop_at = tmpl.get("drop_preroll_at_duration")
        if drop_at and duration and int(duration) >= int(drop_at):
            # `drop_units` (explicit names) drops only those; else drop by "preroll"
            # substring. UK P+ keeps the INTL pre-roll, dropping only the House Pre-Roll.
            drop_units = tmpl.get("drop_units")
            if drop_units:
                names = [n for n in names if n not in drop_units]
            else:
                names = [n for n in names if "preroll" not in n.lower()]
        return names, self.ad_unit_resolver.ids_for(names)

    def _self_exclusions(self, plan: SupportPlan, pluto_brand: bool = False) -> tuple[list, list]:
        """The promoted show's OWN Video Series IDs + Channel SG IDs, to exclude so it
        never promos against itself. Resolved from the exclude show (defaults to the
        promoted title) by EXACT name — only the series/channel that IS the title, not
        every one containing the title words. The Channel SG exclusion applies ONLY to
        Pluto TV brand campaigns ("Pluto TV - Region ..."); a P+ (or other) title does
        not exclude its Pluto channel."""
        target = plan.exclude_show or plan.promoted_title
        if not target:
            return [], []
        series = [s["id"] for s in self.engine.series_resolver.resolve_exact(target).series]
        channel_sgs: list = []
        naming = (self._pluto_cfg().get("naming") or {}).get("channel")
        if pluto_brand and naming:
            code = self._regions.get("regions", {}).get(plan.region, {}).get("code", plan.region)
            prefix, _, suffix = naming.format(region_code=code, name="\x00").partition("\x00")
            m = self.engine.site_group_resolver.select_exact(target, prefix=prefix, suffix=suffix)
            if m.matched:
                channel_sgs = [sg["id"] for sg in m.site_groups]
        return series, channel_sgs

    def _self_audience_exclusions(self, plan: SupportPlan) -> list[str]:
        """The promoted title's OWN audience-segment (DDA) item IDs — excluded on every
        adult set alongside the series self-exclusion, so a promo never chases the audience
        of the very title it's promoting. Resolved from the exclude show (defaults to the
        promoted title) via the segment resolver; only segments with a FreeWheel id are
        usable. Kids brands do no audience targeting, so callers skip this for kids."""
        target = plan.exclude_show or plan.promoted_title
        if not target:
            return []
        # EXACT title only (not the franchise family) — self-exclusion must not knock out
        # every related segment (e.g. exclude "NCIS", not "NCIS: Hawaii/Sydney/...").
        m = self.engine.resolver.resolve_exact(target, region=plan.region)
        if not m.matched:
            return []
        ids = [s.get("segment_id") for s in m.to_dict()["segments"] if s.get("segment_id")]
        return list(dict.fromkeys(ids))

    def _is_pplus(self, plan: SupportPlan) -> bool:
        """Whether this is a Paramount+ brand (drives Recommended Show eligibility)."""
        from .brand_sync import brand_signature
        sig = brand_signature((plan.campaign or {}).get("name", "") or "")
        return bool(sig and sig[0] == "paramount_plus") or str(plan.brand or "").startswith("paramount_plus")

    def _is_pause_format(self, fmt: str) -> bool:
        tmpl = self._templates.get("formats", {}).get(fmt, {})
        return tmpl.get("format_code") == "PAUSE"

    def _standard_segment(self, plan: SupportPlan, brand_cfg: dict) -> str:
        """Which Standard priority table applies (config/standard.yaml segments)."""
        if brand_cfg.get("kids"):
            return "kids"
        domestic = bool(self._regions.get("regions", {})
                        .get(plan.region, {}).get("domestic"))
        if domestic:
            return "adults_domestic"
        return "intl_pluto" if brand_cfg.get("pluto_brand") else "intl_paramount"

    def _standard_entry(self, segment: str, is_pause: bool, duration) -> tuple:
        """(priority, cap) for a Standard placement from config/standard.yaml."""
        from .config import standard_config
        cfg = standard_config().get("segments", {}).get(segment, {})
        if is_pause:
            p = cfg.get("pause", {})
            return p.get("priority"), p.get("cap")
        for row in cfg.get("video", []):
            if duration in (row.get("durations") or []):
                return row.get("priority"), row.get("cap")
        d = cfg.get("video_default", {})
        return d.get("priority"), d.get("cap")

    def _standard_placements(self, plan, fmt, tmpl, brand_cfg, base, durations,
                             name_token, tier_infix, pplus_id_token) -> list:
        """Non-tiered Standard build: one platform-wide placement per duration (video) or
        one pause placement — main SGs + self-exclusions only (no tier includes), at the
        Standard priority/cap. base() carries geo, ad units, main SGs and self-exclusions."""
        segment = self._standard_segment(plan, brand_cfg)
        is_pause = self._is_pause_format(fmt)
        out: list = []
        for dur in durations:
            pri, cap = self._standard_entry(segment, is_pause, dur)
            name = self._tier_name(plan.promoted_title, plan.season_or_messaging, dur,
                                   None, plan.region, token=name_token,
                                   infix=tier_infix) + pplus_id_token
            names, ids = self._ad_units_for_duration(brand_cfg, fmt, tmpl, dur)
            p = base(
                name,
                TieredTargeting(format=fmt),      # no tiers -> platform (main-SG) set only
                duration=dur,
                season_or_messaging=plan.season_or_messaging,
                targeting_ids={},                  # no tier includes (broad platform reach)
                priority_level=pri,
                frequency_cap=cap,
                creative_durations_priority=list(tmpl.get("creative_durations_priority", [])),
            )
            p.ad_unit_names, p.ad_unit_ids = names, ids
            out.append(p)
        return out

    def _scene_lift_tiers(self, plan: SupportPlan) -> Optional[set]:
        """Allowed tier ids for a Scene Lift (None = normal, build all tiers)."""
        if not plan.scene_lift:
            return None
        from .config import scene_lifts_config
        by_type = scene_lifts_config().get("tiers_by_type", {})
        return set(by_type.get(str(plan.scene_lift).lower(), []))

    def _scene_lift_target(self, plan: SupportPlan) -> Optional[dict]:
        """The existing Scene Lift IO to append into, by the selected Pluto campaign."""
        if not plan.scene_lift:
            return None
        from .config import scene_lifts_config
        campaign = (plan.campaign or {}).get("name", "")
        return scene_lifts_config().get("target_ios", {}).get(campaign)

    def _extra_audience_exclusions(self, plan: SupportPlan) -> list[str]:
        """Planner-specified audience segments (picked by name) to exclude on every
        placement's audience_targeting — resolved to DDA audience-item IDs. On top of the
        promoted-title self-exclusion; adult only (kids do no audience targeting)."""
        ids: list[str] = []
        for name in plan.exclude_audience_segments:
            ids += self.engine.resolver.id_for_segment_name(name)
        return list(dict.fromkeys(ids))

    def _extra_exclusions(self, plan: SupportPlan) -> tuple[list, list]:
        """Planner-specified extra excludes: Video Series + Pluto channels (by name) to
        keep off EVERY placement, on top of the promoted-title self-exclusion. Series
        use keyword select-all (exclude every matching series); channels resolve within
        the region's Pluto channel section. Unlike self-exclusion, these apply on any
        brand (a P+ promo can still exclude a Pluto channel it would otherwise run in)."""
        series: list = []
        for name in plan.exclude_series:
            # Exact match (like the promoted-title self-exclusion): the planner picks a
            # specific series from the list, so exclude that series, not every substring.
            series += [s["id"] for s in self.engine.series_resolver.resolve_exact(name).series]
        channel_sgs: list = []
        naming = (self._pluto_cfg().get("naming") or {}).get("channel")
        if plan.exclude_channels and naming:
            code = self._regions.get("regions", {}).get(plan.region, {}).get("code", plan.region)
            prefix, _, suffix = naming.format(region_code=code, name="\x00").partition("\x00")
            for name in plan.exclude_channels:
                m = self.engine.site_group_resolver.select_all(name, prefix=prefix, suffix=suffix)
                if m.matched:
                    channel_sgs += [sg["id"] for sg in m.site_groups]
        return list(dict.fromkeys(series)), list(dict.fromkeys(channel_sgs))

    @staticmethod
    def _pluto_cfg() -> dict:
        from .config import pluto_config
        return pluto_config()

    def _resolve_brand(self, plan: SupportPlan) -> Optional[str]:
        # Explicit brand wins; otherwise derive it from the campaign (1:1 per region).
        if plan.brand:
            return plan.brand
        from .config import brand_for_campaign
        return brand_for_campaign(plan.campaign)

    @staticmethod
    def _order_frequency_caps(region: str, is_kids: bool) -> list[str]:
        """Order-level frequency caps for this IO, from config/frequency_caps.yaml.
        Kids -> the kids rule; adult -> the region override (USA adds 20/month) else the
        adult default. Returns human strings ("1 per 30 min"); the FW client encodes them."""
        from .config import frequency_caps_config
        cfg = frequency_caps_config().get("order_level", {})
        group = cfg.get("kids" if is_kids else "adult", {})
        by_region = (group.get("by_region") or {}).get(region)
        return list(by_region if by_region is not None else group.get("default", []))

    def _brand_cfg(self, brand: Optional[str]) -> dict:
        # `brand` selects the per-brand nuance block (ad units, extra excludes). The
        # exact Advertiser + Campaign in the plan remain authoritative. {} when absent.
        return self._brands.get("brands", {}).get(brand or "", {})

    # --- naming ---------------------------------------------------------- #

    @staticmethod
    def _tier_name(title, season, duration, tier, region, token=None, infix=None) -> str:
        # {title} - {season} - {duration|token} (Tier N)[ (infix)] - {region}.
        # The tier ALWAYS rides in parentheses with the duration/token slot (e.g.
        # "30 (Tier 1)"), matching the live IOs. `infix` appends a line marker like
        # "(Pluto)" -> "15 (Tier 2) (Pluto)". Blanks are skipped.
        slot = str(duration) if duration else (token or "")
        tier_part = f"(Tier {tier})" if tier else ""
        slot = " ".join(x for x in (slot, tier_part, infix) if x)
        parts = [title, season, slot, region]
        return " - ".join(p for p in parts if p)

    def _guaranteed_name(self, plan: SupportPlan, tmpl: dict) -> str:
        # Simple style (CBS sponsorship lines): "{title} - {label} - {region}".
        if tmpl.get("name_style") == "simple":
            parts = [plan.promoted_title, tmpl.get("guaranteed_label", ""), plan.region]
            return " - ".join(p for p in parts if p)
        # P+ Plan style (mirrors Dutton):
        #   "Paramount + - {unit_label} - {plan_label} - {title} - {region} - [ShowID:{id}]"
        label = "MovieID" if (plan.content_type or "show").lower() == "movie" else "ShowID"
        unit = tmpl.get("unit_label", "")
        plan_label = tmpl.get("plan_label", "")
        audience = tmpl.get("audience_label", "")   # e.g. "Kids" -> "… - Kids - {region}"
        parts = ["Paramount +", unit, plan_label, plan.promoted_title, audience, plan.region]
        return " - ".join(p for p in parts if p) + f" - [{label}:{plan.content_id or ''}]"

    def _pplus_id_token(self, plan: SupportPlan, brand_key: Optional[str]) -> str:
        """The [ShowID:]/[MovieID:] token that rides on EVERY placement name for a
        Paramount+ campaign (not just the guaranteed Plan lines). Mirrors the guaranteed
        style: a blank id still stamps "[ShowID:]" so the CM fills it in the UI. Returns
        "" for non-Paramount+ campaigns, so nothing changes for other brands.
        """
        from .brand_sync import brand_signature
        sig = brand_signature((plan.campaign or {}).get("name", "") or "")
        is_pplus = ((sig and sig[0] == "paramount_plus")
                    or str(brand_key or "").startswith("paramount_plus"))
        if not is_pplus:
            return ""
        label = "MovieID" if (plan.content_type or "show").lower() == "movie" else "ShowID"
        return f" - [{label}:{plan.content_id or ''}]"

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
        brand_key = self._resolve_brand(plan)
        brand_cfg = self._brand_cfg(brand_key)
        # Paramount+ campaigns stamp the [ShowID:]/[MovieID:] token on EVERY placement
        # name (guaranteed lines already carry it; this adds it to remnant/flat lines too).
        pplus_id_token = self._pplus_id_token(plan, brand_key)
        # Brand-level per-format overrides (e.g. UK bumper "Basic Plan", region-specific
        # main SGs) let regions reuse a format without a new template.
        overrides = (brand_cfg.get("format_overrides", {}) or {}).get(fmt, {})
        tmpl = {**fmt_templates[fmt], **overrides}
        exclude = plan.exclude_show or plan.promoted_title
        recommended = plan.recommended_show or plan.promoted_title
        extra = {k: tmpl[k] for k in ("spec", "standard_sizes", "salesforce_asset_field") if k in tmpl}
        geo_names = self._geo_country_names(plan.region)
        geo_ids = self._geo_country_ids(geo_names)
        # Region-grouping geo (e.g. LATAM -> FW geography region 1069) overrides the
        # per-country geo when the region config names one.
        region_cfg = self._regions.get("regions", {}).get(plan.region, {})
        geo_region_ids = ([str(region_cfg["geo_region"])]
                          if region_cfg.get("geo_region") else [])
        ad_unit_names = self._ad_unit_names(brand_cfg, fmt)
        ad_unit_ids = self._ad_unit_ids(brand_cfg, fmt)
        excl_sgs = list(brand_cfg.get("extra_exclude_site_groups", []))
        excl_vgs = list(brand_cfg.get("extra_exclude_video_groups", []))
        # Format-level always-excludes applied to EVERY set of the placement, e.g. the
        # guaranteed Plan rules: Bumper excludes SG Stream Type: Live; Pre-Roll excludes
        # VG Format: Clips (kids + adults, all regions).
        excl_sgs += list(tmpl.get("extra_exclude_site_groups", []))
        excl_vgs += list(tmpl.get("extra_exclude_video_groups", []))
        # Rating restrictions (Network 10 AU): VG values supplied per-campaign, excluded
        # on every set of the opted-in format. Passed through as VG IDs (Network 10
        # supplies the values); resolved names would be layered here if ever needed.
        if tmpl.get("applies_rating_restrictions") and plan.rating_restrictions:
            excl_vgs += [vg for vg in plan.rating_restrictions if vg not in excl_vgs]
        # US Pluto FREQUENT DNR: excluded on every US brand EXCEPT Pluto TV - USA.
        from .config import relationship_targeting_config
        dnr = relationship_targeting_config().get("us_pluto_dnr", {})
        if (plan.region == "USA" and dnr.get("site_group")
                and self._resolve_brand(plan) not in dnr.get("except_brands", [])):
            if dnr["site_group"] not in excl_sgs:
                excl_sgs.append(dnr["site_group"])
        main_sgs = list(brand_cfg.get("main_site_groups", []))
        # Per-format main-SG override (the UK P+/Pluto split: P+ line vs Pluto line).
        if tmpl.get("main_site_groups"):
            main_sgs = list(tmpl["main_site_groups"])
        include_vgs = list(brand_cfg.get("include_video_groups", []))
        pause_main = list(brand_cfg.get("pause_main_site_groups", []))
        # Pluto TV brands exclude Samsung TV Plus SGs on EVERY placement (placement-level
        # content exclude), region-scoped: US SGs domestically, the intl SGs abroad.
        content_excl_sgs: list[str] = []
        if brand_cfg.get("pluto_brand"):
            samsung = relationship_targeting_config().get("samsung_tv_plus", {})
            samsung_sgs = list(samsung.get("domestic" if plan.region == "USA"
                                           else "international", []))
            # Placements WITH relationship sets: Samsung goes in the set excludes (the
            # API drops a placement-level content_targeting when sets are present).
            excl_sgs += [sg for sg in samsung_sgs if sg not in excl_sgs]
            # Set-less flat lines carry it at the placement-level content exclude.
            content_excl_sgs = samsung_sgs
        # Self-exclusion: the promoted show's own Video Series (excluded on every set)
        # + its Channel SGs (added to the site-group excludes). Plus any planner-specified
        # extra series/channel excludes, applied to EVERY placement the same way.
        self_series, self_channel_sgs = self._self_exclusions(
            plan, pluto_brand=bool(brand_cfg.get("pluto_brand")))
        extra_series, extra_channel_sgs = self._extra_exclusions(plan)
        self_series = list(self_series) + [s for s in extra_series if s not in self_series]
        excl_sgs += [sg for sg in self_channel_sgs + extra_channel_sgs if sg not in excl_sgs]

        # Kids: layer the Older/Younger VGs + Kids content SG. Main SGs are per-format
        # (remnant P+/Pluto = [Pluto, P+]; guaranteed = [P+]).
        is_kids = bool(brand_cfg.get("kids") and tmpl.get("kids"))
        kids_vgs = kids_video_groups(plan.kids_audience) if is_kids else []
        kids_sg = kids_targeting_config().get("content_site_group") if is_kids else None
        # ADULT self-exclusion: also exclude the promoted title's own audience segment on
        # every set (combined with the series self-exclusion). Kids do no audience targeting.
        self_audience = ([] if is_kids
                         else self._self_audience_exclusions(plan) + self._extra_audience_exclusions(plan))
        # Brazil/LATAM Paramount Promo Blocks (SG 1258011): this SG is BR/LATAM inventory,
        # so it is excluded ONLY on adult Pluto placements in the BR + LATAM regions
        # (Pluto SG in its main SGs), across all tiers + standard lines. Skips every other
        # region (a US IO's only baseline Pluto exclude is FREQUENT DNR), kids brands,
        # guaranteed P+ lines (not on Pluto), and the Pluto TV - BR / Pluto TV - LATAM
        # campaigns (which ARE those blocks).
        pblk = relationship_targeting_config().get("latam_br_promo_blocks", {})
        # Effective main = the per-format/brand main, else the shared default (which
        # domestic brands like P+ Domestic / CBS / Pluto ES rely on) — same fallback
        # _relationship_sets uses, so "runs on Pluto" is judged on what actually serves.
        default_main = relationship_targeting_config().get("domestic_usa", {}).get(
            "main_site_groups", [])
        effective_main = main_sgs or default_main
        if (pblk.get("site_group") and not is_kids and not tmpl.get("guaranteed")
                and plan.region in pblk.get("regions", [])
                and pblk.get("pluto_site_group") in effective_main
                and self._resolve_brand(plan) not in pblk.get("except_brands", [])):
            if pblk["site_group"] not in excl_sgs:
                excl_sgs.append(pblk["site_group"])
        if is_kids and tmpl.get("kids_main_site_groups"):
            main_sgs = list(tmpl["kids_main_site_groups"])

        def base(name, targeting, **kw) -> Placement:
            return Placement(
                name=name, format=fmt, format_code=tmpl["format_code"], region=plan.region,
                targeting=targeting, endpoints=list(tmpl.get("endpoints", [])),
                platforms=list(tmpl.get("platforms", [])), exclusions=[exclude],
                geo_country_names=geo_names, geo_country_ids=geo_ids,
                geo_region_ids=list(geo_region_ids),
                ad_unit_names=ad_unit_names, ad_unit_ids=ad_unit_ids,
                extra_exclude_site_groups=excl_sgs, extra_exclude_video_groups=excl_vgs,
                main_site_groups=main_sgs, include_video_groups=include_vgs,
                pause_main_site_groups=pause_main,
                kids_video_groups=list(kids_vgs), kids_content_site_group=kids_sg,
                content_exclude_site_groups=list(content_excl_sgs),
                exclude_series=list(self_series),
                exclude_videos=list(plan.exclude_videos),
                exclude_audience_items=list(self_audience),
                region_has_pluto=bool(self._regions.get("regions", {})
                                      .get(plan.region, {}).get("has_pluto", True)),
                region_is_domestic=bool(self._regions.get("regions", {})
                                        .get(plan.region, {}).get("domestic", False)),
                is_pluto_brand=bool(brand_cfg.get("pluto_brand")),
                is_pplus_brand=self._is_pplus(plan),
                # Movies can't carry a Recommended Show argument (Show-ID-only feature);
                # their id rides only in the placement name ([MovieID:…]).
                recommended_show_enabled=(plan.content_type or "show").lower() != "movie",
                nests_in=tmpl.get("nests_in", "new_insertion_order"), extra=extra, **kw)

        # Guaranteed formats.
        if tmpl.get("guaranteed"):
            precedence = tmpl.get("precedence_level", "HIGH")
            # Kids guaranteed (Pre-Roll/Bumper): Kids targeting instead of the adult
            # genre + recommended-show arguments.
            if tmpl.get("kids"):
                fc = tmpl.get("frequency_cap") or self._freq_cap(None, fmt)
                return [base(
                    self._guaranteed_name(plan, tmpl), TieredTargeting(format=fmt),
                    guaranteed=True, precedence_level=precedence,
                    priority_level=self._guaranteed_priority(), frequency_cap=fc,
                )]
            # Simple sponsorship lines (CBS Pre-Roll / Bumper / Lockdown): ad unit +
            # geo only, no targeting sets, HIGHEST precedence. Only capped if the
            # template names a cap (Bumper/Lockdown have none).
            if tmpl.get("no_targeting"):
                return [base(
                    self._guaranteed_name(plan, tmpl),
                    TieredTargeting(format=fmt),
                    guaranteed=True, no_targeting=True, precedence_level=precedence,
                    priority_level=self._guaranteed_priority(),
                    frequency_cap=tmpl.get("frequency_cap"),
                )]
            fc = tmpl.get("frequency_cap") or self._freq_cap(None, fmt)
            # P+ Plan lines: one Genre argument (genre VGs) + one Recommended Show.
            g_ids: dict[str, list] = {}
            g_vgs = self.genre_resolver.ids_for(list(plan.genres))
            if g_vgs:
                g_ids["genre_vgs"] = g_vgs
            return [base(
                self._guaranteed_name(plan, tmpl),
                TieredTargeting(format=fmt),
                guaranteed=True, precedence_level=precedence,
                arguments={"genre": list(plan.genres), "recommended_show": recommended},
                targeting_ids=g_ids,
                recommended_show_value=plan.recommended_show_id or plan.content_id,
                priority_level=self._guaranteed_priority(), frequency_cap=fc,
            )]

        # Flat lines: one placement per duration, named
        # "{title} - {label} - {duration} - {suffix}". Used for the simple untargeted
        # remnant brands (e.g. Pluto En Español): no tier stack, ad units + geo only.
        # `label` defaults to the plan messaging (else the template's line_label); the
        # naming `suffix` is the brand's placement_name_suffix (else the region). Short
        # durations get the House Pre-Roll; it drops at `drop_preroll_at_duration`.
        if tmpl.get("flat_line"):
            ptier = tmpl.get("priority_tier", 4)
            label = plan.season_or_messaging or tmpl.get("line_label", "")
            # Naming suffix: an audience label ("Kids") becomes "{audience} - {region}";
            # else the brand's placement_name_suffix; else the region. A duration_infix
            # (e.g. "(P+/Pluto)") rides with the duration: "15 (P+/Pluto)".
            audience = tmpl.get("audience_label")
            region_suffix = brand_cfg.get("placement_name_suffix") or plan.region
            suffix = f"{audience} - {plan.region}" if audience else region_suffix
            infix = tmpl.get("duration_infix")
            # Kids O&O lines put the audience BEFORE the duration slot (mirrors the AU
            # Nick IOs: "{title} - {msg} - Kids - 15 (10 Streaming) - AU").
            audience_first = bool(audience and tmpl.get("audience_before_slot"))
            # Fixed priority / frequency cap override the tier-derived defaults — kids
            # remnant lines run at priority 1 (override -1) with the kids cap, not tier 4.
            fixed_priority = tmpl.get("priority")
            fixed_fc = tmpl.get("frequency_cap")
            # Brand-constant relationship sets (e.g. Pluto En Español). When present they
            # ARE the targeting; otherwise the line is untargeted per the template.
            static_sets = list(brand_cfg.get("relationship_sets") or [])
            no_targeting = bool(tmpl.get("no_targeting")) and not static_sets
            # Optional brand name prefix (e.g. "Paramount Consumer Products - {title} …").
            name_prefix = brand_cfg.get("placement_name_prefix")
            out: list[Placement] = []
            for dur in self._durations(plan):
                slot = f"{dur} {infix}" if infix else str(dur)
                parts = ([plan.promoted_title, label, audience, slot, region_suffix]
                         if audience_first
                         else [plan.promoted_title, label, slot, suffix])
                if name_prefix:
                    parts = [name_prefix] + parts
                names, ids = self._ad_units_for_duration(brand_cfg, fmt, tmpl, dur)
                placement = base(
                    " - ".join(p for p in parts if p) + pplus_id_token,
                    TieredTargeting(format=fmt),
                    tier=ptier, duration=dur, no_targeting=no_targeting,
                    static_relationship_sets=static_sets,
                    priority_level=(fixed_priority if fixed_priority is not None
                                    else self._priority(ptier, dur)),
                    frequency_cap=fixed_fc or self._freq_cap(ptier, fmt),
                )
                placement.ad_unit_names, placement.ad_unit_ids = names, ids
                out.append(placement)
            return out

        targeting = self.engine.build(plan, fmt)
        uses_durations = bool(tmpl.get("uses_durations"))
        durations = self._durations(plan) if uses_durations else [None]
        name_token = tmpl.get("name_token")   # e.g. "Pause Ad" for non-duration formats
        tier_infix = tmpl.get("tier_infix")   # e.g. "(Pluto)" for the UK Pluto split line
        # Per-format targeting routing (the UK P+/Pluto split): P+ lines keep the showlist
        # (series), Pluto lines keep channels/categories. Empty => keep everything.
        kinds = tmpl.get("targeting_kinds")

        # Standard (non-tiered): ONE platform-wide placement per duration (video) or one
        # pause placement — main SGs + self-exclusions only, at the Standard priority/cap.
        if plan.standard:
            return self._standard_placements(
                plan, fmt, tmpl, brand_cfg, base, durations, name_token,
                tier_infix, pplus_id_token)

        placements: list[Placement] = []
        # Scene Lift: build only the allowed tiers (AI -> [3]; standard -> [1,2,3]).
        allowed_tiers = self._scene_lift_tiers(plan)
        for tier in targeting.tiers:
            if allowed_tiers is not None and tier.id not in allowed_tiers:
                continue
            tids = self._targeting_ids(plan, tier)
            if kinds is not None:
                tids = {k: v for k, v in tids.items() if k in kinds}
            for dur in durations:
                # CA (and other non-tiered markets) suppress the "(Tier N)" label.
                label_tier = None if tmpl.get("no_tier_label") else tier.id
                name = self._tier_name(plan.promoted_title, plan.season_or_messaging,
                                       dur, label_tier, plan.region, token=name_token,
                                       infix=tier_infix) + pplus_id_token
                names, ids = self._ad_units_for_duration(brand_cfg, fmt, tmpl, dur)
                placement = base(
                    name,
                    TieredTargeting(format=fmt, tiers=[tier]),   # one tier per placement
                    tier=tier.id,
                    duration=dur,
                    season_or_messaging=plan.season_or_messaging,
                    targeting_ids=tids,
                    # Recommended Show rides on Tier 1 (mirrors Dutton).
                    recommended_show_value=(plan.recommended_show_id or plan.content_id)
                                           if tier.id == 1 else None,
                    priority_level=self._priority(tier.id, dur),
                    frequency_cap=self._freq_cap(tier.id, fmt),
                    creative_durations_priority=list(tmpl.get("creative_durations_priority", [])),
                )
                placement.ad_unit_names, placement.ad_unit_ids = names, ids
                placements.append(placement)
        return placements

    def build(self, plan: SupportPlan) -> Order:
        brand_cfg = self._brand_cfg(plan.brand)
        io_name = plan.insertion_order_name or f"{plan.promoted_title} - {plan.region}"
        # Scene Lift: placements are added into the existing "Scene Lifts - {Region}" IO
        # (no new IO). Use that IO's name for reference; routing id set below.
        sl_target = self._scene_lift_target(plan)
        if sl_target:
            io_name = sl_target.get("io_name", io_name)

        order = Order(
            name=io_name,
            promoted_title=plan.promoted_title,
            brand=plan.brand,
            region=plan.region,
            network_id=str(self._brands.get("network_id")) if self._brands.get("network_id") else None,
            advertiser=dict(plan.advertiser),
            campaign=dict(plan.campaign),
            flight=plan.flight,
            primary_trafficker=plan.primary_trafficker,
            scene_lift=plan.scene_lift,
            scene_lift_io_id=(sl_target or {}).get("io_id"),
            existing_io_id=plan.existing_io_id,
            template_ref={
                # Exact advertiser/campaign come from the plan; brand_cfg is fallback.
                "advertiser_id": plan.advertiser.get("resolved_id"),
                "campaign_id": plan.campaign.get("resolved_id"),
                "template_io_id": plan.template_io_id or brand_cfg.get("template_io_id"),
                "brand_id": plan.brand_id,
            },
        )
        # Order-level frequency caps (general rule): kids IOs 1/15min; adult IOs 1/30min,
        # plus 20/month for USA. Resolved from the campaign's brand (kids vs adult) + region.
        cap_cfg = self._brand_cfg(self._resolve_brand(plan)) or brand_cfg
        order.frequency_caps = self._order_frequency_caps(plan.region, bool(cap_cfg.get("kids")))
        # Record the promoted title's own resolved Video Series (the self-exclusion). Empty
        # => the title didn't match a FreeWheel series; the CM must exclude it manually.
        order.promoted_series_ids = list(self._self_exclusions(plan)[0])
        # Adult orders also record the promoted title's audience segments (excluded on every
        # set). Kids do no audience targeting, so leave empty for kids brands.
        order.promoted_audience_items = ([] if cap_cfg.get("kids")
                                         else self._self_audience_exclusions(plan))
        # Kids brands only build when a Kids audience (Older/Younger) is selected in the
        # Salesforce targeting; no audience -> no Kids IOs.
        if brand_cfg.get("kids") and not plan.kids_audience:
            return order

        for fmt in plan.formats:
            # Scene Lifts are VIDEO ONLY — skip pause (and any non-video) formats.
            if plan.scene_lift and self._is_pause_format(fmt):
                continue
            order.placements.extend(self._placements_for_format(plan, fmt))
        return order
