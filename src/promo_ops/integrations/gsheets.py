"""Google Sheets integration.

Two jobs:
  1. sync_audience_segments() — pull the "Audience Segments - Promo Operations" sheet
     (all tabs) into normalized CSV snapshots under data/audience_segments/, so the
     Tier-1 resolver has current segment data.
  2. read_plan_template() — read a standardized planning sheet into a support-plan
     dict (the "start with a Google Sheet template today" path).

Uses google-api-python-client + google-auth (install with the `gsheets` extra) and a
service account with read access to the sheet.

Each source tab has a slightly different column layout; TAB_COLUMN_MAP records how to
normalize the columns we've seen. New tabs just need an entry here.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from ..audience_segments import DATA_DIR
from ..config import env, require_env

# MAP: per-tab column layout. Values are the source header names.
# Target normalized columns: show, segment_name, segment_id, platform, region.
TAB_COLUMN_MAP = {
    "10 Streaming - Australia": {
        "show": "Show",
        "segment_name": "FW Audience Naming Convention",
        "region_const": "AU",
        "platform_const": "10 Streaming",
    },
    "Pluto (WIP)": {
        "show": 0,               # positional columns in this tab
        "segment_name": 1,
        "segment_id": 2,
        "region_const": "USA",
        "platform_const": "Pluto TV",
    },
}


def _sheets_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "google-api-python-client/google-auth not installed. "
            "Run: pip install -e '.[gsheets]'"
        ) from exc
    creds = service_account.Credentials.from_service_account_file(
        require_env("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=creds)


def sync_audience_segments(sheet_id: Optional[str] = None,
                           out_dir: Path = DATA_DIR) -> list[Path]:
    """Sync every mapped tab into a synced_<tab>.csv snapshot. Returns file paths."""
    sheet_id = sheet_id or require_env("AUDIENCE_SEGMENTS_SHEET_ID")
    service = _sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for sheet in meta.get("sheets", []):
        title = sheet["properties"]["title"]
        colmap = TAB_COLUMN_MAP.get(title)
        if not colmap:
            continue  # skip unmapped tabs; add to TAB_COLUMN_MAP to include
        values = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=title
        ).execute().get("values", [])
        rows = _normalize_tab(values, colmap)
        path = out_dir / f"synced_{_slug(title)}.csv"
        _write_csv(path, rows)
        written.append(path)
    return written


def _normalize_tab(values: list[list[str]], colmap: dict) -> list[dict[str, Any]]:
    if not values:
        return []
    header = values[0]
    rows = []
    for raw in values[1:]:
        def get(key):
            spec = colmap.get(key)
            if spec is None:
                return ""
            if isinstance(spec, int):
                return raw[spec] if spec < len(raw) else ""
            if spec in header:
                idx = header.index(spec)
                return raw[idx] if idx < len(raw) else ""
            return ""
        rows.append({
            "show": get("show"),
            "segment_name": get("segment_name"),
            "segment_id": get("segment_id"),
            "platform": colmap.get("platform_const", ""),
            "region": colmap.get("region_const", ""),
        })
    return [r for r in rows if r["show"] and r["segment_name"]]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["show", "segment_name", "segment_id", "platform", "region", "source"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            r.setdefault("source", path.stem)
            writer.writerow(r)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower()


# --------------------------------------------------------------------------- #
# Campaign plan template
#
# The interim "fill out a sheet per campaign" workflow. The template is two tabs:
#
#   "Plan"      — key/value: one scalar field per row (col A = label, col B = value).
#   "Targeting" — columnar lists: one list per column (Networks | Genres | Showlist
#                 | Pluto Categories | Pluto Channels), each running down its column.
#
# See templates/campaign-plan/ for importable CSVs (filled with the Frisco King
# example) and docs/PLAN_TEMPLATE.md for the field reference.
# --------------------------------------------------------------------------- #

# Products section: template label -> PRODUCT_FAMILIES key. Each is a Yes/No toggle;
# blank = brand default. Order here is the order they appear in the Plan tab.
PRODUCT_TOGGLES: dict[str, str] = {
    "include remnant video": "remnant_video",
    "include pause ads": "pause_ads",
    "include premium pre-roll": "premium_preroll",
    "include essential bumper": "essential_bumper",
    "include cbs pre-roll": "cbs_preroll",
    "include after mid-roll bumper": "after_midroll_bumper",
    "include 1z lockdown": "cbs_1z_lockdown",
    "include 2z lockdown": "cbs_2z_lockdown",
}

# Plan tab: normalized label -> where it lands in the plan dict (+ optional type).
PLAN_TAB_FIELDS: dict[str, dict[str, Any]] = {
    "promoted title": {"path": ["promoted_title"]},
    "region": {"path": ["region"]},
    "salesforce case": {"path": ["salesforce_case"]},
    # FreeWheel nesting: IO under an existing Campaign under an Advertiser.
    # Specify the EXACT Advertiser + Campaign (name and/or id).
    "advertiser": {"path": ["advertiser", "name"]},
    "advertiser id": {"path": ["advertiser", "resolved_id"]},
    "campaign name": {"path": ["campaign", "name"]},
    "campaign id": {"path": ["campaign", "resolved_id"]},
    "insertion order name": {"path": ["insertion_order_name"]},
    "recommended show": {"path": ["recommended_show"]},
    "exclude show": {"path": ["exclude_show"]},
    "season or messaging": {"path": ["season_or_messaging"]},
    "video durations": {"path": ["durations"], "type": "list"},
    "content type": {"path": ["content_type"]},          # show | movie
    "content id": {"path": ["content_id"]},               # ShowID / MovieID
    # Recommended Show key-value (Tier 1 + guaranteed). Defaults to Content ID when
    # blank; the assigned CM fills this with the recommended-show value.
    "recommended show id": {"path": ["recommended_show_id"]},
    # Video Domination selector + (for Pluto) its Pluto-category targeting.
    "video domination": {"path": ["video_domination"]},
    "video domination targeting": {"path": ["video_domination_targeting"], "type": "list"},
    "takeover": {"path": ["takeover"]},
    # Optional / legacy — kept for back-compat, not in the standard template.
    "brand": {"path": ["brand"]},
    "advertiser name contains": {"path": ["advertiser", "name_contains"], "type": "list"},
    "flight start": {"path": ["flight", "start"]},
    "flight end": {"path": ["flight", "end"]},
    "flight code": {"path": ["flight", "code"]},
    "formats": {"path": ["formats"], "type": "list"},
    "p+ user states": {"path": ["pplus_user_states"], "type": "list"},
    "demographics age": {"path": ["demographics", "age"]},
    "demographics gender": {"path": ["demographics", "gender"]},
}

# Product toggles land in plan["product_overrides"][<family>] as booleans.
for _label, _family in PRODUCT_TOGGLES.items():
    PLAN_TAB_FIELDS[_label] = {"path": ["product_overrides", _family], "type": "bool"}

# Targeting tab: normalized column header -> where its column of values lands.
# Matching is by prefix, so "Audience Segments (Tier 1)" matches "audience segments".
TARGETING_TAB_COLUMNS: dict[str, list[str]] = {
    "audience segments": ["audience_segments"],   # Tier 1
    "kids audience": ["kids_audience"],            # older / younger (Kids brands)
    "networks": ["networks"],
    "genres": ["genres"],
    "showlist": ["showlist"],
    "pluto categories": ["pluto", "categories"],
    "pluto channels": ["pluto", "channels"],
}

_TRUE_VALUES = {"y", "yes", "true", "x", "1", "✓"}


def _set_nested(target: dict[str, Any], path: list[str], value: Any) -> None:
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def parse_plan_tab(rows: list[list[str]]) -> dict[str, Any]:
    """Parse the key/value 'Plan' tab rows into (partial) plan dict."""
    from .salesforce import _split
    plan: dict[str, Any] = {}
    for row in rows:
        if not row or not row[0].strip():
            continue
        label = row[0].strip().lower()
        spec = PLAN_TAB_FIELDS.get(label)
        if not spec:
            continue  # ignore comment/header rows
        raw = row[1].strip() if len(row) > 1 else ""
        if raw == "":
            continue
        kind = spec.get("type")
        if kind == "list":
            value: Any = _split(raw)
        elif kind == "bool":
            value = raw.lower() in _TRUE_VALUES
        else:
            value = raw
        _set_nested(plan, spec["path"], value)
    return plan


def parse_targeting_tab(rows: list[list[str]]) -> dict[str, Any]:
    """Parse the columnar 'Targeting' tab rows into (partial) plan dict."""
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]
    columns: dict[int, list[str]] = {i: [] for i in range(len(header))}
    for row in rows[1:]:
        for i in range(len(header)):
            cell = row[i].strip() if i < len(row) else ""
            if cell:
                columns[i].append(cell)
    plan: dict[str, Any] = {}
    for i, col_label in enumerate(header):
        path = _match_targeting_column(col_label)
        if path and columns[i]:
            _set_nested(plan, path, columns[i])
    return plan


def _match_targeting_column(col_label: str) -> Optional[list[str]]:
    """Match a header to a targeting column by prefix (tolerates '(Tier 1)' etc.)."""
    for key, path in TARGETING_TAB_COLUMNS.items():
        if col_label == key or col_label.startswith(key):
            return path
    return None


def assemble_plan_template(plan_rows: list[list[str]],
                           targeting_rows: list[list[str]]) -> dict[str, Any]:
    """Merge the two tabs into a single plan dict (support_plan_from_dict-ready)."""
    plan = parse_plan_tab(plan_rows)
    targeting = parse_targeting_tab(targeting_rows)
    # Deep-merge the pluto sub-dict; everything else is disjoint.
    for key, value in targeting.items():
        if key == "pluto":
            plan.setdefault("pluto", {}).update(value)
        else:
            plan[key] = value
    return plan


def read_plan_template(sheet_id: str, plan_tab: str = "Plan",
                       targeting_tab: str = "Targeting") -> dict[str, Any]:
    """Read a campaign-plan sheet (Plan + Targeting tabs) into a plan dict."""
    service = _sheets_service()

    def _rows(tab: str) -> list[list[str]]:
        return service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=tab
        ).execute().get("values", [])

    return assemble_plan_template(_rows(plan_tab), _rows(targeting_tab))
