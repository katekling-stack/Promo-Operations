"""Mirror an existing order/plan to another country.

Ad Ops often builds the same title across markets: set up "Frisco King - FR", then
want the GSA / IT / ES equivalents with the same creative and targeting, just
re-pointed at each country's brand and re-named. Because the whole system is
config-driven, that's exactly: take the source plan, swap region + campaign to the
target market's equivalent brand, and drop the derived identity so IO name, ad
units, geo and per-tier placements re-derive for the target.

This module is pure (no network). integrations/freewheel duplicates the *live*
placements at push time from the mirrored plan; the CLI (`promo-ops mirror`) and the
plan form's "Duplicate to another market" section both call in here.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from . import brand_sync
from .config import brands_config

# Identity fields that are specific to the source order — dropped so they re-derive
# for the target market instead of leaking the source's country into the copy.
_SOURCE_SPECIFIC = ("brand", "advertiser", "brand_id", "template_io_id",
                    "template_campaign_id", "insertion_order_name")


def equivalent_campaign(source_campaign_name: str, target_region: str,
                        brands_cfg: Optional[dict[str, Any]] = None) -> Optional[str]:
    """The target-region campaign of the same brand family + kids-ness, or None.

    e.g. ('Paramount + - FR', 'GSA') -> 'Paramount + - GSA'. Returns None when the
    target market has no equivalent brand (so the caller can flag it, not guess).
    """
    brands = brands_cfg if brands_cfg is not None else brands_config().get("brands", {})
    sig = brand_sync.brand_signature(source_campaign_name)
    if not sig:
        return None
    for v in brands.values():
        cname = v.get("campaign_name", "")
        if (brand_sync.region_of(cname) == target_region
                and brand_sync.brand_signature(cname) == sig):
            return cname
    return None


def mirror_plan(source: dict[str, Any], target_region: str,
                brands_cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Copy a source plan-dict, re-pointed at the target market's equivalent brand.

    Carries the shared creative + targeting (title, season, durations, content,
    genres, showlist, products, pluto, audience) and swaps region + campaign; the
    builder re-derives naming, ad units, geo and placements for the target. Raises
    ValueError if the target market has no equivalent brand.
    """
    src_campaign = (source.get("campaign") or {}).get("name", "")
    equ = equivalent_campaign(src_campaign, target_region, brands_cfg)
    if not equ:
        sig = brand_sync.brand_signature(src_campaign)
        raise ValueError(
            f"No {target_region} equivalent for {src_campaign!r} "
            f"(brand {sig[0] if sig else '?'}) — build it by hand.")
    plan = copy.deepcopy(source)
    plan["region"] = target_region
    plan["campaign"] = {"name": equ}
    for field in _SOURCE_SPECIFIC:
        plan.pop(field, None)
    return plan


def mirror_to_markets(source: dict[str, Any], target_regions: list[str],
                      brands_cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Mirror to several markets at once. Returns {plans: {region: plan},
    skipped: {region: reason}} so a caller can report the markets with no equivalent."""
    plans, skipped = {}, {}
    for region in target_regions:
        try:
            plans[region] = mirror_plan(source, region, brands_cfg)
        except ValueError as exc:
            skipped[region] = str(exc)
    return {"plans": plans, "skipped": skipped}
