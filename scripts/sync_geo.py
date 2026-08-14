"""Turn FreeWheel's Geography Dataset dumps into committed geo reference tables.

FreeWheel publishes the geo code/ID reference as tab-separated dumps attached to the
"Geography Data" Streaming Hub user-guide page (hub.freewheel.tv ... /Geography+Data):
country.txt, state.txt, dma.txt, city.txt, postalCode.txt, isp.txt. Placement geo
targeting is written with the numeric *FreewheelID* from these tables
(geography_targeting.include.{country,state,dma,city}), so a CM's typed names have to
resolve to those IDs. There is no query API for this — the dumps are the source.

This script converts the raw dumps into the compact CSVs the engine + form read from
data/geo/, filtering the large tables to only the countries we operate in
(config/regions.yaml -> regions[].countries):

    state.csv   fw_id,country_iso,code,name        (all rows; ~90 KB)
    dma.csv     fw_id,dma_code,name                (all rows; US Nielsen DMAs)
    city.csv    fw_id,name,country_iso,state_fw_id (operating countries only)

postalCode.txt (1.8M rows / 72 MB) and isp.txt are NOT materialised — those levels are
supported by the engine via raw FreeWheel-ID passthrough, not name resolution, so there
is nothing to commit. country.txt already has a committed seed (seed_countries.csv).

Usage:
    python scripts/sync_geo.py --src /path/to/unzipped/geo/dumps
    # writes/overwrites data/geo/{state,dma,city}.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "geo"
REGIONS = REPO / "config" / "regions.yaml"

# Country NAME -> ISO code, for filtering the big tables to our footprint. FreeWheel's
# tables key geography by ISO country code; regions.yaml lists country names.
NAME_TO_ISO = {
    "United States": "US", "Canada": "CA", "Australia": "AU", "Mexico": "MX",
    "Argentina": "AR", "Chile": "CL", "Colombia": "CO", "Peru": "PE", "Brazil": "BR",
    "United Kingdom": "GB", "Ireland": "IE", "France": "FR", "Italy": "IT",
    "Germany": "DE", "Switzerland": "CH", "Austria": "AT", "Finland": "FI",
    "Denmark": "DK", "Norway": "NO", "Sweden": "SE", "Spain": "ES",
}


def operating_isos() -> set[str]:
    cfg = yaml.safe_load(REGIONS.read_text())
    isos: set[str] = set()
    unknown: set[str] = set()
    for region in cfg.get("regions", {}).values():
        for name in region.get("countries") or []:
            iso = NAME_TO_ISO.get(name)
            (isos.add(iso) if iso else unknown.add(name))
    if unknown:
        print(f"  ! no ISO mapping for {sorted(unknown)} (add to NAME_TO_ISO)")
    return isos


def _read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = [ln.rstrip("\n").split("\t") for ln in fh]
    return rows[0], rows[1:]


def sync_state(src: Path) -> int:
    # FreewheelID  country  stateName(code)  decription(name)
    _, rows = _read_tsv(src / "state.txt")
    out = DATA / "state.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fw_id", "country_iso", "code", "name"])
        n = 0
        for r in rows:
            if len(r) < 4:
                continue
            w.writerow([r[0], r[1], r[2], r[3]])
            n += 1
    print(f"  state.csv: {n} rows")
    return n


def sync_dma(src: Path) -> int:
    # FreewheelID  DMAID  description
    _, rows = _read_tsv(src / "dma.txt")
    out = DATA / "dma.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fw_id", "dma_code", "name"])
        n = 0
        for r in rows:
            if len(r) < 3:
                continue
            w.writerow([r[0], r[1], r[2]])
            n += 1
    print(f"  dma.csv: {n} rows")
    return n


def sync_city(src: Path, isos: set[str]) -> int:
    # FreewheelID  cityName  country  state(state FreewheelID)  cityDescription
    _, rows = _read_tsv(src / "city.txt")
    out = DATA / "city.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fw_id", "name", "country_iso", "state_fw_id"])
        n = 0
        for r in rows:
            if len(r) < 4 or r[2] not in isos:
                continue
            w.writerow([r[0], r[1], r[2], r[3]])
            n += 1
    print(f"  city.csv: {n} rows (filtered to {len(isos)} countries)")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="dir with unzipped *.txt geo dumps")
    args = ap.parse_args()
    src = Path(args.src)
    DATA.mkdir(parents=True, exist_ok=True)
    isos = operating_isos()
    print(f"Operating ISO countries: {sorted(isos)}")
    sync_state(src)
    sync_dma(src)
    sync_city(src, isos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
