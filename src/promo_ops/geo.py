"""FreeWheel geography (country) resolver.

The team targets geography by NAME in the FreeWheel UI — they search "United
States" under Add New Country and select it. The Placement API, however, writes
`geography_targeting.include.country` as a set of numeric FW country IDs.

This resolver bridges the two: a region code (USA) maps to one or more country
NAMES (config/regions.yaml -> `countries`), and each name resolves to its FW
country ID via the country table.

Source of the table: the FreeWheel Standard Attributes taxonomy type
`content_territories` (verified to match the UI's Add-New-Country IDs exactly,
e.g. United States = 165, Canada = 27, Australia = 10, Brazil = 21). It is
exported to CSV by `FreeWheelClient.sync_countries()`; a committed seed CSV
(data/geo/seed_countries.csv) makes resolution work offline.

Matching is by normalized name. Unmatched names are reported, never guessed — a
wrong country ID would mis-target a live placement.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audience_segments import normalize_title  # reuse name normalization
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "geo"


@dataclass
class CountryMatch:
    name: str
    id: Optional[str]
    matched: bool


class CountryResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._index: dict[str, str] = {}   # normalized country name -> id
        self._loaded = False

    def load(self) -> "CountryResolver":
        self._index.clear()
        if self.data_dir.exists():
            # synced_ (live refresh) wins over seed_ when both are present.
            for path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("country_name") or row.get("name") or "").strip()
                _id = (row.get("id") or "").strip()
                if name and _id:
                    self._index[normalize_title(name)] = _id

    def resolve(self, name: str) -> CountryMatch:
        if not self._loaded:
            self.load()
        _id = self._index.get(normalize_title(name))
        return CountryMatch(name=name, id=_id, matched=_id is not None)

    def resolve_all(self, names: list[str]) -> list[CountryMatch]:
        return [self.resolve(n) for n in names]

    def ids_for(self, names: list[str]) -> list[str]:
        """Resolved FW country IDs for a list of names (unmatched dropped)."""
        return [m.id for m in self.resolve_all(names) if m.id]
