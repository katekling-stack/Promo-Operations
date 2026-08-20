"""Parse a promo media brief into a draft support plan, resolving the key affinities
against the synced FreeWheel catalogs.

Two brief shapes are supported by the SAME parser:

1. **Labeled** — the clean media-plan style a CM pastes:

       Genres: Drama, Crime, Suspense
       Shows/Titles: Watson, Elsbeth, NCIS Franchise (except NCIS: Sydney)
       Pluto TV Categories: True Crime, Drama
       Pluto TV Channels: Pluto TV Drama, CSI, CSI: NY

2. **Prose marketing brief** (e.g. a Global Media Brief .docx) — the targeting signal
   is buried in prose + a ``COMP SHOW LIST`` block + a ``Top DMAS`` line + a logistics
   table (BRAND / CAMPAIGN NAME / LIVE DATE). We mine those.

`parse_brief(text)` runs BOTH passes and unions the result — labeled values win, prose
fills the gaps. `resolve_brief(draft, region)` then matches every extracted term against
the real catalogs (SeriesResolver, GenreVideoGroupResolver) and reports, per field, what
matched exactly, what's a close-but-unconfirmed suggestion, and what didn't resolve — the
same three-way confidence the form's brief box shows. Nothing is guessed silently; a CM
confirms the "review" items before a plan is pushed.

Geo is intentionally NOT extracted: promos run broad across the campaign's whole country,
so DMAs/markets never come from a brief.
"""

from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# --- brief text extraction ------------------------------------------------- #

def docx_to_text(path: str | Path) -> str:
    """Best-effort plain-text extraction from a .docx (no external deps): pull every
    text run in document order, breaking lines on paragraphs and table cells."""
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "ignore")
    xml = xml.replace("</w:p>", "\n").replace("</w:tc>", " | ").replace("</w:tr>", "\n")
    xml = re.sub(r"<[^>]+>", "", xml)
    lines = [re.sub(r"[ \t]+", " ", ln).strip(" |").strip() for ln in html.unescape(xml).split("\n")]
    return "\n".join(ln for ln in lines if ln)


def read_brief(path: str | Path) -> str:
    p = Path(path)
    if p.suffix.lower() == ".docx":
        return docx_to_text(p)
    return p.read_text(encoding="utf-8", errors="ignore")


# --- what we can target ---------------------------------------------------- #

# Fields the brief can fill (the plan keys the OrderBuilder consumes for targeting).
BRIEF_FIELDS = ("genres", "showlist", "pluto_categories", "pluto_channels")

# Labeled-brief routing: label alias (lowercased) -> plan field. Longest alias wins.
# NOTE: Pluto categories/channels require the "Pluto" carrier — bare "Category:"/"Channel:"
# appear all over marketing prose (audience profiling), so they'd false-positive. DMAs are
# mined from the "Top DMAS" block (prose), not a label, for the same reason.
LABEL_ROUTES: dict[str, str] = {}
for _field, _aliases in {
    "genres": ["genres", "genre"],
    "showlist": ["shows/titles", "shows", "titles", "series", "comp show list"],
    "pluto_categories": ["pluto tv categories", "pluto categories"],
    "pluto_channels": ["pluto tv channels", "pluto channels"],
    "audience_hints": ["target audience", "audience segments"],
}.items():
    for _a in _aliases:
        LABEL_ROUTES[_a] = _field

# Informational labels — surfaced as notes, never auto-targeted.
NOTE_LABELS = ["video domination", "pause ads", "flight", "budget", "goal", "kpi", "kpis",
               "objective", "owner/poc", "live date", "brief date"]

# Genre words worth probing the brief's prose for; each is only kept if it actually
# resolves to a genre Video Group (so we never invent a genre FW can't target).
GENRE_HINTS = ["Crime Drama", "True Crime", "Crime", "Drama", "Action", "Thriller",
               "Suspense", "Mystery", "Horror", "Western", "Westerns", "Sports",
               "Documentary", "Sci-Fi", "Fantasy", "Comedy"]


@dataclass
class BriefDraft:
    """Raw pulled-from-the-brief terms, before catalog resolution."""
    fields: dict[str, list[str]] = field(default_factory=lambda: {f: [] for f in BRIEF_FIELDS})
    logistics: dict[str, str] = field(default_factory=dict)
    audience_hints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --- parsing --------------------------------------------------------------- #

_EXCEPT = re.compile(r"\(\s*(?:except|excluding|no|not)\s+(.+?)\s*\)", re.I)


def _split_terms(payload: str) -> list[str]:
    return [t.strip(" .;") for t in re.split(r"[\n,;\t]+", payload) if t.strip(" .;")]


def _logistics(text: str) -> dict[str, str]:
    """Pull the Section-1 logistics table. Labels sit on their OWN line with the value on
    the NEXT line (BRAND\\nParamount+), so read label->next-nonempty-line."""
    want = {"BRAND": "brand", "CAMPAIGN NAME": "campaign_name", "CAMPAIGN TYPE": "campaign_type",
            "LIVE DATE": "live_date", "OWNER/POC": "owner", "BUDGET": "budget"}
    lines = [ln.strip() for ln in text.splitlines()]
    out: dict[str, str] = {}
    for i, ln in enumerate(lines):
        key = want.get(ln.upper())
        if key and key not in out and i + 1 < len(lines) and lines[i + 1]:  # first wins
            out[key] = lines[i + 1]
    m = re.search(r"Premiere:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", text)
    if m:
        out["premiere"] = m.group(1)
    return out


def _comp_show_list(text: str) -> list[str]:
    """The 'COMP SHOW LIST' block (Internal + External sub-lists) is the richest affinity
    signal in a marketing brief. Capture every title line until the next SECTION header."""
    m = re.search(r"COMP SHOW LIST", text, re.I)
    if not m:
        return []
    tail = text[m.end():]
    end = re.search(r"\n\s*SECTION\b", tail, re.I)
    block = tail[: end.start()] if end else tail
    shows: list[str] = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s or s.lower() in ("internal", "external"):
            continue
        if "," in s or len(s.split()) <= 8:      # a title line, not a sentence
            shows.extend(_split_terms(s))
    return shows


def _labeled_sections(text: str) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Find '<label>: <values>' where a label starts a line or follows ';'. A payload runs to
    the end of its LINE (or the next mid-line label), so a stray label in prose can only ever
    capture its own line — never runs away and swallows the document."""
    t = "\n" + text
    aliases = sorted(list(LABEL_ROUTES) + NOTE_LABELS, key=len, reverse=True)
    kw = "|".join(re.escape(a) for a in aliases)
    rx = re.compile(r"(?:^|\n|;)[ \t]*(" + kw + r")[ \t]*:", re.I)
    hits = list(rx.finditer(t))
    fields: dict[str, list[str]] = {f: [] for f in BRIEF_FIELDS}
    audience: list[str] = []
    notes: list[str] = []
    for i, mt in enumerate(hits):
        label = mt.group(1).lower().strip()
        start = mt.end()
        eol = t.find("\n", start)
        eol = len(t) if eol < 0 else eol
        nxt = hits[i + 1].start() if i + 1 < len(hits) else len(t)
        payload = t[start:min(eol, nxt)].strip()
        terms = _split_terms(payload)
        route = LABEL_ROUTES.get(label)
        if route == "audience_hints":
            audience.extend(terms)
        elif route in fields:
            fields[route].extend(terms)
        elif payload:
            notes.append(f"{label}: {payload[:120]}")
    return fields, audience, notes


def parse_brief(text: str) -> BriefDraft:
    d = BriefDraft()
    d.logistics = _logistics(text)

    # 1) labeled sections (works for the clean media-plan paste)
    lf, audience, notes = _labeled_sections(text)
    for f in BRIEF_FIELDS:
        d.fields[f].extend(lf[f])
    d.audience_hints.extend(audience)
    d.notes.extend(notes)

    # 2) prose-brief fallbacks
    d.fields["showlist"].extend(_comp_show_list(text))              # COMP SHOW LIST block
    # NOTE: DMAs are deliberately NOT pulled — promos run broad across the whole country,
    # so geo never comes from a brief.
    lower = text.lower()
    for g in GENRE_HINTS:                                            # genre words present anywhere
        if re.search(r"\b" + re.escape(g.lower()) + r"\b", lower):
            d.fields["genres"].append(g)

    # de-dup each field, preserve order (case-insensitive)
    for f in BRIEF_FIELDS:
        seen, uniq = set(), []
        for v in d.fields[f]:
            k = v.lower()
            if k and k not in seen:
                seen.add(k); uniq.append(v)
        d.fields[f] = uniq
    return d


# --- resolution against the catalogs -------------------------------------- #

@dataclass
class FieldResult:
    field: str
    matched: list[str] = field(default_factory=list)          # canonical option names
    review: list[dict] = field(default_factory=list)          # [{term, options:[...]}]
    missed: list[str] = field(default_factory=list)


def _expand_franchise(term: str, series_resolver) -> tuple[list[str], bool]:
    """'NCIS Franchise (except NCIS: Sydney)' -> every NCIS series name minus the exception.
    Returns (names, is_franchise)."""
    _folded = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())       # ignore ':' vs '-' vs spacing
    excepts = [_folded(e) for e in _EXCEPT.findall(term) if e.strip()]
    base = _EXCEPT.sub("", term).strip()
    is_fr = bool(re.search(r"\bfranchise\b", base, re.I))
    base = re.sub(r"\bfranchise\b", "", base, flags=re.I).strip(" :-")
    if not is_fr:
        return [term], False
    names, seen = [], set()
    for hit in series_resolver.resolve(base).series:
        nm = hit["name"]
        fold = _folded(nm)
        if fold in seen or any(x and x in fold for x in excepts):
            continue
        seen.add(fold); names.append(nm)
    return names, True


def resolve_brief(draft: BriefDraft, region: str,
                  series_resolver=None, genre_resolver=None) -> dict[str, FieldResult]:
    from .series import SeriesResolver
    from .video_groups import GenreVideoGroupResolver

    sr = series_resolver or SeriesResolver().load()
    gr = genre_resolver or GenreVideoGroupResolver().load()

    out: dict[str, FieldResult] = {}

    # Shows -> Video Series (exact; franchise terms expand; near-misses become review)
    shows = FieldResult("showlist")
    for term in draft.fields["showlist"]:
        names, is_fr = _expand_franchise(term, sr)
        if is_fr:
            (shows.matched.extend(names) if names else shows.missed.append(term))
            continue
        exact = sr.resolve_exact(term).series
        if exact:
            shows.matched.append(exact[0]["name"])
        else:
            near = [h["name"] for h in sr.resolve(term, limit=6).series]
            (shows.review.append({"term": term, "options": near}) if near else shows.missed.append(term))
    out["showlist"] = _dedup(shows)

    # Genres -> genre Video Groups (only keep the ones FW can actually target)
    genres = FieldResult("genres")
    for term in draft.fields["genres"]:
        genres.matched.append(term) if gr.resolve(term).matched else genres.missed.append(term)
    out["genres"] = _dedup(genres)

    # Pluto categories / channels -> region option lists (best-effort; needs Pluto data)
    cats, chans = _pluto_options(region)
    out["pluto_categories"] = _match_list(draft.fields["pluto_categories"], cats, "pluto_categories")
    out["pluto_channels"] = _match_list(draft.fields["pluto_channels"], chans, "pluto_channels")
    return out


def _dedup(r: FieldResult) -> FieldResult:
    seen, uniq = set(), []
    for v in r.matched:
        if v.lower() not in seen:
            seen.add(v.lower()); uniq.append(v)
    r.matched = uniq
    return r


def _pluto_options(region: str) -> tuple[list[str], list[str]]:
    """Region's Pluto categories/channels from the exported option lists (if present)."""
    import csv
    from .config import REPO_ROOT
    base = REPO_ROOT / "templates" / "targeting-options"
    def col(fname: str, want: str) -> list[str]:
        p = base / fname
        if not p.exists():
            return []
        vals = []
        for row in csv.DictReader(p.open(encoding="utf-8")):
            if (row.get("region") or "").strip() == region:
                v = (row.get(want) or "").strip()
                if v:
                    vals.append(v)
        return vals
    return (col("pluto-categories-by-region.csv", "category"),
            col("pluto-channels-by-region.csv", "channel"))


def _match_list(terms: list[str], options: list[str], field_name: str) -> FieldResult:
    r = FieldResult(field_name)
    low = {o.lower(): o for o in options}
    for term in terms:
        t = term.lower()
        if t in low:
            r.matched.append(low[t])
        else:
            near = [o for o in options if t in o.lower() or o.lower() in t][:6]
            (r.review.append({"term": term, "options": near}) if near else r.missed.append(term))
    return _dedup(r)


# --- draft plan ------------------------------------------------------------ #

def to_plan_dict(draft: BriefDraft, resolved: dict[str, FieldResult], region: str,
                 campaign_name: Optional[str] = None) -> dict:
    """Assemble a draft plan.json from the CONFIRMED (matched) terms. Review/missed items
    are intentionally left out — a CM confirms them in the form/CLI before they're added."""
    title = draft.logistics.get("campaign_name") or "(set title)"
    plan: dict = {
        "promoted_title": title,
        "region": region,
        "campaign": {"name": campaign_name or draft.logistics.get("campaign_name") or ""},
        "genres": resolved["genres"].matched,
        "showlist": resolved["showlist"].matched,
    }
    if resolved["pluto_categories"].matched or resolved["pluto_channels"].matched:
        plan["pluto"] = {}
        if resolved["pluto_categories"].matched:
            plan["pluto"]["categories"] = resolved["pluto_categories"].matched
        if resolved["pluto_channels"].matched:
            plan["pluto"]["channels"] = resolved["pluto_channels"].matched
    return plan


def report_text(draft: BriefDraft, resolved: dict[str, FieldResult]) -> str:
    """Human-readable match report — matched / needs-review / not-found per field."""
    lines: list[str] = []
    if draft.logistics:
        lines.append("LOGISTICS: " + ", ".join(f"{k}={v}" for k, v in draft.logistics.items()))
    titles = {"showlist": "Shows (affinity)", "genres": "Genres",
              "pluto_categories": "Pluto Categories", "pluto_channels": "Pluto Channels"}
    for f, r in resolved.items():
        if not (r.matched or r.review or r.missed):
            continue
        lines.append(f"\n{titles.get(f, f)}:")
        if r.matched:
            lines.append(f"  matched ({len(r.matched)}): " + ", ".join(r.matched[:20])
                         + (" …" if len(r.matched) > 20 else ""))
        for rv in r.review:
            opts = ", ".join(rv["options"][:4])
            lines.append(f"  review — '{rv['term']}' → did you mean: {opts}")
        if r.missed:
            lines.append(f"  not found ({len(r.missed)}): " + ", ".join(r.missed))
    if draft.audience_hints:
        lines.append("\nAudience hints (not auto-targeted): " + ", ".join(draft.audience_hints[:10]))
    if draft.notes:
        lines.append("\nNotes: " + " · ".join(draft.notes[:8]))
    return "\n".join(lines)
