"""Load a SupportPlan from its various sources.

Today: YAML files (the primary format, version-controlled in plans/).
Planned: Google Sheet templates and Salesforce Cases — both normalize into the
same SupportPlan, so the rest of the system is source-agnostic. See
integrations/gsheets.py and integrations/salesforce.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Flight, SupportPlan


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
        brand=raw.get("brand"),
        formats=list(raw.get("formats") or []),
        networks=list(raw.get("networks") or []),
        genres=list(raw.get("genres") or []),
        showlist=list(raw.get("showlist") or []),
        audience_segments=list(raw.get("audience_segments") or []),
        pluto_categories=categories,
        pluto_channels=channels,
        pplus_user_states=list(raw.get("pplus_user_states") or []),
        recommended_show=raw.get("recommended_show"),
        exclude_show=raw.get("exclude_show"),
        season_or_messaging=raw.get("season_or_messaging"),
        durations=[int(d) for d in (raw.get("durations") or [])],
        content_type=raw.get("content_type") or "show",
        content_id=raw.get("content_id"),
        recommended_show_id=raw.get("recommended_show_id"),
        video_domination=raw.get("video_domination") or None,
        video_domination_targeting=list(raw.get("video_domination_targeting") or []),
        takeover=raw.get("takeover") or None,
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

    Brand derives from the Campaign; Formats default to the brand's format set. Leaves
    everything else to the builder's own defaults (IO name, recommended/exclude show).
    """
    from .config import brand_for_campaign, brands_config
    if not plan.brand:
        plan.brand = brand_for_campaign(plan.campaign)
    if not plan.formats and plan.brand:
        cfg = brands_config().get("brands", {}).get(plan.brand, {})
        plan.formats = list(cfg.get("formats") or [])


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

    if plan.takeover:
        from .config import operative_takeovers_config
        types = operative_takeovers_config().get("types", {})
        if plan.takeover not in types:
            problems.append(f"Unknown Takeover {plan.takeover!r}. Known: {', '.join(types)}.")
    return problems
