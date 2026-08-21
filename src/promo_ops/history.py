"""Learn targeting from what ALREADY ran: harvest past FreeWheel IOs into a corpus of
plans (title + genres + showlist + Pluto channels), so the affinity suggester can
recommend by analogy to real, previously-built campaigns — no manual corpus, no scraping.

Flow:
  build_corpus(client, campaign_ids) -> reads each campaign's IOs, reads every placement's
  targeting, reverse-maps the FW IDs back to names (series -> show, genre VG -> genre,
  site group -> Pluto channel) using our synced snapshots, and writes one JSON line per IO.

The corpus rows match the plan-dict shape suggest_history() already consumes, so
suggest_history(title, genres, load_corpus(path)) works directly.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Optional

from .config import REPO_ROOT

_ID = re.compile(r'"(\d{4,})"')


# --- reverse maps from our synced snapshots -------------------------------- #

def _id_to_show() -> dict[str, str]:
    from .series import SeriesResolver
    return {r["id"]: r["name"] for r in SeriesResolver().load()._rows}


def _id_to_genre() -> dict[str, str]:
    from .video_groups import GenreVideoGroupResolver
    gr = GenreVideoGroupResolver().load()
    out: dict[str, str] = {}
    for label, vgs in gr._by_genre.items():
        for v in vgs:
            # store the picker-facing label (e.g. "Crime Drama", "Sub: Sports")
            out[v["id"]] = label if not label.islower() else v["name"].split(":", 2)[-1].strip()
    return out


_CHAN_PREFIX = re.compile(r"^SG: (?:PlutoTV Channels|My5 Channels): [A-Z]{2}: ", re.I)


def _id_to_channel() -> dict[str, str]:
    out: dict[str, str] = {}
    sg_dir = REPO_ROOT / "data" / "site_groups"
    for f in ("synced_site_groups.csv", "synced_my5_site_groups.csv", "seed_site_groups.csv"):
        p = sg_dir / f
        if not p.exists():
            continue
        for row in csv.DictReader(p.open(encoding="utf-8")):
            _id, name = (row.get("id") or "").strip(), (row.get("name") or "").strip()
            if _id and name and "Channels:" in name:
                out.setdefault(_id, _CHAN_PREFIX.sub("", name))
    return out


# --- harvest ---------------------------------------------------------------- #

_TIER_SUFFIX = re.compile(
    r"\s*[-–]\s*(Stream Now|Now Streaming|Tier \d|T\d|\d{1,3}|\(.*?\)|Kids|FAST Channel|UK|USA|CA|AU|BR|GSA|IE|IT|FR|LATAM).*$",
    re.I)

# Region codes appear as the IO-name suffix ("Walker - UK", "Dexter … - USA"), so a
# harvested row can be tagged with its region — titles/channels differ per region.
_REGION_CODES = {"USA", "UK", "CA", "AU", "BR", "GSA", "IE", "IT", "FR", "LATAM",
                 "FI", "DK", "NO", "SE", "ES"}


def _region_from_name(io_name: str) -> str:
    parts = [p.strip() for p in io_name.split(" - ")]
    for p in reversed(parts):
        if p.upper() in _REGION_CODES:
            return p.upper()
    return ""


def _clean_title(io_name: str) -> str:
    """'Walker - Stream Now - 30 (Tier 2) (My5) - UK' -> 'Walker'."""
    name = io_name.split(" - ")[0].strip()
    return name or io_name.strip()


def harvest_io(client, io_id: str, io_name: str, maps: tuple[dict, dict, dict]) -> dict:
    """One IO -> a plan-shaped row by aggregating targeting IDs across ALL its placements
    and reverse-mapping them (shows / genres / channels)."""
    id2show, id2genre, id2chan = maps
    shows: dict[str, None] = {}
    genres: dict[str, None] = {}
    channels: dict[str, None] = {}
    for p in client.list_placements(io_id):
        try:
            d = client._invoke("sh_1_0_show-a-placement", placement_id=int(p["id"]),
                               show="all", content_targeting="true")
        except Exception:
            continue
        body = ((d.get("data") or {}).get("placement")) or {}
        blob = json.dumps(body.get("relationship_targeting") or body.get("content_targeting") or {})
        for _id in set(_ID.findall(blob)):
            if _id in id2show:
                shows.setdefault(id2show[_id])
            elif _id in id2genre:
                genres.setdefault(id2genre[_id])
            elif _id in id2chan:
                channels.setdefault(id2chan[_id])
    return {"promoted_title": _clean_title(io_name), "io_id": io_id, "io_name": io_name,
            "region": _region_from_name(io_name),
            "genres": list(genres), "showlist": list(shows),
            "pluto": {"channels": list(channels)}}


def build_corpus(client, campaign_ids: list[str], out_path: str | Path,
                 max_ios_per_campaign: int = 40, progress=None) -> str:
    """Harvest campaigns' IOs into a JSONL corpus. Skips IOs that yield no targeting
    (empty shells / VD lines).

    RESUMABLE: appends to an existing corpus and skips IOs already harvested (by io_id),
    so a large multi-region sweep can run in several passes — an interruption never loses
    prior progress, and re-running only fills the gaps. Pass progress=print (or any
    callable) for per-campaign logging on long runs.
    """
    maps = (_id_to_show(), _id_to_genre(), _id_to_channel())
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = {str(r.get("io_id")) for r in load_corpus(out)} if out.exists() else set()
    log = progress or (lambda *_: None)
    n = 0
    with out.open("a", encoding="utf-8") as fh:
        for ci, cid in enumerate(campaign_ids, 1):
            try:
                payload = client._invoke("sh_1_1_list-insertion-orders-of-a-campaign",
                                         campaign_id=int(cid), per_page=max_ios_per_campaign, page=1)
                ios = client._rows(payload, "insertion_orders")
            except Exception:
                log(f"[{ci}/{len(campaign_ids)}] campaign {cid}: list failed — skipped")
                continue
            added = 0
            for io in ios[:max_ios_per_campaign]:
                io_id = str(io.get("id"))
                if io_id in seen:
                    continue
                seen.add(io_id)
                row = harvest_io(client, io_id, str(io.get("name", "")), maps)
                if row["showlist"] or row["genres"] or row["pluto"]["channels"]:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
                    n += 1
                    added += 1
            log(f"[{ci}/{len(campaign_ids)}] campaign {cid}: +{added} rows ({n} new this run)")
    return f"{out} ({n} new plans)"


def load_corpus(path: str | Path) -> list[dict]:
    """Read a JSONL corpus (or a folder of *.plan.json) into plan dicts for suggest_history."""
    p = Path(path)
    if p.is_dir():
        from .suggest import load_past_plans
        return load_past_plans(p)
    out: list[dict] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out
