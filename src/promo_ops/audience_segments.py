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


def _dda_tokens(text: str) -> str:
    """Normalize a DDA segment name / show to space-separated alphanumeric tokens.

    Collapses ALL separators (- _ : etc.) so the inconsistent DDA conventions all
    reduce to the same tokens: 'GL-DDA-1P-SHOW_Tulsa_King', 'GL-DDA-1P-SHOW-FBI'
    and 'GL-DDA-1P_FBI_-_International' -> '... show tulsa king' / '... fbi ...'.
    Drops the connector word 'and' so '& ' and 'and' match ("Tony & Ziva" ==
    "Tony and Ziva").
    """
    toks = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return " ".join(t for t in toks if t != "and")


class AudienceSegmentResolver:
    """Loads synced DDA segment CSVs and resolves show titles to segments.

    Matching mirrors the team's workflow — "search DDA + the show name and select
    everything" — via a normalized substring match, so it is robust to the
    inconsistent DDA naming (SHOW_ vs SHOW- vs no SHOW).
    """

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._records: list[SegmentRecord] = []   # all GL-DDA-1P records
        self._norm: list[str] = []                # parallel normalized names
        self._loaded = False

    def load(self) -> "AudienceSegmentResolver":
        self._records, self._norm = [], []
        if self.data_dir.exists():
            for csv_path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(csv_path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                seg_name = (row.get("segment_name") or "").strip()
                # DDA ONLY. AAM segments are sunset and must never be targeted.
                if not seg_name or not seg_name.upper().startswith("GL-DDA-1P"):
                    continue
                self._records.append(SegmentRecord(
                    show=(row.get("show") or "").strip(),
                    segment_name=seg_name,
                    segment_id=(row.get("segment_id") or "").strip() or None,
                    platform=(row.get("platform") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    source=(row.get("source") or path.stem).strip() or None,
                ))
                self._norm.append(_dda_tokens(seg_name))

    def resolve(self, show: str, region: Optional[str] = None) -> SegmentMatch:
        """Select-all: every GL-DDA-1P segment whose name contains the show tokens."""
        if not self._loaded:
            self.load()
        kw = _dda_tokens(show)
        if not kw:
            return SegmentMatch(show=show, matched=False)
        # word-boundary token match so "FBI" doesn't hit inside another word
        pat = re.compile(rf"(?:^| ){re.escape(kw)}(?: |$)")
        recs = [r for r, n in zip(self._records, self._norm) if pat.search(n)]
        return SegmentMatch(show=show, matched=bool(recs), records=recs)

    def resolve_all(self, shows: list[str], region: Optional[str] = None) -> list[SegmentMatch]:
        return [self.resolve(s, region) for s in shows]
