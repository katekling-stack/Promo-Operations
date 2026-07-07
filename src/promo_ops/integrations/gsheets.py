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


def read_plan_template(sheet_id: str, tab: str = "Plan") -> dict[str, Any]:
    """Read a standardized planning sheet (key/value rows) into a plan dict.

    Expected layout: column A = field name, column B = value (lists semicolon-
    separated). CONFIRM: finalize the template layout with the ops team.
    """
    service = _sheets_service()
    values = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=tab
    ).execute().get("values", [])
    kv = {row[0].strip(): (row[1] if len(row) > 1 else "") for row in values if row}
    from ..integrations.salesforce import _split  # reuse list splitting
    plan: dict[str, Any] = {}
    for key, value in kv.items():
        plan[key] = _split(value)
    return plan
