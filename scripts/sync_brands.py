"""Sync FreeWheel (Promo) Brands per advertiser/region -> data/brands/synced_brands.csv.

The Brand list feeds the form's Brand picker (and, later, the IO brand_id + exclusivity).
Reads the MRM Publisher API (XML) via the PromoAdOps INTERNAL client-credentials app
(integrations/freewheel_mrm.py). Brands live per-advertiser; each VCBS "(Promo)"
advertiser maps to one of our regions (Adult/Kids).

    python scripts/sync_brands.py            # all current regions
    python scripts/sync_brands.py --region SE NO DK

Requires FREEWHEEL_MRM_CLIENT_ID / FREEWHEEL_MRM_CLIENT_SECRET in the environment.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from promo_ops.config import REPO_ROOT
from promo_ops.integrations.freewheel_mrm import FreeWheelMRMClient

OUT = REPO_ROOT / "data" / "brands" / "synced_brands.csv"

# Advertiser-name country token -> our region code. "USA"/"GSA"/"LATAM" already match.
NAME_TO_REGION = {
    "australia": "AU", "brazil": "BR", "canada": "CA", "denmark": "DK", "finland": "FI",
    "france": "FR", "gsa": "GSA", "ireland": "IE", "italy": "IT", "latam": "LATAM",
    "norway": "NO", "spain": "ES", "sweden": "SE", "united kingdom": "UK", "usa": "USA",
}


def _region_of(advertiser_name: str) -> str | None:
    low = advertiser_name.lower()
    for token, code in NAME_TO_REGION.items():
        if token in low:
            return code
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", nargs="*", default=[], help="limit to these region codes")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    want = {r.upper() for r in args.region}

    fw = FreeWheelMRMClient()
    advertisers = fw.list_advertisers("VCBS")
    # Only the "(Promo)" advertisers, skipping test accounts.
    advertisers = [a for a in advertisers
                   if "(Promo)" in a["name"] and "Tests Only" not in a["name"]]

    rows: list[dict] = []
    for a in sorted(advertisers, key=lambda x: x["name"]):
        region = _region_of(a["name"])
        if not region or (want and region not in want):
            continue
        kids = "kids" in a["name"].lower()
        brands = fw.list_brands(a["id"])
        promo = [b for b in brands
                 if "(promo)" in b["name"].lower() and b["status"].upper() == "ACTIVE"]
        print(f"  {a['name']:44} region={region:5} kids={int(kids)}  "
              f"{len(promo)}/{len(brands)} (Promo)")
        for b in promo:
            rows.append({"region": region, "kids": int(kids),
                         "advertiser_id": a["id"], "advertiser_name": a["name"],
                         "brand_id": b["id"], "brand_name": b["name"]})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["region", "kids", "advertiser_id",
                                           "advertiser_name", "brand_id", "brand_name"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["region"], x["kids"], x["brand_name"])):
            w.writerow(r)
    print(f"\nWrote {len(rows)} brands across "
          f"{len({r['region'] for r in rows})} regions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
