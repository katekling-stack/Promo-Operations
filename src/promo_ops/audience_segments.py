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
# resolver keeps only segments matching a known convention. Every region resolves against
# the GLOBAL GL-DDA-1P convention FIRST (use the regular segment when a show/movie has one),
# PLUS any region-specific conventions: AU also matches its DWH "Summit" segments
# ("AU - DWH - <src> - ID - Summit - …"), and every region matches its new request-tool bucket.
DEFAULT_TIER1_CONVENTION = "gl dda 1p"
TIER1_CONVENTIONS: dict[str, str] = {
    "AU": "au dwh",
}

# The Audience Segment Request tool (v3) stamps NEW segments with a region-bucketed prefix
# (US-/EU/UK-/APAC-DDA-1P-SERIES|MOVIE-<Title>), rolling out alongside the legacy GL-DDA-1P
# SHOW set. A segment requested under one region's bucket is commonly reusable for a
# campaign in a different region too, so every region matches ALL THREE buckets (plus its
# own legacy convention, if any) rather than just the bucket it would have requested under.
ALL_BUCKET_CONVENTIONS = ["us dda 1p", "eu uk dda 1p", "apac dda 1p"]

# Which request-tool bucket is a region's OWN (the one a new segment for that market is
# requested under). Used only to PREFER the region-specific segment when targeting.
REGION_BUCKET_CONVENTION: dict[str, str] = {
    "USA": "us dda 1p", "CA": "us dda 1p", "BR": "us dda 1p", "LATAM": "us dda 1p",
    "AU": "apac dda 1p",
    "UK": "eu uk dda 1p", "IE": "eu uk dda 1p", "FR": "eu uk dda 1p", "IT": "eu uk dda 1p",
    "GSA": "eu uk dda 1p", "ES": "eu uk dda 1p", "FI": "eu uk dda 1p", "DK": "eu uk dda 1p",
    "NO": "eu uk dda 1p", "SE": "eu uk dda 1p",
}


def _segment_rank(norm: str, region: Optional[str], streaming10: bool) -> Optional[int]:
    """Whether (and how well) a Tier 1 segment fits a campaign's region for INCLUDE targeting
    (lower wins; None = never used for this line). REGION-ONLY policy: a segment is used only
    if it carries the campaign's own region --
      0  AU "AU - DWH - 10 - ..." Network 10 Summit segments -- (10 Streaming) lines only
      1  the region's OWN segments: its request-tool bucket (US-/EU-UK-/APAC-DDA-1P) and, for
         AU, the non-Network-10 DWH Summit segments (PP, ...)
    The standard GL-DDA-1P segments and other regions' buckets are NOT used. (A region we have
    no own bucket for keeps the old behavior: GL = 2, another bucket = 3.)"""
    r = (region or "").upper()
    if norm.startswith("au dwh"):
        if r != "AU":
            return None                              # AU Summit never leaks to other regions
        if norm.split()[:3] == ["au", "dwh", "10"]:
            return 0 if streaming10 else None
        return 1
    own = REGION_BUCKET_CONVENTION.get(r)
    if own and norm.startswith(own):
        return 1
    if own:
        return None                                  # region-only: no GL / other-region segment
    if norm.startswith(DEFAULT_TIER1_CONVENTION):
        return 2
    return 3


def _au_content_title(norm: str) -> str:
    """The title inside an AU Summit content segment -- "au dwh <src> id summit content
    <title> watchers apac" -> "<title>" -- or "" when the name isn't that shape. These names
    never END with the bare title, so the generic trailing-title rule can't match them."""
    toks = norm.split()
    if "content" not in toks:
        return ""
    rest = toks[toks.index("content") + 1:]
    if rest[-2:] == ["watchers", "apac"]:
        rest = rest[:-2]
    elif rest[-1:] == ["watchers"]:
        rest = rest[:-1]
    return " ".join(rest)


# Segment "families" -- which naming convention a segment belongs to. The coverage rule below
# works on these, and the campaign form gets the same codes, so the builder's alert, the
# `promo-ops dda` list and the form's flag can never disagree.
FAMILY_LABEL = {"gl": "GL-DDA-1P", "us": "US-DDA-1P", "eu": "EU/UK-DDA-1P", "apac": "APAC-DDA-1P"}
_BUCKET_FAMILY = {"us dda 1p": "us", "eu uk dda 1p": "eu", "apac dda 1p": "apac"}
_FALLBACK_ORDER = ("gl", "us", "eu", "apac")      # standard first, then another region's bucket


# What can wrap a show's title inside a segment name, none of which is part of the title:
# a type marker after the prefix (SHOW / SERIES / MOVIE / INTL) and, in the request-tool
# buckets, the region code the tool appends ("..._eu", "..._au", "..._us").
_TITLE_MARKERS = {"show", "series", "movie", "intl"}
_BUCKET_REGION_CODE = {"us dda 1p": "us", "eu uk dda 1p": "eu", "apac dda 1p": "au"}


def _show_portion(norm: str, conv: str) -> str:
    """The title inside a (non-AU-Summit) segment name: after the convention prefix, with the
    leading type markers and the bucket's trailing region code removed.
    "eu uk dda 1p series the yorkshire vet eu" -> "the yorkshire vet"."""
    parts = norm[len(conv):].split()
    while parts and parts[0] in _TITLE_MARKERS:
        parts = parts[1:]
    code = _BUCKET_REGION_CODE.get(conv)
    if code and len(parts) > 1 and parts[-1] == code:
        parts = parts[:-1]
    return " ".join(parts)


def _family_of(norm: str) -> Optional[str]:
    """gl | us | eu | apac | au (AU Summit PP etc.) | au_10 (AU Summit Network 10), or None."""
    if norm.startswith("au dwh"):
        return "au_10" if norm.split()[:3] == ["au", "dwh", "10"] else "au"
    for prefix, fam in (("gl dda 1p", "gl"), ("us dda 1p", "us"),
                        ("eu uk dda 1p", "eu"), ("apac dda 1p", "apac")):
        if norm.startswith(prefix):
            return fam
    return None


def region_bucket_family(region: Optional[str]) -> Optional[str]:
    """The family of a region's OWN request-tool bucket (us/eu/apac), or None if unmapped."""
    return _BUCKET_FAMILY.get(REGION_BUCKET_CONVENTION.get((region or "").upper(), ""))


def region_own_label(region: Optional[str]) -> str:
    """Human label for what counts as the region's own segment (for alerts)."""
    fam = region_bucket_family(region)
    label = FAMILY_LABEL.get(fam, "")
    if (region or "").upper() == "AU":
        return f"{label} or AU Summit"
    return label


def classify_families(fams, region: Optional[str]) -> tuple[str, Optional[str]]:
    """The single Tier 1 coverage rule for ONE show, given the families that have a segment for
    it. REGION-ONLY policy: only the campaign's own region's segments are ever targeted.
    Returns (kind, label):
      ("own", None)         the region's own segment exists -> it is used
      ("elsewhere", label)  a segment exists ONLY outside the region (the standard GL-DDA-1P or
                            another region's bucket; label says which) -> NOT used; a regional
                            one has to be requested
      ("none", None)        no segment anywhere -> one has to be requested
    AU Summit segments only count for AU; the Network 10 ones only ever serve (10 Streaming)
    lines, so they never count here. A region we don't know the own bucket of never alerts."""
    r = (region or "").upper()
    usable = set(fams or ())
    usable.discard("au_10")
    if r != "AU":
        usable.discard("au")
    if not usable:
        return ("none", None)
    own = region_bucket_family(r)
    if own is None:
        return ("own", None)
    if own in usable or (r == "AU" and "au" in usable):
        return ("own", None)
    for fam in _FALLBACK_ORDER:
        if fam in usable:
            return ("elsewhere", FAMILY_LABEL[fam])
    return ("none", None)


def segment_family(segment_name: str) -> Optional[str]:
    """The family (gl/us/eu/apac/au/au_10) a segment NAME belongs to, or None."""
    return _family_of(_dda_tokens(segment_name))


def is_region_segment(segment_name: str, region: Optional[str]) -> bool:
    """True when a segment carries the campaign's own region (region-only policy)."""
    fam = segment_family(segment_name)
    return bool(fam) and classify_families({fam}, region)[0] == "own"


def _conventions_for_region(region: Optional[str]) -> list[str]:
    """Conventions a region's Tier 1 segments may use: the GLOBAL GL-DDA-1P convention,
    EVERY Audience Segment Request tool (v3) bucket (US-/EU-UK-/APAC-DDA-1P) regardless of
    the campaign's own region — a segment requested under one region's bucket is commonly
    reusable for a campaign in a different region too, so narrowing to just the query
    region's own bucket silently hid usable overlap — PLUS the region's own region-specific
    LEGACY convention if it has one (e.g. AU's DWH "Summit" segments, which are AU's own
    data warehouse and do NOT carry over to other regions)."""
    r = (region or "").upper()
    out = [DEFAULT_TIER1_CONVENTION, *ALL_BUCKET_CONVENTIONS]
    legacy = TIER1_CONVENTIONS.get(r)
    if legacy and legacy not in out:
        out.append(legacy)
    return out




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

    def resolve_exact(self, show: str, region: Optional[str] = None,
                      prefer_region: bool = False, streaming10: bool = False) -> SegmentMatch:
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
        def show_portion(seg_name: str) -> str:
            n = _dda_tokens(seg_name)
            for conv in want:
                if n.startswith(conv):
                    return _show_portion(n, conv)
            return n

        recs = []
        for r in m.records:
            n = _dda_tokens(r.segment_name)
            # AU DWH naming isn't "<conv> <type> <title>", so keep the trailing-title match.
            if n.startswith("au dwh"):
                if n == kw or n.endswith(" " + kw) or _au_content_title(n) == kw:
                    recs.append(r)
            elif show_portion(r.segment_name) == kw:
                recs.append(r)
        if prefer_region and recs:
            recs = self._prefer_region(recs, region, streaming10)
        return SegmentMatch(show=show, matched=bool(recs), records=recs)

    def _prefer_region(self, recs: list[SegmentRecord], region: Optional[str],
                       streaming10: bool = False) -> list[SegmentRecord]:
        """Keep only the best-ranked tier that has a match (see _segment_rank). Used for
        INCLUDE targeting; self-exclusion deliberately doesn't use it, since it must cover
        every variant of the title."""
        ranked = [(_segment_rank(_dda_tokens(r.segment_name), region, streaming10), r) for r in recs]
        ranked = [(k, r) for k, r in ranked if k is not None]
        if not ranked:
            return []
        best = min(k for k, _ in ranked)
        return [r for k, r in ranked if k == best]

    def title_families(self) -> dict[str, set[str]]:
        """{normalized title -> {families with a segment for it}}, built with the SAME matching
        resolve_exact uses (so a title is "covered" exactly when the builder would resolve it).
        Non-AU names: the title is what follows the convention prefix (+ optional SHOW/SERIES/
        MOVIE). AU Summit names: any trailing run of tokens, or the "<title> watchers APAC"
        content title. Region-independent; classify_families applies the region."""
        if not self._loaded:
            self.load()
        cached = getattr(self, "_title_families", None)
        if cached is not None:
            return cached
        idx: dict[str, set[str]] = {}
        for r, n, conv in zip(self._records, self._norm, self._conv):
            fam = _family_of(n)
            if fam is None:
                continue
            keys: set[str] = set()
            if n.startswith("au dwh"):
                toks = n.split()
                keys.update(" ".join(toks[i:]) for i in range(len(toks)))
                ct = _au_content_title(n)
                if ct:
                    keys.add(ct)
            else:
                title = _show_portion(n, conv)
                if title:
                    keys.add(title)
            for k in keys:
                idx.setdefault(k, set()).add(fam)
        self._title_families = idx
        return idx

    def region_coverage(self, shows: list[str], region: Optional[str] = None) -> dict[str, list]:
        """Group a showlist by Tier 1 coverage in `region` (region-only policy): "own" (a
        regional segment exists and is used), "elsewhere" ({"show", "using"} -- a segment exists
        only outside the region, so it is NOT used; a regional one must be requested) and "none"
        (no segment anywhere)."""
        idx = self.title_families()
        out: dict[str, list] = {"own": [], "elsewhere": [], "none": []}
        seen: set[str] = set()
        for s in shows:
            key = _dda_tokens(s or "")
            if not key or key in seen:
                continue
            seen.add(key)
            kind, label = classify_families(idx.get(key), region)
            if kind == "elsewhere":
                out["elsewhere"].append({"show": s, "using": label})
            else:
                out[kind].append(s)
        return out

    def resolve_all(self, shows: list[str], region: Optional[str] = None) -> list[SegmentMatch]:
        return [self.resolve(s, region) for s in shows]

    def resolve_all_exact(self, shows: list[str], region: Optional[str] = None,
                          prefer_region: bool = False, streaming10: bool = False) -> list[SegmentMatch]:
        """Exact per show — each showlist entry resolves to ONLY its own segment(s), never
        the wider franchise family (so 'CSI Miami' does not pull in 'The Real CSI Miami').
        `prefer_region` keeps only the region-specific match per show when there is one."""
        return [self.resolve_exact(s, region, prefer_region, streaming10) for s in shows]

    def missing_dda(self, shows: list[str], region: Optional[str] = None
                    ) -> tuple[list[dict], list[dict]]:
        """Split a showlist into (have_dda, need). A show HAS a DDA segment when a segment with
        a real FreeWheel id resolves for it (region + title find-logic); otherwise it needs one
        generated. Returns {'show', 'segment_id'} for the ones we have and {'show'} for the
        ones that need a segment generated (flag, not a submission)."""
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
            # Existence uses the SAME find-by-logic as targeting (region + title contained),
            # so messy real names (INTL prefixes, _eu/_au suffixes) are recognized and not
            # re-requested. resolve_exact would miss those and duplicate the request.
            m = self.resolve(s, region)
            sid = next((r.segment_id for r in m.records if r.segment_id), None)
            if sid:
                have.append({"show": s, "segment_id": sid})
            else:
                need.append({"show": s})
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
