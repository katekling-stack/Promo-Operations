"""Show -> FreeWheel Video Series resolver (Tier 2 "Affinity Shows").

Placement content targeting writes `series` as **Video Series** IDs (the FreeWheel
"Asset Group" namespace — large IDs like 1362684028). This is NOT the
standard-attribute series namespace returned by `liststandardseries` (small IDs
like 3732), which the placement API rejects ("Asset Group item doesn't exist").

The Video Series list (`list-series`, ~229k) has no name filter, so — exactly like
Site Groups — we sync the full index once (FreeWheelClient.sync_series ->
data/series/synced_series.csv) and keyword select-all locally: search the show
name and select every matching series, letting delivery run against whichever are
correct (the team's UI workflow). A committed seed (seed_video_series.csv) covers
the offline/test path.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .audience_segments import normalize_title
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "series"


def _norm_series(name: str) -> str:
    """Normalize a series name for matching, treating '_' as a space.

    Video Series come in both spaced ("MasterChef Australia") and underscored
    ("masterchef_australia") forms — notably the Network 10 / 10 Streaming catalog.
    Folding underscores to spaces makes a single keyword match BOTH variants, so a
    showlist include (Tier 2) and the self-exclusion both catch every spelling.
    """
    return normalize_title(name.replace("_", " "))


@dataclass
class SeriesMatch:
    show: str
    series: list[dict] = field(default_factory=list)   # [{id, name}]

    @property
    def matched(self) -> bool:
        return bool(self.series)


class SeriesResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._rows: list[dict] = []      # [{id, name, norm}]
        self._loaded = False

    def load(self) -> "SeriesResolver":
        self._rows = []
        seen: set[str] = set()
        if self.data_dir.exists():
            for path in sorted(self.data_dir.glob("*.csv")):   # synced_ overrides seed_
                self._load_csv(path, seen)
        self._loaded = True
        return self

    def _load_csv(self, path: Path, seen: set[str]) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                _id = (row.get("id") or "").strip()
                name = (row.get("name") or "").strip()
                if not (_id and name) or _id in seen:
                    continue
                seen.add(_id)
                self._rows.append({"id": _id, "name": name, "norm": _norm_series(name)})

    def resolve(self, show: str, limit: int = 200) -> SeriesMatch:
        """Keyword select-all: every Video Series whose name contains the show."""
        if not self._loaded:
            self.load()
        kw = _norm_series(show)
        if not kw:
            return SeriesMatch(show=show)
        hits = [{"id": r["id"], "name": r["name"]} for r in self._rows if kw in r["norm"]]
        return SeriesMatch(show=show, series=hits[:limit])

    def resolve_exact(self, show: str) -> SeriesMatch:
        """Exact-name match (underscore-folded): only Video Series whose name IS the
        title — used for SELF-EXCLUSION so a promo never blocks unrelated shows that
        merely contain the title words. Catches both "MasterChef Australia" and
        "masterchef_australia", but not "Junior MasterChef Australia"."""
        if not self._loaded:
            self.load()
        kw = _norm_series(show)
        if not kw:
            return SeriesMatch(show=show)
        hits = [{"id": r["id"], "name": r["name"]} for r in self._rows if r["norm"] == kw]
        return SeriesMatch(show=show, series=hits)

    def resolve_all(self, shows: list[str]) -> list[SeriesMatch]:
        return [self.resolve(s) for s in shows]
