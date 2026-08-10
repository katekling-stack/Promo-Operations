"""Domain models for promo operations.

These dataclasses are the vocabulary shared by every part of the system:
a SupportPlan comes in, the targeting engine turns it into TieredTargeting,
and the order builder assembles an Order with one Placement per format x region.
Everything is plain data so it serializes cleanly to JSON for dry-run review and
for hand-off to the integration clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Input: the support plan
# --------------------------------------------------------------------------- #

# Toggleable products for the plan template's "Products" section. Each friendly family
# key maps to the placement format(s) it controls. A planner toggle of True INCLUDES
# the product, False EXCLUDES it, and blank/absent leaves the brand's default set. Not
# every campaign runs every product, so this is mostly used to drop one a campaign
# doesn't have. "after_midroll_bumper" spans the three brand-specific bumper formats;
# only the one in the brand's set is ever added.
PRODUCT_FAMILIES: dict[str, list[str]] = {
    "remnant_video": ["remnant_video"],
    "pause_ads": ["pause_ads"],
    "premium_preroll": ["premium_preroll"],
    "essential_bumper": ["essential_bumper"],
    "cbs_preroll": ["cbs_preroll"],
    "after_midroll_bumper": ["cbs_after_midroll_bumper", "mtve_after_midroll_bumper",
                             "bet_after_midroll_bumper"],
    "cbs_1z_lockdown": ["cbs_1z_lockdown"],
    "cbs_2z_lockdown": ["cbs_2z_lockdown"],
    # UK P+ only: the optional Pluto breakout remnant lines. Off by default; the
    # "Include Pluto" checkbox opts them in (Pluto is auto-combined in other regions).
    "pluto_breakout": ["pplus_uk_remnant_pluto"],
    # AU only: optional Network 10 (10 Streaming) lines. The opt-in adds whichever
    # members the selected brand supports — P+ AU gets the tiered remnant; Nick AU gets
    # the Kids 10 Streaming remnant + After Mid-Roll Bumper.
    "network_10": ["network_10_remnant", "nick_au_network_10_remnant",
                   "nick_au_network_10_bumper"],
}


@dataclass
class Flight:
    start: Optional[str] = None
    end: Optional[str] = None
    code: Optional[str] = None


@dataclass
class SupportPlan:
    """The campaign inputs — from a YAML file, a planning sheet, or a SF Case."""

    promoted_title: str
    region: str
    # Language (from Salesforce) for multi-language regions like Canada — routes the
    # campaign to the matching French vs English advertiser/campaign. The campaign name
    # already encodes it; this documents/validates the routing.
    language: Optional[str] = None
    formats: list[str] = field(default_factory=list)
    # Optional legacy grouping; the exact Advertiser + Campaign are the real inputs.
    brand: Optional[str] = None
    networks: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    showlist: list[str] = field(default_factory=list)
    # Manually-specified Tier 1 audience segments (names or IDs). Added to Tier 1
    # in addition to any segments auto-resolved from the showlist.
    audience_segments: list[str] = field(default_factory=list)
    # FreeWheel "Recommended Show" Key Value. Feeds Tier 1 carousel targeting and the
    # Premium Pre-Roll / Essential recommended-show argument. Defaults to promoted_title.
    recommended_show: Optional[str] = None
    # Label to exclude from EVERY placement (label-based exclusion). Defaults to
    # promoted_title — the show being promoted is excluded everywhere.
    exclude_show: Optional[str] = None
    # Extra Video Series / Pluto channels (BY NAME) to exclude from EVERY placement, on
    # top of the automatic self-exclusion of the promoted title. Planner searches +
    # picks these in the form; resolved to FreeWheel IDs at build time (keyword
    # select-all, so "NCIS" excludes every NCIS series so the promo never runs in it).
    exclude_series: list[str] = field(default_factory=list)
    exclude_channels: list[str] = field(default_factory=list)
    # Individual FreeWheel Video (asset) IDs to exclude on every placement — for MOVIES,
    # which are single video assets rather than series. Applied as content exclude `video`.
    exclude_videos: list[str] = field(default_factory=list)
    # Existing audience segments (by name, from the picklist) to exclude on every
    # placement's audience_targeting — resolved to DDA audience-item IDs by the builder.
    exclude_audience_segments: list[str] = field(default_factory=list)
    # Placement naming: "{title} - {season_or_messaging} - {duration} - Tier N - {region}".
    season_or_messaging: Optional[str] = None
    # Primary Trafficker — the submitting CM's name; carried onto the IO.
    primary_trafficker: Optional[str] = None
    # Scene Lift type (Pluto UK/CA/USA only): "ai" -> Tier 3 only; "standard" (60s) ->
    # Tiers 1-3. Placements are ADDED into the existing "Scene Lifts - {Region}" IO under
    # the associated Pluto campaign (see config/scene_lifts.yaml). Blank = normal promo.
    scene_lift: Optional[str] = None
    # Standard (NON-TIERED): build one platform-wide placement per duration (+ pause)
    # using config/standard.yaml priorities/caps instead of the tier stack. Still excludes
    # the promoted title + audience. Applies to video AND pause. Blank/False = tiered.
    standard: bool = False
    # Add to an EXISTING Insertion Order: when set, placements are created INTO this IO
    # (by FreeWheel IO id) instead of a new one — e.g. adding Season 2 lines to the
    # Season 1 IO that already exists. Blank = create a new IO as usual.
    existing_io_id: Optional[str] = None
    # Creative durations (seconds) that each video tier is split into (one placement
    # per tier x duration). Defaults applied if empty.
    durations: list[int] = field(default_factory=list)
    # Guaranteed Premium/Essential placement id token. content_type selects the label:
    # "show" -> "{title} [ShowID:{content_id}]", "movie" -> "{title} [MovieID:{content_id}]".
    content_type: str = "show"          # "show" | "movie"
    content_id: Optional[str] = None    # ShowID / MovieID (left blank -> "[ShowID:]")
    # Video Domination selector (config/video_dominations.yaml option key: pluto |
    # standard | aus_10_streaming | uk_my5). `video_domination_targeting` holds the
    # Pluto category names for a Pluto VD.
    video_domination: Optional[str] = None
    video_domination_targeting: list[str] = field(default_factory=list)
    # Operative takeover selector (config/operative_takeovers.yaml type key:
    # hpto | first_impression | arena_takeover | three_peat).
    takeover: Optional[str] = None
    # Per-campaign product toggles (Products section of the template). Keys are
    # PRODUCT_FAMILIES keys; True includes / False excludes / absent = brand default.
    product_overrides: dict[str, bool] = field(default_factory=dict)
    # Kids audience (from the Salesforce targeting): which age group(s) to build Kids
    # placements for — values "older" / "younger". Empty => NO Kids IOs are built for a
    # Kids brand. Selects the Kids Video Groups layered into Kids targeting.
    kids_audience: list[str] = field(default_factory=list)
    # Rating restrictions (VG values). Network 10 (AU) sometimes supplies rating-based
    # Video Groups that must be excluded from its (10 Streaming) lines. Empty => none.
    # Only applied to formats flagged `applies_rating_restrictions` in the template.
    rating_restrictions: list[str] = field(default_factory=list)
    # Recommended Show custom key-value ("recommended_show=<id>") on Tier 1 + the
    # guaranteed Plan placements. Falls back to content_id; blank -> CM adds in the UI.
    recommended_show_id: Optional[str] = None
    pluto_categories: list[str] = field(default_factory=list)
    pluto_channels: list[str] = field(default_factory=list)
    pplus_user_states: list[str] = field(default_factory=list)
    demographics: Optional[dict[str, Any]] = None
    flight: Flight = field(default_factory=Flight)
    # FreeWheel nesting: IO (this campaign flight) under an existing Campaign under
    # an Advertiser. advertiser={name, name_contains, resolved_id};
    # campaign={name, resolved_id}. insertion_order_name defaults to
    # "{promoted_title} - {region}".
    advertiser: dict[str, Any] = field(default_factory=dict)
    campaign: dict[str, Any] = field(default_factory=dict)
    insertion_order_name: Optional[str] = None
    brand_id: Optional[str] = None       # FreeWheel brand_id (from the reference IO)
    template_io_id: Optional[str] = None # existing IO to model this one after
    salesforce_case: Optional[str] = None

    def source_value(self, source: str) -> Any:
        """Resolve a tier dimension's `source` key to the plan's input value.

        The tier config references plan inputs by name (e.g. `source: showlist`);
        this maps those names onto plan attributes so the engine stays declarative.
        """
        mapping = {
            "showlist": self.showlist,
            "genres": self.genres,
            "networks": self.networks,
            "pluto_channels": self.pluto_channels,
            "pluto_categories": self.pluto_categories,
            "promoted_title": self.promoted_title,
            "region": self.region,
            "pplus_user_states": self.pplus_user_states,
            "demographics": self.demographics,
            "recommended_show": self.recommended_show or self.promoted_title,
        }
        return mapping.get(source)


# --------------------------------------------------------------------------- #
# Output: targeting
# --------------------------------------------------------------------------- #

@dataclass
class TargetingDimension:
    """One targeting clause within a tier (e.g. the resolved showlist segments)."""

    key: str
    label: str
    source: str
    values: list[Any] = field(default_factory=list)
    # For audience_segments: the resolved FW segment records (name/id + match info).
    resolved: list[dict[str, Any]] = field(default_factory=list)
    notes: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.values and not self.resolved


@dataclass
class Tier:
    id: int
    name: str
    dimensions: list[TargetingDimension] = field(default_factory=list)


@dataclass
class TieredTargeting:
    """The full tier stack applied to one format."""

    format: str
    tiers: list[Tier] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Output: order + placements
# --------------------------------------------------------------------------- #

@dataclass
class Placement:
    name: str
    format: str
    format_code: str
    region: str
    targeting: TieredTargeting
    tier: Optional[int] = None          # this placement's single tier (per-tier model)
    duration: Optional[int] = None      # creative duration in seconds (video)
    season_or_messaging: Optional[str] = None
    priority_level: Optional[Any] = None   # ad-server priority (from config, per tier)
    frequency_cap: Optional[str] = None
    endpoints: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    creative_durations_priority: list[int] = field(default_factory=list)
    # Label-based exclusions applied to this placement (always includes the
    # promoted show, so it never promos against itself).
    exclusions: list[str] = field(default_factory=list)
    # Geo targeting. `geo_country_names` are what the team searches/selects in the
    # FreeWheel UI (e.g. "United States"); `geo_country_ids` are the resolved FW
    # country IDs the Placement API writes (e.g. 165). Names come from the region
    # config; IDs resolve via the country table (data/geo).
    geo_country_names: list[str] = field(default_factory=list)
    geo_country_ids: list[str] = field(default_factory=list)
    # Some regions target a FreeWheel geography REGION (a country grouping) instead of
    # individual countries — e.g. LATAM = region 1069. When set, it takes precedence
    # over geo_country_ids in the geography_targeting body.
    geo_region_ids: list[str] = field(default_factory=list)
    # Ad unit names/IDs — names mirror past setups + the priority doc; IDs resolve
    # once the ad-unit table is synced.
    ad_unit_names: list[str] = field(default_factory=list)
    ad_unit_ids: list[str] = field(default_factory=list)
    # Resolved relationship-targeting IDs for this placement (FW namespaces), keyed
    # by kind: dda, series, channels (Pluto channel SGs), categories (Pluto category
    # SGs), genre_vgs (genre Video Groups). Combined with the config "main SGs" in
    # freewheel._relationship_sets to mirror Dutton.
    targeting_ids: dict[str, list] = field(default_factory=dict)
    # Recommended Show custom key-value value (a ShowID). Blank -> CM adds in the UI.
    recommended_show_value: Optional[str] = None
    # Whether the Recommended Show argument may be added at all. FALSE for Movies:
    # recommended_show(s) targeting only supports Show IDs, so a Movie's id rides only
    # in the placement NAME ([MovieID:…]), never in this custom-targeting key-value.
    recommended_show_enabled: bool = True
    # Brand-specific always-exclude IDs, layered onto the shared DNR exclude in every
    # relationship set (e.g. CBS News excludes the Pluto News category site groups).
    extra_exclude_site_groups: list[str] = field(default_factory=list)
    extra_exclude_video_groups: list[str] = field(default_factory=list)
    # Per-brand platform "main SGs" override (e.g. MTVE = PlutoTV/VCBS/CBS Local, no
    # P+). Empty -> the shared default from config. `include_video_groups` are brand
    # content VGs AND-ed into the genre targeting (e.g. the MTV / BET brand VG).
    main_site_groups: list[str] = field(default_factory=list)
    include_video_groups: list[str] = field(default_factory=list)
    # Per-brand Pause Ad main-SG override (independent of remnant main). Empty -> the
    # shared pause config default. Paramount Pictures uses [Pluto, CBS Local, VCBS]
    # (no P+) instead of the standard [Pluto, P+, VCBS].
    pause_main_site_groups: list[str] = field(default_factory=list)
    # Kids targeting: the Older/Younger Video Groups + the Kids content Site Group,
    # grouped together and AND-ed with main_site_groups (mirrors the P+ Kids IOs).
    # Set only for Kids-brand placements; drives the "Kids" relationship set.
    kids_video_groups: list[str] = field(default_factory=list)
    kids_content_site_group: Optional[str] = None
    # Placement-level content_targeting.exclude (applies to the whole placement, not a
    # relationship set) — Pluto TV brands exclude the Samsung TV Plus SGs everywhere.
    content_exclude_site_groups: list[str] = field(default_factory=list)
    # Self-exclusion: the promoted show's OWN Video Series IDs, excluded on every set so
    # it never promos against itself (its Channel SGs go in extra_exclude_site_groups).
    exclude_series: list[str] = field(default_factory=list)
    # Extra individual Video (asset) IDs to exclude on every set — for MOVIES (single
    # video assets, not series). Added to content_targeting exclude as `video`.
    exclude_videos: list[str] = field(default_factory=list)
    # Self-exclusion (ADULT only): the promoted title's OWN audience-segment (DDA) item IDs,
    # excluded on every set's audience_targeting so the promo doesn't chase its own audience.
    # Empty on kids placements (no audience targeting on kids).
    exclude_audience_items: list[str] = field(default_factory=list)
    # Whether the placement's region carries Pluto (regions.yaml has_pluto). Drives the
    # no-Pluto pause-ad main-SG drop (e.g. IE). Default True preserves existing behavior.
    region_has_pluto: bool = True
    # Whether the region is Domestic (US). International regions use the fuller pause
    # custom-targeting key-value exclude list. Default True preserves existing behavior.
    region_is_domestic: bool = True
    # Whether this is a Pluto TV brand placement. Drives the Recommended Show argument:
    # Pluto uses the key "recommended_shows" (plural) and ONLY domestically (the feature
    # isn't rolled out globally); P+/other adult brands use "recommended_show" globally.
    is_pluto_brand: bool = False
    # Brand-constant relationship sets (targeting fixed per brand, not derived from the
    # plan) — e.g. Pluto En Español's "Targeting VOD" / "En Espanol" sets. Each item:
    # {set_name, include: [subset,...], exclude: {site_group:[...]}}. Built verbatim.
    static_relationship_sets: list[dict[str, Any]] = field(default_factory=list)
    # Guaranteed placements (Premium Pre-Roll, Essential Bumper) are built from a
    # small set of explicit arguments rather than the tier stack, and live in an
    # existing guaranteed order rather than the new remnant IO.
    guaranteed: bool = False
    # Guaranteed override precedence ("HIGH" for P+ Plan lines, "HIGHEST" for CBS
    # sponsorship lines). no_targeting => a bare sponsorship line (ad unit + geo only,
    # no relationship sets).
    precedence_level: Optional[str] = None
    no_targeting: bool = False
    arguments: dict[str, Any] = field(default_factory=dict)
    nests_in: str = "new_insertion_order"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    name: str
    promoted_title: str
    brand: str
    region: str
    network_id: Optional[str] = None
    advertiser: dict[str, Any] = field(default_factory=dict)
    campaign: dict[str, Any] = field(default_factory=dict)
    flight: Flight = field(default_factory=Flight)
    placements: list[Placement] = field(default_factory=list)
    template_ref: dict[str, Any] = field(default_factory=dict)
    # Order-level frequency caps as human strings ("1 per 30 min", "20 per month"),
    # resolved from config by kids/adult + region. The FreeWheel client encodes these
    # onto the IO's delivery.frequency_cap.
    frequency_caps: list[str] = field(default_factory=list)
    # The promoted title's own resolved Video Series ids (the self-exclusion). EMPTY when
    # the title didn't match a FreeWheel series — a flag for the CM to exclude it by hand.
    promoted_series_ids: list[str] = field(default_factory=list)
    # The promoted title's own resolved audience-segment (DDA) ids, excluded on adult IOs.
    promoted_audience_items: list[str] = field(default_factory=list)
    # Primary Trafficker — the submitting CM's name; stamped onto the IO's
    # primary_trafficker field so the draft is owned by whoever requested it.
    primary_trafficker: Optional[str] = None
    # Scene Lift routing: when set, placements are ADDED into this existing IO (no new IO
    # is created). `scene_lift` records the type (ai | standard) for reference/naming.
    scene_lift_io_id: Optional[str] = None
    scene_lift: Optional[str] = None
    # Add-to-existing-IO: when set, placements are created INTO this IO id (no new IO) —
    # e.g. adding Season 2 lines to the existing Season 1 IO.
    existing_io_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
