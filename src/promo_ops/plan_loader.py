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
    return SupportPlan(
        promoted_title=raw["promoted_title"],
        region=raw["region"],
        brand=raw["brand"],
        formats=list(raw.get("formats") or []),
        networks=list(raw.get("networks") or []),
        genres=list(raw.get("genres") or []),
        showlist=list(raw.get("showlist") or []),
        pluto_categories=categories,
        pluto_channels=channels,
        pplus_user_states=list(raw.get("pplus_user_states") or []),
        demographics=raw.get("demographics"),
        flight=Flight(
            start=flight_raw.get("start"),
            end=flight_raw.get("end"),
            code=flight_raw.get("code"),
        ),
        advertiser=raw.get("advertiser") or {},
        campaign=raw.get("campaign") or {},
        salesforce_case=raw.get("salesforce_case"),
    )


def load_plan(path: str | Path) -> SupportPlan:
    """Load a support plan from a YAML file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not raw:
        raise ValueError(f"Empty or invalid plan file: {path}")
    return support_plan_from_dict(raw)
