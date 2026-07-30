"""Generate docs/salesforce-case-fields.csv — the Salesforce admin build sheet — from
the live config, so the Case object spec never drifts from what the automation reads.

Run:  python scripts/build_salesforce_fields.py
"""
from __future__ import annotations
import csv
from pathlib import Path
from promo_ops.integrations.salesforce import build_case_field_rows, CASE_STATUS_REASON_VALUES

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "salesforce-case-fields.csv"
COLS = ["Object", "Section", "Field Label", "API Name", "Data Type",
        "Length / Picklist Values", "Required (planner)", "Help Text"]


def build() -> Path:
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for row in build_case_field_rows():
            w.writerow(row)
        for field, value, help_ in CASE_STATUS_REASON_VALUES:
            w.writerow({"Object": "Case", "Section": "Status/Reason",
                        "Field Label": f"{field} (add value)", "API Name": field,
                        "Data Type": "Picklist value", "Length / Picklist Values": value,
                        "Required (planner)": "", "Help Text": help_})
    return OUT


if __name__ == "__main__":
    print(f"Wrote {build()}")
