"""Content-rating restriction resolver.

Rating restrictions are done via FreeWheel Video Groups named
"VG: Content Rating: {REGION}: {RATING}" (e.g. "VG: Content Rating: US: TV-MA",
"VG: Content Rating: GSA: 16", "VG: Content Rating: UK: 18"). The REGION token is our
region *code* (US/UK/GSA/LATAM/AU/CA/FR/IT/ES/FI/DK/NO/SE/BR), so a campaign resolves its
own market's ratings directly.

A CM selects which rating(s) to EXCLUDE; the selected VGs are excluded on every placement
in the order (content_targeting.network_items.exclude.video_group). Synced once from
FreeWheel -> data/video_groups/synced_content_rating_video_groups.csv.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "video_groups"
PREFIX = "VG: Content Rating: "
_FILE = "synced_content_rating_video_groups.csv"


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


class RatingRestrictionResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._by_region: dict[str, dict[str, str]] = {}    # region -> {norm_rating: vg_id}
        self._labels: dict[str, list[str]] = {}            # region -> [rating label, ...]
        self._loaded = False

    def load(self) -> "RatingRestrictionResolver":
        path = self.data_dir / _FILE
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    if (row.get("status") or "").strip() != "ACTIVE":
                        continue
                    name = (row.get("name") or "").strip()
                    if not name.startswith(PREFIX) or "[IA]" in name:
                        continue
                    body = name[len(PREFIX):]
                    region, sep, rating = body.partition(":")
                    region, rating = region.strip(), rating.strip()
                    if not sep or not region or not rating:
                        continue
                    self._by_region.setdefault(region, {})[_norm(rating)] = str(row.get("id"))
                    self._labels.setdefault(region, []).append(rating)
        self._loaded = True
        return self

    def _ensure(self):
        if not self._loaded:
            self.load()

    def ratings_for(self, region_code: str) -> list[str]:
        """Top-level rating labels for a region code (the sub-descriptor variants like
        'TV-MA: V' are hidden from the picker), sorted."""
        self._ensure()
        labels = {r for r in self._labels.get(region_code, []) if ":" not in r}
        return sorted(labels, key=str.lower)

    def resolve(self, region_code: str, ratings: list[str]) -> list[str]:
        """Selected rating labels -> VG ids for the region (exact, normalized match).
        Numeric entries are treated as raw VG ids and passed through (back-compat)."""
        self._ensure()
        table = self._by_region.get(region_code, {})
        out: list[str] = []
        for r in ratings or []:
            r = str(r).strip()
            if not r:
                continue
            if r.isdigit():                       # already a VG id
                out.append(r)
                continue
            vg = table.get(_norm(r))
            if vg and vg not in out:
                out.append(vg)
        return out

    def regions(self) -> list[str]:
        self._ensure()
        return sorted(self._by_region)
