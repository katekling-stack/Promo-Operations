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


# Tier-1 audience-segment naming conventions, in _dda_tokens (normalized) form. The
# resolver keeps only segments matching a known convention, and each region resolves
# against ITS convention. The global default is the GL-DDA-1P DDA convention; AU uses
# the DWH "Summit" segments instead ("AU - DWH - <src> - ID - Summit - ..." — never the
# GL-DDA-1P ones).
DEFAULT_TIER1_CONVENTION = "gl dda 1p"
TIER1_CONVENTIONS: dict[str, str] = {
    "AU": "au dwh",
}

# The Audience Segment Request tool (v3) stamps NEW segments with a region-bucketed prefix
# (US-/EU/UK-/APAC-DDA-1P-SERIES|MOVIE-<Title>), rolling out alongside the legacy GL-DDA-1P
# SHOW set. So each region matches BOTH its legacy convention AND its new bucket convention.
REGION_BUCKET_CONVENTION: dict[str, str] = {
    "USA": "us dda 1p", "CA": "us dda 1p", "BR": "us dda 1p", "LATAM": "us dda 1p",
    "AU": "apac dda 1p",
    "UK": "eu uk dda 1p", "IE": "eu uk dda 1p", "FR": "eu uk dda 1p", "IT": "eu uk dda 1p",
    "GSA": "eu uk dda 1p", "ES": "eu uk dda 1p", "FI": "eu uk dda 1p", "DK": "eu uk dda 1p",
    "NO": "eu uk dda 1p", "SE": "eu uk dda 1p",
}
ALL_BUCKET_CONVENTIONS = ["us dda 1p", "eu uk dda 1p", "apac dda 1p"]


def _conventions_for_region(region: Optional[str]) -> list[str]:
    """Conventions a region's Tier 1 segments may use: its legacy convention (GL, or AU DWH)
    PLUS its new request-tool bucket convention, so old and new segments both resolve."""
    r = (region or "").upper()
    out = [TIER1_CONVENTIONS.get(r, DEFAULT_TIER1_CONVENTION)]
    b = REGION_BUCKET_CONVENTION.get(r)
    if b and b not in out:
        out.append(b)
    return out


def dda_request_name(show: str) -> str:
    """Canonical DDA segment name to request for a show (matches the GL-DDA-1P-SHOW
    convention, spaces -> underscores): 'Tulsa King' -> 'GL-DDA-1P-SHOW-Tulsa_King'."""
    return "GL-DDA-1P-SHOW-" + re.sub(r"\s+", "_", (show or "").strip())


# --- alignment with the Audience Segment Request tool (Apps Script) ---------- #
# The request form groups markets into three region buckets and stamps a region prefix.
TOOL_REGION_BUCKET = {
    "USA": "Americas", "CA": "Americas", "BR": "Americas", "LATAM": "Americas",
    "AU": "APAC",
    "UK": "EU/UK", "IE": "EU/UK", "FR": "EU/UK", "IT": "EU/UK", "GSA": "EU/UK",
    "ES": "EU/UK", "FI": "EU/UK", "DK": "EU/UK", "NO": "EU/UK", "SE": "EU/UK",
}
TOOL_REGION_PREFIX = {"Americas": "US-DDA-1P", "APAC": "APAC-DDA-1P", "EU/UK": "EU/UK-DDA-1P"}


# Map our genres -> the request tool's genre TAB (required field). Best-guess; CM can override.
_GENRE_TAB_GUESS = {
    "crime": "Crime", "true crime": "Crime", "drama": "Drama/Action", "action": "Drama/Action",
    "adventure": "Drama/Action", "thriller": "Horror/Thriller", "suspense": "Horror/Thriller",
    "horror": "Horror/Thriller", "mystery": "Crime", "comedy": "Comedy/Sitcom",
    "sitcom": "Comedy/Sitcom", "sports": "Sports", "reality": "Reality", "anime": "Anime/Gaming",
    "gaming": "Anime/Gaming", "sci-fi": "Sci-Fi/Fantasy", "science fiction": "Sci-Fi/Fantasy",
    "fantasy": "Sci-Fi/Fantasy", "romance": "Romance", "news": "News/Documentary",
    "documentary": "News/Documentary", "western": "Western", "music": "Music",
    "kids": "Family/Young Adult", "family": "Family/Young Adult", "food": "Food/Home",
    "home": "Food/Home", "classic": "Classic TV", "bet": "BET/African American",
}


def guess_genre_tab(genres: list[str]) -> str:
    """Best-guess the request tool's genre TAB from a plan's genres (first match wins)."""
    for g in genres or []:
        gl = (g or "").lower()
        for key, tab in _GENRE_TAB_GUESS.items():
            if key in gl:
                return tab
    return ""


def tool_request(show: str, region: str, content_type: str = "show",
                 io: str = "", requester: str = "") -> dict:
    """Build the exact payload the Audience Segment Request tool expects for one show, so a
    request is paste-ready (or POST-ready if the Apps Script adds a doPost). The tool
    generates its own name as {region-prefix}-{SERIES|MOVIE}-{Title_}."""
    bucket = TOOL_REGION_BUCKET.get((region or "").upper(), "Americas")
    typ = "Movie" if str(content_type).lower() == "movie" else "Series"
    slug = re.sub(r"\s+", "_", (show or "").strip())
    gen = f"{TOOL_REGION_PREFIX[bucket]}-{typ.upper()}-{slug}"
    return {"type": typ, "region": bucket, "title": show, "io": io,
            "action": "Include", "requester": requester, "generated_name": gen}


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
        self._records: list[SegmentRecord] = []   # Tier-1 convention records
        self._norm: list[str] = []                # parallel normalized names
        self._conv: list[str] = []                # parallel matched convention prefix
        self._loaded = False

    def _conventions(self) -> list[str]:
        return [DEFAULT_TIER1_CONVENTION, *TIER1_CONVENTIONS.values(), *ALL_BUCKET_CONVENTIONS]

    def load(self) -> "AudienceSegmentResolver":
        self._records, self._norm, self._conv = [], [], []
        if self.data_dir.exists():
            for csv_path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(csv_path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        conventions = self._conventions()
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                seg_name = (row.get("segment_name") or "").strip()
                # Skip deactivated segments — the name carries a "deactivated" marker and
                # targeting one would deliver nothing.
                if not seg_name or "deactivated" in seg_name.lower():
                    continue
                norm = _dda_tokens(seg_name)
                # Keep DDA/Summit segments matching a known Tier-1 convention only. AAM
                # (and other) segments are sunset and must never be targeted.
                conv = next((c for c in conventions if norm.startswith(c)), None)
                if conv is None:
                    continue
                self._records.append(SegmentRecord(
                    show=(row.get("show") or "").strip(),
                    segment_name=seg_name,
                    segment_id=(row.get("segment_id") or "").strip() or None,
                    platform=(row.get("platform") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    source=(row.get("source") or path.stem).strip() or None,
                ))
                self._norm.append(norm)
                self._conv.append(conv)

    def resolve(self, show: str, region: Optional[str] = None) -> SegmentMatch:
        """Select-all: every Tier-1 segment (in the REGION's convention) whose name
        contains the show tokens. AU resolves the DWH Summit segments; all other regions
        the global GL-DDA-1P DDA segments."""
        if not self._loaded:
            self.load()
        kw = _dda_tokens(show)
        if not kw:
            return SegmentMatch(show=show, matched=False)
        want_conv = _conventions_for_region(region)
        # word-boundary token match so "FBI" doesn't hit inside another word
        pat = re.compile(rf"(?:^| ){re.escape(kw)}(?: |$)")
        recs = [r for r, n, c in zip(self._records, self._norm, self._conv)
                if c in want_conv and pat.search(n)]
        return SegmentMatch(show=show, matched=bool(recs), records=recs)

    def resolve_exact(self, show: str, region: Optional[str] = None) -> SegmentMatch:
        """Only the segment(s) that ARE exactly this title — the SHOW-name portion of the
        segment (after the convention prefix + an optional "SHOW" token) must equal the
        query exactly. So "CSI Miami" matches "…SHOW-CSI_Miami" but NOT "…SHOW-NCIS_Hawaii"
        (suffix extra) or "…SHOW-The_Real_CSI_Miami" (prefix extra). Used for self-exclusion,
        where we must exclude the exact title only — never the wider franchise family."""
        m = self.resolve(show, region)
        if not m.matched:
            return m
        kw = _dda_tokens(show)
        want = _conventions_for_region(region)
        drop = {"show", "series", "movie"}   # the type token after the convention prefix

        def show_portion(seg_name: str) -> str:
            n = _dda_tokens(seg_name)
            for conv in want:
                if n.startswith(conv):
                    parts = n[len(conv):].split()
                    while parts and parts[0] in drop:
                        parts = parts[1:]
                    return " ".join(parts)
            return n

        recs = []
        for r in m.records:
            n = _dda_tokens(r.segment_name)
            # AU DWH naming isn't "<conv> <type> <title>", so keep the trailing-title match.
            if n.startswith("au dwh"):
                if n == kw or n.endswith(" " + kw):
                    recs.append(r)
            elif show_portion(r.segment_name) == kw:
                recs.append(r)
        return SegmentMatch(show=show, matched=bool(recs), records=recs)

    def resolve_all(self, shows: list[str], region: Optional[str] = None) -> list[SegmentMatch]:
        return [self.resolve(s, region) for s in shows]

    def resolve_all_exact(self, shows: list[str], region: Optional[str] = None) -> list[SegmentMatch]:
        """Exact per show — each showlist entry resolves to ONLY its own segment(s), never
        the wider franchise family (so 'CSI Miami' does not pull in 'The Real CSI Miami')."""
        return [self.resolve_exact(s, region) for s in shows]

    def missing_dda(self, shows: list[str], region: Optional[str] = None
                    ) -> tuple[list[dict], list[dict]]:
        """Split a showlist into (have_dda, needs_request). A show HAS a DDA segment when an
        exact-match segment with a real FreeWheel id exists; otherwise it needs a new segment
        requested. Returns request-ready rows: {'show', 'request_name'} for the missing ones
        (canonical GL-DDA-1P name), and {'show', 'segment_id'} for the ones we already have."""
        if not self._loaded:
            self.load()
        have: list[dict] = []
        need: list[dict] = []
        seen: set[str] = set()
        for s in shows:
            key = (s or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            m = self.resolve_exact(s, region)
            sid = next((r.segment_id for r in m.records if r.segment_id), None)
            if sid:
                have.append({"show": s, "segment_id": sid})
            else:
                need.append({"show": s, "request_name": dda_request_name(s)})
        return have, need

    def id_for_segment_name(self, name: str) -> list[str]:
        """Resolve an EXISTING segment picked by its exact name (from the audience
        picklist) to its FreeWheel audience-item id(s) — used to EXCLUDE a specific
        segment on every placement. Exact, case-insensitive match on the segment name."""
        if not self._loaded:
            self.load()
        want = (name or "").strip().lower()
        if not want:
            return []
        ids = [r.segment_id for r in self._records
               if r.segment_id and r.segment_name.strip().lower() == want]
        return list(dict.fromkeys(ids))
