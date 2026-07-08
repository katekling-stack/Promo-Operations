"""FreeWheel Standard Attribute resolver.

Maps plain input names (genre, network/brand, Pluto category/channel, device) to
FreeWheel Standard Attribute IDs, which content/platform targeting requires.

Same design as the audience-segment resolver:
  * Reads synced/seed CSVs under data/standard_attributes/ (columns: type,name,id).
  * `sync_standard_attributes()` (FreeWheel client) refreshes them from the live
    /services/v4/standard_attributes API (types: genres, brands, channels,
    programmers, device_types, content_territories, ...).
  * Matching is by normalized name within a type. Unmatched names are reported,
    never guessed — a wrong ID would mis-target a live placement.

Note: specific SHOWS/series are NOT standard attributes; they resolve to FW
series/video IDs via content lookup (Site API) and are handled separately.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .audience_segments import normalize_title  # reuse name normalization
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "standard_attributes"

# Which Standard Attribute `type` each tier dimension resolves against.
DIMENSION_ATTRIBUTE_TYPE = {
    "genre": "genres",
    "network": "brands",            # e.g. "Paramount Network"
    "pluto_category": "channels",   # Pluto category/channel standard attributes
    "pluto_channel_list": "channels",
    "pluto_channel": "channels",
    "endpoints": "device_types",
}


@dataclass
class AttributeMatch:
    name: str
    type: str
    id: Optional[str]
    matched: bool


class StandardAttributeResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        # index[type][normalized_name] = id
        self._index: dict[str, dict[str, str]] = {}
        self._loaded = False

    def load(self) -> "StandardAttributeResolver":
        self._index.clear()
        if self.data_dir.exists():
            for path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                typ = (row.get("type") or "").strip()
                name = (row.get("name") or "").strip()
                _id = (row.get("id") or "").strip()
                if typ and name and _id:
                    self._index.setdefault(typ, {})[normalize_title(name)] = _id

    def resolve(self, name: str, attr_type: str) -> AttributeMatch:
        if not self._loaded:
            self.load()
        _id = self._index.get(attr_type, {}).get(normalize_title(name))
        return AttributeMatch(name=name, type=attr_type, id=_id, matched=_id is not None)

    def resolve_dimension(self, dimension_key: str, values: list[str]) -> list[AttributeMatch]:
        attr_type = DIMENSION_ATTRIBUTE_TYPE.get(dimension_key)
        if not attr_type:
            return []
        return [self.resolve(v, attr_type) for v in values]
