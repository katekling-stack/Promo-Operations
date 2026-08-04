"""Export canonical targeting option lists from the FreeWheel-synced data.

These are the *pre-defined values* for the targeting fields — the source of truth for
both the interactive plan form's dropdowns and (eventually) the Salesforce picklists,
so a planner can only pick real values (no free-text typos).

Outputs (templates/targeting-options/):
  genres.csv                     one row per canonical genre (global, not per-region)
  pluto-categories.csv           pluto_market, category   (Tier 3)
  pluto-channels.csv             pluto_market, channel    (Tier 2)
  audience-segments.csv          segment_name             (Tier 1 DDA)
  REGION-MAP.md                  how our regions map to Pluto market codes

Genres + categories are small (good as scroll/multi-select). Channels (~13k) and
audience (~6k) are large — use a type-to-search picker. Showlist is NOT exported: FW
has ~230k series, so it stays a search-as-you-type field, not a finite list.

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
# regions map 1:1. GSA and LATAM span several Pluto markets, so per the team we use one
# PRIMARY market each (GSA -> DE, LATAM -> MX) for a clean list — change these here if a
# different lead market is preferred.
REGION_TO_PLUTO_MARKETS = {
    "USA": ["US"], "CA": ["CA"], "AU": ["AU"], "BR": ["BR"], "UK": ["UK"],
    "IE": ["IE"], "FR": ["FR"], "IT": ["IT"], "FI": ["FI"], "DK": ["DK"],
    "NO": ["NO"], "SE": ["SE"], "ES": ["ES"],
    "GSA": ["DE"],     # primary of DE/AT/CH
    "LATAM": ["MX"],   # primary of the LATAM markets
}


def _active(path: Path):
    for r in csv.DictReader(path.open()):
        if r.get("status", "ACTIVE") == "ACTIVE":
            yield r


def genres() -> list[str]:
    seen: dict[str, None] = {}
    for r in _active(DATA / "video_groups" / "seed_genre_video_groups.csv"):
        name = r["name"]
        if name.startswith("VG: Genre:"):
            label = name.split("VG: Genre:", 1)[1].strip()
            seen.setdefault(label, None)
    return sorted(seen)


_CAT = re.compile(r"SG: PlutoTV (?:Promo )?Category:?\s*(.*)")
_CHAN = re.compile(r"SG: PlutoTV Channels:\s*([A-Z]{2}):\s*(.*)")


def _pluto():
    """Return {market: {'categories': set, 'channels': set}} from site groups."""
    out: dict[str, dict[str, set]] = {}
    for r in _active(DATA / "site_groups" / "seed_site_groups.csv"):
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


def audience_segments() -> list[str]:
    path = DATA / "audience_segments" / "synced_audience_items.csv"
    if not path.exists():
        return []
    names = {r.get("segment_name") or r.get("name") for r in csv.DictReader(path.open())}
    return sorted(n for n in names if n)


def build() -> dict[str, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    g = genres()
    (OUT / "genres.csv").write_text(
        "genre\n" + "\n".join(g) + "\n", encoding="utf-8")

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

    # Same data keyed by OUR region (via the primary market) — the directly-usable form
    # of the lists: for a Salesforce dependent picklist (Region controls the values).
    def _by_region(kind: str, path: Path):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["region", kind[:-1] if kind.endswith("s") else kind])
            for region, markets in REGION_TO_PLUTO_MARKETS.items():
                vals = sorted({v for m in markets for v in pluto.get(m, {}).get(kind, [])})
                for v in vals:
                    w.writerow([region, v])
    _by_region("categories", OUT / "pluto-categories-by-region.csv")
    _by_region("channels", OUT / "pluto-channels-by-region.csv")

    aud = audience_segments()
    (OUT / "audience-segments.csv").write_text(
        "segment_name\n" + "\n".join(aud) + "\n", encoding="utf-8")

    lines = ["# Region → Pluto market mapping", "",
             "Pluto categories/channels are keyed by country. Our single-country regions",
             "map 1:1; GSA and LATAM span several markets (confirm the intended set).", "",
             "| Our region | Pluto market(s) | categories | channels |",
             "|---|---|---|---|"]
    for region, markets in REGION_TO_PLUTO_MARKETS.items():
        cats = len({c for m in markets for c in pluto.get(m, {}).get("categories", [])})
        chans = len({c for m in markets for c in pluto.get(m, {}).get("channels", [])})
        lines.append(f"| {region} | {', '.join(markets)} | {cats} | {chans} |")
    (OUT / "REGION-MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"genres": len(g),
            "pluto_markets": len(pluto),
            "categories": sum(len(v.get("categories", [])) for v in pluto.values()),
            "channels": sum(len(v.get("channels", [])) for v in pluto.values()),
            "audience_segments": len(aud)}


if __name__ == "__main__":
    counts = build()
    print(f"Wrote {OUT.relative_to(REPO)}/:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
