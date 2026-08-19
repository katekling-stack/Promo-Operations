"""Export canonical targeting option lists from the FreeWheel-synced data.

These are the *pre-defined values* for the targeting fields — the source of truth for
both the interactive plan form's dropdowns and (eventually) the Salesforce picklists,
so a planner can only pick real values (no free-text typos).

Outputs (templates/targeting-options/):
  genres.csv                     value, type   (Genre / Franchise / Daypart)
  pluto-categories-by-region.csv region, category   (Pluto regions only)
  pluto-channels-by-region.csv   region, channel    (Pluto regions only)
  pluto-categories.csv / -channels.csv   raw, keyed by Pluto market (reference)
  audience-segments.csv          segment_name, structure
  REGION-MAP.md                  our region -> Pluto market(s)

Refresh cadence: the Pluto/genre lists change slowly. Audience segments change DAILY —
re-run `promo-ops sync-audience-items` (pulls the live FreeWheel audience library) then
this script to ingest new ones. Showlist is NOT exported (FW has ~230k series -> stays a
search-as-you-type field).

Run: python scripts/build_targeting_options.py
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
OUT = REPO / "templates" / "targeting-options"

# Our campaign region -> the Pluto market its inventory lives under. Single-country
# regions map 1:1. GSA and LATAM span several markets, so per the team we use one
# PRIMARY market each (GSA -> DE, LATAM -> MX). Regions that don't run Pluto
# (regions.yaml has_pluto: false, e.g. AU, IE) are dropped automatically.
REGION_TO_PLUTO_MARKETS = {
    "USA": ["US"], "CA": ["CA"], "AU": ["AU"], "BR": ["BR"], "UK": ["UK"],
    "IE": ["IE"], "FR": ["FR"], "IT": ["IT"], "FI": ["FI"], "DK": ["DK"],
    "NO": ["NO"], "SE": ["SE"], "ES": ["ES"],
    "GSA": ["DE"], "LATAM": ["MX"],
}

# VG: Genre values to drop from the picklist (not real content genres).
REMOVE_GENRES = {"Pluto TV: KIDS  CONTENT (COPPA)", "SERIES", "SPECIAL"}

# Canonical audience-segment naming STRUCTURES (from the Promo Ops workbook). New
# segments matching these prefixes are ingested; anything else is ignored.
AUDIENCE_STRUCTURES = [
    ("GL-DDA-1P", lambda s: s.startswith("GL-DDA-1P")),
    ("AU-DWH-Summit", lambda s: s.startswith("AU - DWH -")),
    ("AAM-VCBS-Extension", lambda s: s.startswith("AAM-VCBS-")
        or s.startswith("AAM - ViacomCBS") or s.startswith("AAM-lotame")
        or s.startswith("AAM-acxiom")),
    ("comScore", lambda s: s.startswith("comScore")),
]


def _active(path: Path):
    for r in csv.DictReader(path.open()):
        if r.get("status", "ACTIVE") == "ACTIVE":
            yield r


def _pluto_regions() -> set[str]:
    """Regions that actually run Pluto (regions.yaml has_pluto)."""
    import yaml
    regions = yaml.safe_load((REPO / "config" / "regions.yaml").read_text())["regions"]
    return {r for r, cfg in regions.items() if cfg.get("has_pluto")}


def _vg_rows(*candidates: str):
    """Active rows from the first existing file in `candidates` (synced preferred, seed
    as the offline fallback) — so the picklist reflects the full FreeWheel list when
    synced, and still works from the committed seed otherwise."""
    for fname in candidates:
        path = DATA / "video_groups" / fname
        if path.exists():
            yield from _active(path)
            return


def genres() -> list[tuple[str, str]]:
    """(value, type) rows: content Genres + Sub-genres + Franchise values + Daypart options."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    # Top-level genres. "VG: Genre-Sub:" does NOT start with "VG: Genre:" (the '-' breaks
    # the match), so this loop is genres only.
    for r in _vg_rows("synced_genre_video_groups.csv", "seed_genre_video_groups.csv"):
        if r["name"].startswith("VG: Genre:"):
            label = r["name"].split("VG: Genre:", 1)[1].strip()
            if label and label not in REMOVE_GENRES and label not in seen:
                seen.add(label); out.append((label, "Genre"))
    # Sub-genres: tagged "Sub: X" so they read unambiguously and never collide with a
    # same-named top-level genre. Same picker (type "Genre"); the resolver keys them under
    # the same "Sub: X" tag.
    for r in _vg_rows("synced_genre_sub_video_groups.csv"):
        if r["name"].startswith("VG: Genre-Sub:"):
            sub = r["name"].split("VG: Genre-Sub:", 1)[1].strip()
            label = "Sub: " + sub
            if sub and label not in seen:
                seen.add(label); out.append((label, "Genre"))
    # Franchise values keep their bare name; Daypart values are prefixed "Daypart: X"
    # so they read unambiguously and never collide with a same-named genre (Sports,
    # News, Movies…), which are DIFFERENT FreeWheel video groups.
    for cands, split_on, kind, label_prefix in (
        (("synced_franchise_video_groups.csv", "seed_franchise_video_groups.csv"),
         "VG: Franchise:", "Franchise", ""),
        (("synced_daypart_video_groups.csv", "seed_daypart_video_groups.csv"),
         "VG: Daypart:", "Daypart", "Daypart: "),
        # Brand / business-division Video Groups (e.g. "VG: Biz Div-Brand: VCBS: Cable
        # Adults: BET") -> picker label "Brand: VCBS: Cable Adults: BET" (searchable by
        # "BET"); the resolver keys them the same way so they target their VG id.
        (("synced_brand_video_groups.csv", "seed_brand_video_groups.csv"),
         "VG: Biz Div-Brand:", "Brand", "Brand: "),
    ):
        for r in _vg_rows(*cands):
            if not r["name"].startswith(split_on):
                continue
            label = label_prefix + r["name"].split(split_on, 1)[-1].strip()
            if label and label not in seen:
                seen.add(label); out.append((label, kind))
    return sorted(out)


_CAT = re.compile(r"SG: PlutoTV (?:Promo )?Category:?\s*(.*)")
_CHAN = re.compile(r"SG: PlutoTV Channels:\s*([A-Z]{2}):\s*(.*)")


def _pluto():
    """Return {market: {'categories': set, 'channels': set}} from site groups. Prefers the
    freshly-synced list (refresh-form / sync-site-groups), falls back to the committed seed."""
    out: dict[str, dict[str, set]] = {}
    sg_dir = DATA / "site_groups"
    sg_file = next((sg_dir / f for f in ("synced_site_groups.csv", "seed_site_groups.csv")
                    if (sg_dir / f).exists()), sg_dir / "seed_site_groups.csv")
    for r in _active(sg_file):
        n = r["name"]
        if "Channels:" in n:
            m = _CHAN.match(n)
            if m and m.group(2).strip():
                out.setdefault(m.group(1), {}).setdefault("channels", set()).add(m.group(2).strip())
        elif "Category" in n:
            m = _CAT.match(n)
            if not m:
                continue
            parts = [p.strip() for p in m.group(1).split(":")]
            if len(parts) >= 2 and re.fullmatch(r"[A-Z]{2}", parts[-1]):
                mkt, cat = parts[-1], ": ".join(parts[:-1])
                if cat:
                    out.setdefault(mkt, {}).setdefault("categories", set()).add(cat)
    return out


def shows() -> list[tuple[str, str]]:
    """(series_id, name) for every active FreeWheel Video Series — the searchable
    universe for the Showlist field. Too large to embed (~230k) so it backs a
    type-to-search lookup, never a scroll picklist or a free-text box."""
    path = DATA / "series" / "synced_series.csv"
    out: dict[str, str] = {}
    if path.exists():
        for r in _active(path):
            name = (r.get("name") or "").strip()
            sid = str(r.get("id") or "")
            if name and sid:
                out.setdefault(name, sid)
    return sorted((sid, name) for name, sid in out.items())


def _classify_segment(name: str) -> str | None:
    for label, fn in AUDIENCE_STRUCTURES:
        if fn(name):
            return label
    return None


def audience_segments() -> list[tuple[str, str]]:
    """(segment_name, structure) from the workbook seed UNION the live FW sync,
    keeping only segments that match a canonical structure. Re-run the FW sync
    (`promo-ops sync-audience-items`) before this to ingest the day's new segments."""
    found: dict[str, str] = {}
    seed = DATA / "audience_segments" / "seed_promo_segments.csv"
    if seed.exists():
        for r in csv.DictReader(seed.open()):
            n = (r.get("segment_name") or "").strip()
            if n:
                found[n] = r.get("structure") or _classify_segment(n) or "other"
    synced = DATA / "audience_segments" / "synced_audience_items.csv"
    if synced.exists():
        for r in csv.DictReader(synced.open()):
            n = (r.get("segment_name") or r.get("name") or "").strip()
            k = _classify_segment(n) if n else None
            if k and n not in found:
                found[n] = k
    return sorted(found.items())


def build() -> dict[str, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    g = genres()
    with (OUT / "genres.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["value", "type"])
        w.writerows(g)

    pluto = _pluto()
    with (OUT / "pluto-categories.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["pluto_market", "category"])
        for mkt in sorted(pluto):
            for cat in sorted(pluto[mkt].get("categories", [])):
                w.writerow([mkt, cat])
    with (OUT / "pluto-channels.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["pluto_market", "channel"])
        for mkt in sorted(pluto):
            for ch in sorted(pluto[mkt].get("channels", [])):
                w.writerow([mkt, ch])

    # Per-OUR-region files (via the primary market) — Pluto regions only.
    pluto_regions = _pluto_regions()
    active_regions = {r: m for r, m in REGION_TO_PLUTO_MARKETS.items() if r in pluto_regions}

    def _by_region(kind: str, path: Path):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["region", kind[:-1] if kind.endswith("s") else kind])
            for region, markets in active_regions.items():
                for v in sorted({v for m in markets for v in pluto.get(m, {}).get(kind, [])}):
                    w.writerow([region, v])
    _by_region("categories", OUT / "pluto-categories-by-region.csv")
    _by_region("channels", OUT / "pluto-channels-by-region.csv")

    aud = audience_segments()
    with (OUT / "audience-segments.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["segment_name", "structure"])
        w.writerows(aud)

    sh = shows()
    with (OUT / "shows.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["series_id", "name"])
        w.writerows(sh)

    lines = ["# Region → Pluto market mapping", "",
             "Pluto categories/channels are keyed by country. Single-country regions map",
             "1:1; GSA and LATAM use a primary market (GSA→DE, LATAM→MX). Regions that",
             "don't run Pluto (has_pluto: false) are omitted.", "",
             "| Our region | Pluto market(s) | categories | channels |",
             "|---|---|---|---|"]
    for region, markets in active_regions.items():
        cats = len({c for m in markets for c in pluto.get(m, {}).get("categories", [])})
        chans = len({c for m in markets for c in pluto.get(m, {}).get("channels", [])})
        lines.append(f"| {region} | {', '.join(markets)} | {cats} | {chans} |")
    (OUT / "REGION-MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    from collections import Counter
    struct = Counter(s for _, s in aud)
    return {"genres": sum(1 for _, t in g if t == "Genre"),
            "franchise": sum(1 for _, t in g if t == "Franchise"),
            "daypart": sum(1 for _, t in g if t == "Daypart"),
            "pluto_regions": len(active_regions),
            "categories": sum(len(v.get("categories", [])) for v in pluto.values()),
            "channels": sum(len(v.get("channels", [])) for v in pluto.values()),
            "audience_segments": len(aud), "audience_by_structure": dict(struct)}


if __name__ == "__main__":
    counts = build()
    print(f"Wrote {OUT.relative_to(REPO)}/:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
