"""Generate the master campaign-plan workbook (.xlsx) from the CSV templates + config.

The workbook is what planners actually copy per campaign: the same Plan + Targeting
layout as templates/campaign-plan/*.csv, but with data-validation **dropdowns** on the
constrained fields (Region, Campaign, Content Type, Video Domination, Takeover, Brand)
so invalid values can't be typed. Dropdown values are sourced from the YAML config, so
this stays in sync with what the builder accepts.

Run:  python scripts/build_template_workbook.py
Out:  templates/campaign-plan/Campaign-Plan-Template.xlsx
Upload that file to Google Drive and "Open with Google Sheets" to get the shared master.
"""

from __future__ import annotations

import csv
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

REPO = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO / "templates" / "campaign-plan"
CONFIG = REPO / "config"


def _yaml(name: str) -> dict:
    with (CONFIG / name).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _csv_rows(name: str) -> list[list[str]]:
    with (TEMPLATE_DIR / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def dropdown_sources() -> dict[str, list[str]]:
    """field-label (lowercased) -> allowed values, sourced from config."""
    regions = list(_yaml("regions.yaml").get("regions", {}))
    brands = _yaml("brands.yaml").get("brands", {})
    campaigns = [b.get("campaign_name") for b in brands.values() if b.get("campaign_name")]
    brand_keys = list(brands)
    vds = list(_yaml("video_dominations.yaml").get("options", {}))
    takeovers = list(_yaml("operative_takeovers.yaml").get("types", {}))
    return {
        "region": regions,
        "campaign name": campaigns,
        "content type": ["show", "movie"],
        "video domination": vds,
        "takeover": takeovers,
        "brand": brand_keys,
    }


# Styling
HEADER_FILL = PatternFill("solid", fgColor="0B3D91")
SECTION_FILL = PatternFill("solid", fgColor="1F6FEB")
WHITE_BOLD = Font(color="FFFFFF", bold=True)
GREY = Font(color="666666")
WRAP = Alignment(wrap_text=True, vertical="top")


def build(out: Path | None = None) -> Path:
    wb = Workbook()
    plan_ws = wb.active
    plan_ws.title = "Plan"
    targ_ws = wb.create_sheet("Targeting")
    lists_ws = wb.create_sheet("_Lists")

    sources = dropdown_sources()

    # --- hidden _Lists sheet: one column per dropdown, referenced by validations ---
    col_ranges: dict[str, str] = {}
    for i, (label, values) in enumerate(sources.items(), start=1):
        letter = get_column_letter(i)
        lists_ws.cell(row=1, column=i, value=label)
        for r, v in enumerate(values, start=2):
            lists_ws.cell(row=r, column=i, value=v)
        col_ranges[label] = f"_Lists!${letter}$2:${letter}${1 + len(values)}"
    lists_ws.sheet_state = "hidden"

    # --- Plan tab ---
    rows = _csv_rows("Plan.csv")
    plan_ws.column_dimensions["A"].width = 26
    plan_ws.column_dimensions["B"].width = 34
    plan_ws.column_dimensions["C"].width = 62
    for c, head in enumerate(rows[0], start=1):
        cell = plan_ws.cell(row=1, column=c, value=head)
        cell.fill = HEADER_FILL
        cell.font = WHITE_BOLD
    for r, row in enumerate(rows[1:], start=2):
        field = row[0] if len(row) > 0 else ""
        value = row[1] if len(row) > 1 else ""
        note = row[2] if len(row) > 2 else ""
        is_section = field.startswith("—")
        fcell = plan_ws.cell(row=r, column=1, value=field)
        vcell = plan_ws.cell(row=r, column=2, value=value)
        ncell = plan_ws.cell(row=r, column=3, value=note)
        ncell.font = GREY
        ncell.alignment = WRAP
        if is_section:
            for c in (1, 2, 3):
                plan_ws.cell(row=r, column=c).fill = SECTION_FILL
                plan_ws.cell(row=r, column=c).font = WHITE_BOLD
        else:
            fcell.font = Font(bold=True)
            key = field.strip().lower()
            if key in col_ranges:
                dv = DataValidation(type="list", formula1=col_ranges[key],
                                    allow_blank=True, showErrorMessage=True)
                dv.error = "Pick a value from the list."
                dv.prompt = "Choose from the dropdown."
                plan_ws.add_data_validation(dv)
                dv.add(vcell)

    # --- Targeting tab ---
    trows = _csv_rows("Targeting.csv")
    for c, head in enumerate(trows[0], start=1):
        cell = targ_ws.cell(row=1, column=c, value=head)
        cell.fill = HEADER_FILL
        cell.font = WHITE_BOLD
        cell.alignment = WRAP
        targ_ws.column_dimensions[get_column_letter(c)].width = 24
    for r, row in enumerate(trows[1:], start=2):
        for c, val in enumerate(row, start=1):
            targ_ws.cell(row=r, column=c, value=val)
    targ_ws.freeze_panes = "A2"
    plan_ws.freeze_panes = "A2"

    out = out or (TEMPLATE_DIR / "Campaign-Plan-Template.xlsx")
    wb.save(out)
    return out


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
