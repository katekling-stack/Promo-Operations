"""Load a SupportPlan from its various sources.

Today: YAML files (the primary format, version-controlled in plans/).
Planned: Google Sheet templates and Salesforce Cases — both normalize into the
same SupportPlan, so the rest of the system is source-agnostic. See
integrations/gsheets.py and integrations/salesforce.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import Flight, SupportPlan

_TRUE_TEXT = {"true", "yes", "y", "1", "x", "✓"}


def _truthy(value: Any) -> bool:
    """Robust bool for a flag that can arrive as a real bool (form/JSON), a Y/N sheet
    cell, or a 'Yes'/'No' Salesforce picklist. 'No'/'' -> False (not Python-truthy)."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE_TEXT


_DAYPART_DAYS = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}

# FreeWheel daypart times are WHOLE HOURS only, and START and END have DIFFERENT valid
# lists (verified live): a START may be "12 MIDNIGHT", but there is NO midnight END — the
# latest end is "11:00PM", which runs THROUGH the end of the day. Off-the-hour inputs (e.g.
# "8:30PM") are rejected; "12:00AM"/"12:00PM" normalize to the tokens.
_VALID_START_TIMES = "12 MIDNIGHT, 01:00AM–11:00AM, 12 NOON, 01:00PM–11:00PM"
_VALID_END_TIMES = "01:00AM–11:00AM, 12 NOON, 01:00PM–11:00PM (no midnight end — use 11:00PM)"


def _norm_daypart_time(t: str, is_end: bool = False) -> str:
    """Normalize a daypart time to FreeWheel's exact token, or raise a clear ValueError.

    Whole hours only. "12:00AM"->"12 MIDNIGHT" (start only), "12:00PM"->"12 NOON". A midnight
    END is rejected (FreeWheel has none) — the caller should use "11:00PM" to run through the
    end of the day. All validated up front, BEFORE a live push can create a partial IO."""
    valid = _VALID_END_TIMES if is_end else _VALID_START_TIMES
    s = str(t).strip().upper().replace(" ", "")
    if s in ("12MIDNIGHT", "MIDNIGHT", "00:00", "0:00", "12:00AM"):
        if is_end:
            raise ValueError(
                f"Daypart end time {t!r} can't be midnight — FreeWheel dayparts have no "
                "midnight end. Use '11:00PM' to run through the end of the day, and put any "
                "after-midnight hours in a SEPARATE window that starts at '12:00AM'.")
        return "12 MIDNIGHT"
    if s in ("12NOON", "NOON", "12:00PM"):
        return "12 NOON"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(AM|PM)", s)
    if not m:
        raise ValueError(
            f"Daypart time {t!r} isn't a recognized time. Use whole hours like "
            f"'08:00PM'. Valid: {valid}.")
    hh, mm, ap = int(m.group(1)), m.group(2), m.group(3)
    if mm != "00":
        raise ValueError(
            f"Daypart time {t!r} must be on the hour — FreeWheel only accepts whole hours "
            f"({valid}). Change ':{mm}' to ':00' (round to the nearest hour).")
    if not 1 <= hh <= 11:
        raise ValueError(f"Daypart time {t!r} has an invalid hour. Valid: {valid}.")
    return f"{hh:02d}:00{ap}"


def _dayparts(raw: Any) -> list[dict]:
    """Normalize daypart windows. Each window needs start_day/end_day/start_time/end_time.
    Days are upper-cased and validated against the weekday enum; malformed windows are
    dropped (never a partial). Times are validated/normalized to FreeWheel's whole-hour
    tokens — an off-the-hour time (e.g. '08:30PM') raises a clear error at build time,
    BEFORE a live push creates the IO. Empty -> [] (= 24/7, no daypart_targeting emitted)."""
    out: list[dict] = []
    for w in (raw or []):
        if not isinstance(w, dict):
            continue
        sd = str(w.get("start_day") or "").strip().upper()
        ed = str(w.get("end_day") or sd).strip().upper()
        st = str(w.get("start_time") or "").strip()
        et = str(w.get("end_time") or "").strip()
        if sd in _DAYPART_DAYS and ed in _DAYPART_DAYS and st and et:
            out.append({"start_day": sd, "end_day": ed,
                        "start_time": _norm_daypart_time(st, is_end=False),
                        "end_time": _norm_daypart_time(et, is_end=True)})
    return out


def _flatten_pluto(raw: dict[str, Any]) -> tuple[list[str], list[str]]:
    pluto = raw.get("pluto") or {}
    return (
        list(pluto.get("categories") or []),
        list(pluto.get("channels") or []),
    )


def support_plan_from_dict(raw: dict[str, Any]) -> SupportPlan:
    """Build a SupportPlan from a plain dict (YAML/JSON/sheet row/SF record)."""
    categories, channels = _flatten_pluto(raw)
    flight_raw = raw.get("flight") or {}
    plan = SupportPlan(
        promoted_title=raw["promoted_title"],
        region=raw["region"],
        language=raw.get("language"),
        brand=raw.get("brand"),
        formats=list(raw.get("formats") or []),
        networks=list(raw.get("networks") or []),
        genres=list(raw.get("genres") or []),
        showlist=list(raw.get("showlist") or []),
        my5_site_groups=list(raw.get("my5_site_groups") or []),
        audience_segments=list(raw.get("audience_segments") or []),
        pluto_categories=categories,
        pluto_channels=channels,
        pplus_user_states=list(raw.get("pplus_user_states") or []),
        recommended_show=raw.get("recommended_show"),
        exclude_show=raw.get("exclude_show"),
        exclude_series=list(raw.get("exclude_series") or []),
        exclude_channels=list(raw.get("exclude_channels") or []),
        exclude_videos=list(raw.get("exclude_videos") or []),
        exclude_audience_segments=list(raw.get("exclude_audience_segments") or []),
        season_or_messaging=raw.get("season_or_messaging"),
        primary_trafficker=raw.get("primary_trafficker"),
        scene_lift=(raw.get("scene_lift") or None),
        standard=_truthy(raw.get("standard")),
        existing_io_id=(str(raw.get("existing_io_id")).strip() or None
                        if raw.get("existing_io_id") else None),
        io_brand=((str(raw.get("io_brand") or raw.get("brand_pick")).strip() or None)
                  if (raw.get("io_brand") or raw.get("brand_pick")) else None),
        dayparts=_dayparts(raw.get("dayparts")),
        durations=[int(d) for d in (raw.get("durations") or [])],
        content_type=raw.get("content_type") or "show",
        content_id=raw.get("content_id"),
        recommended_show_id=raw.get("recommended_show_id"),
        video_domination=raw.get("video_domination") or None,
        video_domination_targeting=list(raw.get("video_domination_targeting") or []),
        takeover=raw.get("takeover") or None,
        product_overrides=dict(raw.get("product_overrides") or {}),
        kids_audience=list(raw.get("kids_audience") or []),
        rating_restrictions=list(raw.get("rating_restrictions") or []),
        rating_inclusions=list(raw.get("rating_inclusions") or []),
        geo_states=list(raw.get("geo_states") or []),
        geo_dmas=list(raw.get("geo_dmas") or []),
        geo_cities=list(raw.get("geo_cities") or []),
        geo_states_exclude=list(raw.get("geo_states_exclude") or []),
        geo_dmas_exclude=list(raw.get("geo_dmas_exclude") or []),
        geo_cities_exclude=list(raw.get("geo_cities_exclude") or []),
        demographics=raw.get("demographics"),
        flight=Flight(
            start=flight_raw.get("start"),
            end=flight_raw.get("end"),
            code=flight_raw.get("code"),
        ),
        advertiser=raw.get("advertiser") or {},
        campaign=raw.get("campaign") or {},
        insertion_order_name=raw.get("insertion_order_name"),
        brand_id=raw.get("brand_id"),
        template_io_id=raw.get("template_io_id"),
        salesforce_case=raw.get("salesforce_case"),
    )
    _apply_defaults(plan)
    return plan


def _apply_defaults(plan: SupportPlan) -> None:
    """Fill fields that derive from the Campaign/Brand so a lean sheet == a full plan.

    Brand derives from the Campaign; Formats default to the brand's format set, then the
    Products toggles include/exclude specific products. Leaves everything else to the
    builder's own defaults (IO name, recommended/exclude show).
    """
    from .config import brand_for_campaign, brands_config, pinned_campaign_id
    if not plan.brand:
        plan.brand = brand_for_campaign(plan.campaign)
    # Pin the parent campaign to the authoritative id in brands.yaml when only a name is given.
    # Two campaigns can share a name (e.g. an old "Paramount + - USA" at the 500-IO cap and its
    # replacement); pinning here means the push lands on the intended campaign, not whichever a
    # name search returns first.
    if plan.campaign and not plan.campaign.get("resolved_id") and plan.campaign.get("name"):
        pinned = pinned_campaign_id(plan.campaign.get("name"))
        if pinned:
            plan.campaign["resolved_id"] = pinned
    cfg = brands_config().get("brands", {}).get(plan.brand or "", {})
    if not plan.formats and plan.brand:
        plan.formats = list(cfg.get("formats") or [])
    _apply_product_overrides(plan, cfg)
    _drop_non_domestic_only(plan)


# After Mid-Roll Bumper is a Domestic (US) product only — its format members must never
# build in any other market, whatever a brand config or Products toggle says.
from .models import PRODUCT_FAMILIES as _PRODUCT_FAMILIES
DOMESTIC_ONLY_FORMATS = set(_PRODUCT_FAMILIES["after_midroll_bumper"])


def _drop_non_domestic_only(plan: SupportPlan) -> None:
    from .config import regions_config
    domestic = bool(regions_config().get("regions", {}).get(plan.region or "", {}).get("domestic"))
    if not domestic and plan.formats:
        plan.formats = [f for f in plan.formats if f not in DOMESTIC_ONLY_FORMATS]


def _apply_product_overrides(plan: SupportPlan, brand_cfg: dict[str, Any]) -> None:
    """Include/exclude products per the plan's Products toggles (blank = brand default).

    True includes the product (if the brand supports it — its default set plus any
    `optional_formats`, plus the UNIVERSAL formats that run on any brand), False removes
    it. Preserves the existing format order and appends opted-in extras.
    """
    from .models import PRODUCT_FAMILIES
    if not plan.product_overrides:
        return
    available = (set(brand_cfg.get("formats") or [])
                 | set(brand_cfg.get("optional_formats") or [])
                 | UNIVERSAL_OPTIONAL_FORMATS)
    formats = list(plan.formats)
    for family_key, want in plan.product_overrides.items():
        members = PRODUCT_FAMILIES.get(family_key, [family_key])
        if want is False:
            formats = [f for f in formats if f not in members]
        elif want is True:
            for member in members:
                if member in available and member not in formats:
                    formats.append(member)
    plan.formats = formats


# Products that can run on ANY brand on request (not tied to a brand's default set) —
# Pause Ads run across P+, CBS, Pluto TV, and more, so "Include Pause Ads = Yes" adds
# them to any brand.
UNIVERSAL_OPTIONAL_FORMATS = {"pause_ads"}


def load_plan(path: str | Path) -> SupportPlan:
    """Load a support plan from a YAML file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not raw:
        raise ValueError(f"Empty or invalid plan file: {path}")
    return support_plan_from_dict(raw)


def validate_plan(plan: SupportPlan) -> list[str]:
    """Intake gate: return human-readable problems with a plan (empty == OK).

    Runs before build/create so a bad hand-off is caught up front rather than
    producing a wrong draft. Checks required fields, and that brand / region /
    formats are known to the config.
    """
    from .config import (brands_config, regions_config, placement_templates_config,
                         brand_for_campaign)
    problems: list[str] = []
    brand = plan.brand or brand_for_campaign(plan.campaign)

    if not plan.promoted_title:
        problems.append("Promoted Title is required.")
    if not plan.formats:
        problems.append("At least one Format is required.")

    regions = regions_config().get("regions", {})
    if not plan.region:
        problems.append("Region is required.")
    elif plan.region not in regions:
        problems.append(f"Unknown Region {plan.region!r}. Known: {', '.join(regions)}.")

    brands = brands_config().get("brands", {})
    if not brand:
        problems.append("Brand is required (or a recognized Campaign it can be derived "
                        "from) — it drives ad units, main SGs, excludes.")
    elif brand not in brands:
        problems.append(f"Unknown Brand {brand!r}. Known: {', '.join(brands)}.")

    known_formats = placement_templates_config().get("formats", {})
    for fmt in plan.formats:
        if fmt not in known_formats:
            problems.append(f"Unknown Format {fmt!r}. Known: {', '.join(known_formats)}.")

    if not (plan.campaign.get("resolved_id") or plan.campaign.get("name")):
        problems.append("Parent Campaign (name or ID) is required.")

    if plan.video_domination:
        from .config import video_dominations_config
        vds = video_dominations_config().get("options", {})
        if plan.video_domination not in vds:
            problems.append(f"Unknown Video Domination {plan.video_domination!r}. "
                            f"Known: {', '.join(vds)}.")
        elif plan.video_domination == "pluto" and not plan.video_domination_targeting:
            problems.append("Pluto Video Domination selected but no Video Domination "
                            "Targeting (Pluto categories) provided.")

    if plan.scene_lift:
        from .config import scene_lifts_config
        sl = scene_lifts_config()
        sl_type = str(plan.scene_lift).lower()
        if sl_type not in sl.get("tiers_by_type", {}):
            problems.append(f"Unknown Scene Lift type {plan.scene_lift!r}. "
                            f"Known: {', '.join(sl.get('tiers_by_type', {}))}.")
        campaign = (plan.campaign or {}).get("name", "")
        if campaign not in sl.get("target_ios", {}):
            problems.append(
                f"Scene Lift not set up for campaign {campaign!r}. Scene Lifts are Pluto "
                f"UK/CA/USA only — pick one of: {', '.join(sl.get('target_ios', {}))}.")

    known_kids = {"older", "younger"}
    for a in plan.kids_audience:
        if str(a).strip().lower() not in known_kids:
            problems.append(f"Unknown Kids Audience {a!r}. Known: older, younger.")

    if plan.takeover:
        from .config import operative_takeovers_config
        types = operative_takeovers_config().get("types", {})
        if plan.takeover not in types:
            problems.append(f"Unknown Takeover {plan.takeover!r}. Known: {', '.join(types)}.")
    return problems
