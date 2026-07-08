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
    # Placement naming: "{title} - {season_or_messaging} - {duration} - Tier N - {region}".
    season_or_messaging: Optional[str] = None
    # Creative durations (seconds) that each video tier is split into (one placement
    # per tier x duration). Defaults applied if empty.
    durations: list[int] = field(default_factory=list)
    # Guaranteed Premium/Essential placement id token. content_type selects the label:
    # "show" -> "{title} [ShowID:{content_id}]", "movie" -> "{title} [MovieID:{content_id}]".
    content_type: str = "show"          # "show" | "movie"
    content_id: Optional[str] = None    # ShowID / MovieID (left blank -> "[ShowID:]")
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
    # Ad unit names/IDs — names mirror past setups + the priority doc; IDs resolve
    # once the ad-unit table is synced.
    ad_unit_names: list[str] = field(default_factory=list)
    ad_unit_ids: list[str] = field(default_factory=list)
    # Guaranteed placements (Premium Pre-Roll, Essential Bumper) are built from a
    # small set of explicit arguments rather than the tier stack, and live in an
    # existing guaranteed order rather than the new remnant IO.
    guaranteed: bool = False
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
