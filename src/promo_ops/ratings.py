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
import re
from pathlib import Path

from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "video_groups"
PREFIX = "VG: Content Rating: "
_FILE = "synced_content_rating_video_groups.csv"

# Some markets have no rating VGs of their own and share another market's. Ireland (IE) uses
# the same UK/BBFC classification, so its ratings resolve against the UK Content Rating VGs.
_REGION_ALIAS = {"IE": "UK"}

# A real FreeWheel Video Group id is a long integer; a rating LABEL that happens to be all
# digits ("15", "18", "12") is only 1-2 chars. The raw-id passthrough (AU supplies VG ids
# directly) must accept only the former, never mistake a short rating label for an id.
_MIN_RAW_VG_ID_LEN = 5


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


def _family_key(rating: str) -> tuple:
    """Group a rating with its age-family: '6', '6: AS', 'A6', 'A6: VD' all share
    ('age','6'), so excluding '6' pulls in every 6-level variant. Non-numeric ratings key
    by their base name, so 'L'/'L: NA' group together but stay distinct from 'AL'."""
    base = str(rating).split(":", 1)[0].strip()
    m = re.fullmatch(r"A?(\d+)", base)
    return ("age", m.group(1)) if m else ("name", _norm(base))


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
        region_code = _REGION_ALIAS.get(region_code, region_code)
        labels = {r for r in self._labels.get(region_code, []) if ":" not in r}
        return sorted(labels, key=str.lower)

    def resolve(self, region_code: str, ratings: list[str]) -> list[str]:
        """Selected rating labels -> the region's VG ids, EXPANDED to the full age-family
        (e.g. '6' -> 6, 6: AS, A6: VD, …) so one pick excludes every variant of that rating.
        A LONG all-digit value passes through as a raw VG id (back-compat with the AU flow
        that supplies ids directly); a short numeric like '6' is a rating and is resolved."""
        self._ensure()
        region_code = _REGION_ALIAS.get(region_code, region_code)   # e.g. IE -> UK
        table = self._by_region.get(region_code, {})
        labels = self._labels.get(region_code, [])
        out: list[str] = []
        seen: set[str] = set()

        def add(vg: str | None) -> None:
            if vg and vg not in seen:
                seen.add(vg)
                out.append(vg)

        for r in ratings or []:
            r = str(r).strip()
            if not r:
                continue
            key = _family_key(r)
            matched = False
            for lab in labels:                    # expand to the whole age-family
                if _family_key(lab) == key:
                    vg = table.get(_norm(lab))
                    if vg:
                        add(vg)
                        matched = True
            # A numeric that isn't a known rating: pass through ONLY if it's long enough to be
            # a real VG id (AU supplies ids directly). A short label like "15"/"18" is a rating,
            # not an id — dropping it (rather than emitting a bogus VG id) avoids a 422.
            if not matched and r.isdigit() and len(r) >= _MIN_RAW_VG_ID_LEN:
                add(r)
        return out

    def regions(self) -> list[str]:
        self._ensure()
        return sorted(self._by_region)
