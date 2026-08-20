"""Affinity suggester for THIN briefs — when all we get is a title + a short description and
no channel/show/genre list. Both engines propose targeting drawn from OUR real inventory so
every suggestion is a pushable FreeWheel value, and both return the same shape (per-field
matched / review / missed) that a CM confirms — never auto-applied.

  * suggest_ai(title, description, region, llm=...)
        An LLM reads the title + description and, constrained to our catalogs, picks genres
        and Pluto categories from the allowed lists and PROPOSES Pluto channels + comp shows;
        we then ground every pick against the real inventory (anything invented is dropped
        to 'review'/'missed'). Runtime needs an Anthropic key (ANTHROPIC_API_KEY); the `llm`
        arg is injectable for tests and offline demos.

  * suggest_history(title, genres, past_plans, k=...)
        Recommend by analogy: score past plans by genre + title similarity, then surface the
        showlist / channels / categories that co-occurred with the most similar past titles.
        Needs a corpus of past plans (a folder of *.plan.json); no external calls.

Feeds the same resolver/plan path as brief.py (to_plan_dict), so a thin brief can still
produce a reviewable, tiered plan.
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# --- inventory the suggestions must ground against -------------------------- #

def _genre_options() -> list[str]:
    """Content genres (+ sub-genres) from the exported option list — NOT franchise/brand/
    daypart, which aren't 'genres' for affinity purposes."""
    from .config import REPO_ROOT
    p = REPO_ROOT / "templates" / "targeting-options" / "genres.csv"
    out: list[str] = []
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            if (r.get("type") or "").strip() == "Genre":
                v = (r.get("value") or "").strip()
                if v:
                    out.append(v)
    return out


def inventory_for(region: str) -> dict[str, list[str]]:
    from .brief import _pluto_options
    cats, chans = _pluto_options(region)
    return {"genres": _genre_options(), "pluto_categories": cats, "pluto_channels": chans}


@dataclass
class AffinitySuggestion:
    source: str                                            # "ai" | "history"
    fields: dict[str, "FieldPicks"] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class FieldPicks:
    field: str
    matched: list[str] = field(default_factory=list)       # real inventory values, ready to add
    review: list[dict] = field(default_factory=list)        # [{term, options:[...]}] close-but-unconfirmed
    missed: list[str] = field(default_factory=list)


# --- AI-assisted engine ---------------------------------------------------- #

_AI_SYSTEM = (
    "You are a senior Paramount streaming media planner. Given a title and a short "
    "description, choose promo TARGETING affinities. Rules:\n"
    "- Pick genres ONLY from the allowed genre list.\n"
    "- Pick Pluto categories ONLY from the allowed category list.\n"
    "- Propose 10-20 comp SHOWS and 10-20 PLUTO CHANNELS by real name (they'll be matched "
    "against our catalog). Aim for a GOOD MIX, not just the single closest genre: include the "
    "core-genre titles PLUS tonally adjacent ones (similar audience, mood, or era) so the "
    "affinity set has breadth. Comp shows = existing TV series with a similar audience/tone "
    "(never the promoted title itself). Order both lists best-fit first.\n"
    "- Each comp show also becomes a Tier 1 audience segment downstream, so favor well-known "
    "series likely to have a dedicated audience.\n"
    'Return STRICT JSON: {"genres":[],"pluto_categories":[],"pluto_channels":[],"comp_shows":[]}. '
    "No commentary."
)


def _ai_user_prompt(title: str, description: str, inv: dict[str, list[str]]) -> str:
    return (f"TITLE: {title}\n\nDESCRIPTION:\n{description.strip()}\n\n"
            f"ALLOWED GENRES ({len(inv['genres'])}): {', '.join(inv['genres'])}\n\n"
            f"ALLOWED PLUTO CATEGORIES ({len(inv['pluto_categories'])}): "
            f"{', '.join(inv['pluto_categories'])}\n")


def _anthropic_llm(system: str, user: str) -> str:
    """Default runtime caller — Anthropic Messages API. Model via AFFINITY_MODEL env."""
    import anthropic  # imported lazily so the module works without the SDK/key
    model = os.environ.get("AFFINITY_MODEL", "claude-sonnet-5")
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=1200, system=system,
                                 messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def _parse_llm_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def suggest_ai(title: str, description: str, region: str,
               llm: Optional[Callable[[str, str], str]] = None,
               series_resolver=None) -> AffinitySuggestion:
    from .series import SeriesResolver
    inv = inventory_for(region)
    caller = llm or _anthropic_llm
    picks = _parse_llm_json(caller(_AI_SYSTEM, _ai_user_prompt(title, description, inv)))

    sug = AffinitySuggestion(source="ai")
    # genres / categories: must be in the allowed list (case-insensitive) — invented ones drop
    sug.fields["genres"] = _ground_exact(picks.get("genres", []), inv["genres"], "genres")
    sug.fields["pluto_categories"] = _ground_exact(
        picks.get("pluto_categories", []), inv["pluto_categories"], "pluto_categories")
    # channels: model proposed names -> match our channel inventory (exact, else fuzzy=review)
    sug.fields["pluto_channels"] = _ground_fuzzy(
        picks.get("pluto_channels", []), inv["pluto_channels"], "pluto_channels")
    # comp shows: model proposed titles -> resolve against the series catalog
    sr = series_resolver or SeriesResolver().load()
    shows = FieldPicks("showlist")
    for term in picks.get("comp_shows", []):
        term = str(term).strip()
        if not term:
            continue
        exact = sr.resolve_exact(term).series
        if exact:
            shows.matched.append(exact[0]["name"])
        else:
            near = [h["name"] for h in sr.resolve(term, limit=5).series]
            (shows.review.append({"term": term, "options": near}) if near else shows.missed.append(term))
    sug.fields["showlist"] = _dedup(shows)
    return sug


def _ground_exact(terms, options, name) -> FieldPicks:
    low = {o.lower(): o for o in options}
    r = FieldPicks(name)
    for t in terms:
        t = str(t).strip()
        (r.matched.append(low[t.lower()]) if t.lower() in low else r.missed.append(t))
    return _dedup(r)


def _ground_fuzzy(terms, options, name) -> FieldPicks:
    low = {o.lower(): o for o in options}
    r = FieldPicks(name)
    for t in terms:
        t = str(t).strip()
        if t.lower() in low:
            r.matched.append(low[t.lower()])
            continue
        near = [o for o in options if t.lower() in o.lower() or o.lower() in t.lower()][:6]
        (r.review.append({"term": t, "options": near}) if near else r.missed.append(t))
    return _dedup(r)


def _dedup(r: FieldPicks) -> FieldPicks:
    seen, uniq = set(), []
    for v in r.matched:
        if v.lower() not in seen:
            seen.add(v.lower()); uniq.append(v)
    r.matched = uniq
    return r


# --- historical / analogy engine ------------------------------------------- #

def load_past_plans(folder: str | Path) -> list[dict]:
    """Read every *.plan.json in a folder into plan dicts (the corpus to learn from)."""
    out: list[dict] = []
    for p in sorted(Path(folder).glob("*.plan.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return out


def _toks(s: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(w) > 2}


def _similarity(title: str, genres: list[str], plan: dict) -> float:
    """Jaccard on genres (primary) + a light title-token overlap bonus."""
    pg = {g.lower() for g in plan.get("genres", [])}
    qg = {g.lower() for g in genres}
    gj = len(pg & qg) / len(pg | qg) if (pg or qg) else 0.0
    pt, qt = _toks(plan.get("promoted_title", "")), _toks(title)
    tj = len(pt & qt) / len(pt | qt) if (pt or qt) else 0.0
    return 0.8 * gj + 0.2 * tj


def suggest_history(title: str, genres: list[str], past_plans: list[dict],
                    k: int = 3, region: Optional[str] = None) -> AffinitySuggestion:
    """Rank past plans by similarity to (title, genres); surface the affinities that recur in
    the most similar ones, weighted by similarity. Pure analogy — no external calls.

    When `region` is given, only same-region history is used (titles/channels differ per
    region) — falling back to all regions if that region has no history yet."""
    if region:
        same = [p for p in past_plans if (p.get("region") or "").upper() == region.upper()]
        past_plans = same or past_plans
    scored = sorted(((p, _similarity(title, genres, p)) for p in past_plans),
                    key=lambda x: x[1], reverse=True)
    top = [(p, s) for p, s in scored if s > 0][:k]
    sug = AffinitySuggestion(source="history")

    def _weighted(getter) -> FieldPicks:
        weight: dict[str, float] = {}
        for p, s in top:
            for v in getter(p):
                weight[v] = weight.get(v, 0.0) + s
        ranked = [v for v, _ in sorted(weight.items(), key=lambda x: x[1], reverse=True)]
        return FieldPicks(getter.__name__.strip("_"), matched=ranked)

    def showlist(p):          return p.get("showlist", [])
    def pluto_channels(p):    return (p.get("pluto") or {}).get("channels", [])
    def pluto_categories(p):  return (p.get("pluto") or {}).get("categories", [])
    for f in (showlist, pluto_channels, pluto_categories):
        picks = _weighted(f); picks.field = f.__name__
        sug.fields[f.__name__] = picks
    if top:
        sug.notes.append("Modeled on: " + ", ".join(
            f"{p.get('promoted_title', '?')} ({s:.0%})" for p, s in top))
    else:
        sug.notes.append("No sufficiently similar past plan found.")
    return sug


# --- shared: fold suggestions into plan fields ----------------------------- #

def suggestion_to_fields(sug: AffinitySuggestion) -> dict[str, list[str]]:
    """The CONFIRMED (matched) picks, ready to merge into a plan dict via brief.to_plan_dict
    or the form. Review/missed are intentionally excluded — a CM confirms those."""
    return {f: fp.matched for f, fp in sug.fields.items() if fp.matched}


# --- combined engine: brief + AI + historicals, ranked by agreement ---------- #

# Field keys shared by all three engines (brief.resolve_brief, suggest_ai, suggest_history).
_COMBINE_FIELDS = ("genres", "showlist", "pluto_categories", "pluto_channels")
_SOURCE_PRIORITY = {"brief": 3, "history": 2, "ai": 1}   # tiebreak when agreement is equal


def combine_targeting(title, region, brief_text=None, description=None, corpus=None,
                      llm=None, series_resolver=None):
    """Build the most grounded targeting by layering every available signal and ranking by
    AGREEMENT across them. Each source contributes values already grounded to our inventory:

      * brief    — explicit lists parsed from an uploaded/pasted brief (brief.resolve_brief)
      * ai       — inferred from title + description (suggest_ai); skipped if no LLM/key
      * history  — what similar past titles actually ran (suggest_history over a corpus)

    A value confirmed by more sources ranks higher (brief > history > ai on ties). Returns
    {'fields': {field: [values ranked]}, 'provenance': {field: {value: [sources]}}} — nothing
    guessed: every value came through a resolver. Degrades gracefully when a source is absent.
    """
    sources: dict[str, dict[str, set]] = {}

    def add(field, values, src):
        d = sources.setdefault(field, {})
        for v in values or []:
            d.setdefault(v, set()).add(src)

    if brief_text:
        from .brief import parse_brief, resolve_brief
        draft = parse_brief(brief_text)
        for f, r in resolve_brief(draft, region).items():
            add(f, r.matched, "brief")
        if not description:                       # let the AI use the brief's own text
            description = brief_text

    if llm is not None or description:
        try:
            sug = suggest_ai(title, description or "", region, llm=llm,
                             series_resolver=series_resolver)
            for f, fp in sug.fields.items():
                add(f, fp.matched, "ai")
        except Exception:                          # no key/SDK -> skip the AI layer, keep the rest
            pass

    if corpus:
        genres_so_far = list(sources.get("genres", {}))
        h = suggest_history(title, genres_so_far, corpus)
        for f, fp in h.fields.items():
            add(f, fp.matched, "history")

    fields: dict[str, list] = {}
    provenance: dict[str, dict] = {}
    for f in _COMBINE_FIELDS:
        vals = sources.get(f, {})
        ranked = sorted(vals.items(),
                        key=lambda kv: (-len(kv[1]), -max(_SOURCE_PRIORITY[s] for s in kv[1])))
        fields[f] = [v for v, _ in ranked]
        provenance[f] = {v: sorted(srcs) for v, srcs in vals.items()}
    return {"fields": fields, "provenance": provenance}


def combined_to_plan(result, title, region, campaign_name=None, durations=None):
    """A draft plan dict from a combine_targeting() result."""
    f = result["fields"]
    plan = {"promoted_title": title, "region": region,
            "campaign": {"name": campaign_name or ""},
            "genres": f.get("genres", []), "showlist": f.get("showlist", [])}
    pluto = {k2: f[k1] for k1, k2 in
             (("pluto_categories", "categories"), ("pluto_channels", "channels")) if f.get(k1)}
    if pluto:
        plan["pluto"] = pluto
    if durations:
        plan["durations"] = list(durations)
    return plan
