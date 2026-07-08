"""FreeWheel ad-unit resolver.

Ad units are the named inventory assigned to a placement's ad product
(`ad_product.ad_unit_node[].ad_unit_id`). Which units to use mirrors past setups
and the priority-levels doc (see config/ad_units.yaml, keyed by platform group).

Like the country/standard-attribute resolvers, this maps ad-unit NAMES to FW
ad-unit IDs via a CSV table:
  * `FreeWheelClient.sync_ad_units()` writes data/ad_units/synced_ad_units.csv
    from the Ad Unit API v4 (`list-standard-and-custom-ad-units`).
  * A committed seed (data/ad_units/seed_ad_units.csv) makes it work offline.

Matching is by normalized name. Unmatched names are reported, never guessed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audience_segments import normalize_title  # reuse name normalization
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "ad_units"


@dataclass
class AdUnitMatch:
    name: str
    id: Optional[str]
    matched: bool


class AdUnitResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._index: dict[str, str] = {}   # normalized name -> id
        self._loaded = False

    def load(self) -> "AdUnitResolver":
        self._index.clear()
        if self.data_dir.exists():
            for path in sorted(self.data_dir.glob("*.csv")):  # synced_ overrides seed_
                self._load_csv(path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("name") or "").strip()
                _id = (row.get("id") or "").strip()
                if name and _id:
                    self._index[normalize_title(name)] = _id

    def resolve(self, name: str) -> AdUnitMatch:
        if not self._loaded:
            self.load()
        _id = self._index.get(normalize_title(name))
        return AdUnitMatch(name=name, id=_id, matched=_id is not None)

    def resolve_all(self, names: list[str]) -> list[AdUnitMatch]:
        return [self.resolve(n) for n in names]

    def ids_for(self, names: list[str]) -> list[str]:
        return [m.id for m in self.resolve_all(names) if m.id]
