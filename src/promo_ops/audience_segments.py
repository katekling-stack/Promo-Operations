"""Tier-1 audience segment resolver.

Maps a show title to its FreeWheel audience segment(s), using the "Audience
Segments - Promo Operations" spreadsheet as the source of truth. That sheet lists,
per show/genre/platform, the FreeWheel audience naming convention and (where
available) the numeric Segment ID.

Design principles:
  * The resolver reads *synced* CSV snapshots under data/audience_segments/. Each
    row is normalized to: show, segment_name, segment_id, platform, region, source.
  * Matching is by normalized title. If a show is not found, it is returned as
    UNRESOLVED — never guessed. A fabricated segment ID could mis-target a live
    campaign, so unresolved shows are surfaced so an operator can request/add the
    segment (mirroring the sheet's own "Available in FW (Y/N)" workflow).
  * `sync_from_sheet()` (see integrations/gsheets.py) refreshes the CSV snapshots
    from the live Google Sheet across all tabs.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "audience_segments"


def normalize_title(title: str) -> str:
    """Normalize a title for matching: lowercase, strip punctuation/whitespace."""
    title = title.lower().strip()
    title = re.sub(r"[:\-–&,'!\.]", " ", title)   # drop common punctuation
    title = re.sub(r"\s+", " ", title)
    return title.strip()


@dataclass
class SegmentRecord:
    show: str
    segment_name: str
    segment_id: Optional[str] = None
    platform: Optional[str] = None
    region: Optional[str] = None
    source: Optional[str] = None


@dataclass
class SegmentMatch:
    show: str
    matched: bool
    records: list[SegmentRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "show": self.show,
            "matched": self.matched,
            "segments": [
                {
                    "segment_name": r.segment_name,
                    "segment_id": r.segment_id,
                    "platform": r.platform,
                    "region": r.region,
                    "source": r.source,
                }
                for r in self.records
            ],
        }


class AudienceSegmentResolver:
    """Loads synced segment CSVs and resolves show titles to segments."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._by_title: dict[str, list[SegmentRecord]] = {}
        self._loaded = False

    def load(self) -> "AudienceSegmentResolver":
        """Load all *.csv snapshots in the data dir into the title index."""
        self._by_title.clear()
        if self.data_dir.exists():
            for csv_path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(csv_path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                show = (row.get("show") or "").strip()
                seg_name = (row.get("segment_name") or "").strip()
                if not show or not seg_name or show.upper() == "N/A":
                    continue
                rec = SegmentRecord(
                    show=show,
                    segment_name=seg_name,
                    segment_id=(row.get("segment_id") or "").strip() or None,
                    platform=(row.get("platform") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    source=(row.get("source") or path.stem).strip() or None,
                )
                self._by_title.setdefault(normalize_title(show), []).append(rec)

    def resolve(self, show: str, region: Optional[str] = None) -> SegmentMatch:
        if not self._loaded:
            self.load()
        recs = self._by_title.get(normalize_title(show), [])
        if region:
            region_recs = [r for r in recs if not r.region or r.region == region]
            recs = region_recs or recs   # fall back to region-agnostic matches
        return SegmentMatch(show=show, matched=bool(recs), records=recs)

    def resolve_all(self, shows: list[str], region: Optional[str] = None) -> list[SegmentMatch]:
        return [self.resolve(s, region) for s in shows]
