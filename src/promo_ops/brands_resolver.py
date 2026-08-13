"""Brand resolver — the IO-level FreeWheel Brand a CM picks for a campaign.

Brands are synced per advertiser/region (scripts/sync_brands.py ->
data/brands/synced_brands.csv). The form offers the region's brands by name; the engine
resolves the picked name to its FreeWheel brand_id and stamps it on the Insertion Order.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .config import REPO_ROOT

DATA_FILE = REPO_ROOT / "data" / "brands" / "synced_brands.csv"


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


class BrandResolver:
    def __init__(self, data_file: Path = DATA_FILE):
        self.data_file = Path(data_file)
        # region -> list[(brand_name, brand_id)]  and  region -> {norm_name: brand_id}
        self._by_region: dict[str, list[tuple[str, str]]] = {}
        self._index: dict[str, dict[str, str]] = {}
        self._loaded = False

    def load(self) -> "BrandResolver":
        if self.data_file.exists():
            with open(self.data_file, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    region = (row.get("region") or "").strip()
                    name = (row.get("brand_name") or "").strip()
                    bid = (row.get("brand_id") or "").strip()
                    if not region or not name or not bid:
                        continue
                    self._by_region.setdefault(region, []).append((name, bid))
                    self._index.setdefault(region, {})[_norm(name)] = bid
        self._loaded = True
        return self

    def _ensure(self):
        if not self._loaded:
            self.load()

    def brands_for(self, region: str) -> list[str]:
        """Distinct brand names available for a region, sorted."""
        self._ensure()
        return sorted({n for n, _ in self._by_region.get(region, [])}, key=str.lower)

    def resolve(self, region: str, name_or_id: str) -> str | None:
        """A picked brand name (or a raw numeric brand_id) -> brand_id for the region."""
        self._ensure()
        val = str(name_or_id or "").strip()
        if not val:
            return None
        if val.isdigit():
            return val
        return self._index.get(region, {}).get(_norm(val))

    def regions(self) -> list[str]:
        self._ensure()
        return sorted(self._by_region)
