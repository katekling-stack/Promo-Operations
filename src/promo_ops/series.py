"""Show -> FreeWheel Video Series ID resolver (Tier 2 content-affinity showlist).

FreeWheel's series API is searchable by name (standard_attributes/series), but the
right entry is usually the "(ViacomCBS Production)" variant. This resolver reads
synced/seed CSVs (columns: show,id,name) so the offline build/preview can resolve
shows to series IDs without live calls; refresh with the FreeWheel client's
`resolve_series` / a sync step.

Unmatched or ambiguous shows are surfaced, never guessed (e.g. "Marshals" ->
U.S. Marshals vs Marshals: A Yellowstone Story must be picked deliberately).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audience_segments import normalize_title
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "series"


@dataclass
class SeriesMatch:
    show: str
    id: Optional[str]
    name: Optional[str]
    matched: bool


class SeriesResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._by_show: dict[str, tuple[str, str]] = {}
        self._loaded = False

    def load(self) -> "SeriesResolver":
        self._by_show.clear()
        if self.data_dir.exists():
            for path in sorted(self.data_dir.glob("*.csv")):
                with path.open(encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        show = (row.get("show") or "").strip()
                        _id = (row.get("id") or "").strip()
                        if show and _id:
                            self._by_show[normalize_title(show)] = (_id, (row.get("name") or "").strip())
        self._loaded = True
        return self

    def resolve(self, show: str) -> SeriesMatch:
        if not self._loaded:
            self.load()
        hit = self._by_show.get(normalize_title(show))
        if hit:
            return SeriesMatch(show=show, id=hit[0], name=hit[1], matched=True)
        return SeriesMatch(show=show, id=None, name=None, matched=False)

    def resolve_all(self, shows: list[str]) -> list[SeriesMatch]:
        return [self.resolve(s) for s in shows]
