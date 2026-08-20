"""Combined targeting: layer brief + AI + historicals, ground to inventory, rank by agreement
across sources, and carry provenance. Degrades gracefully when a source is absent."""

from __future__ import annotations

import json

from promo_ops.suggest import combine_targeting, combined_to_plan


def _ai_stub(_system, _user):
    return json.dumps({"genres": ["Crime", "Drama"], "pluto_categories": [],
                       "pluto_channels": ["Pluto TV Crime Drama"],
                       "comp_shows": ["Criminal Minds", "Fargo"]})


CORPUS = [{"promoted_title": "Tracker", "genres": ["Crime", "Drama"],
           "showlist": ["Criminal Minds", "NCIS"],
           "pluto": {"channels": ["Pluto TV Crime Drama"]}}]

BRIEF = "Genres: Crime, Drama\nShows: Criminal Minds, Yellowstone\n"


def test_combine_ranks_by_agreement_with_provenance():
    res = combine_targeting("New Crime Show", "USA", brief_text=BRIEF, llm=_ai_stub, corpus=CORPUS)
    shows = res["fields"]["showlist"]
    prov = res["provenance"]["showlist"]
    # Criminal Minds is in brief + ai + history -> most sources -> ranked first
    assert shows[0] == "Criminal Minds"
    assert set(prov["Criminal Minds"]) == {"ai", "brief", "history"}
    # a single-source show still surfaces, tagged
    assert "Yellowstone" in shows and prov["Yellowstone"] == ["brief"]


def test_combine_degrades_without_ai():
    # No llm and no description -> AI layer skipped; brief + history still produce a result.
    res = combine_targeting("New Crime Show", "USA", brief_text=BRIEF, corpus=CORPUS)
    assert "Criminal Minds" in res["fields"]["showlist"]
    for v, srcs in res["provenance"]["showlist"].items():
        assert "ai" not in srcs                     # AI cleanly absent


def test_combined_to_plan_shape():
    res = combine_targeting("New Crime Show", "USA", brief_text=BRIEF, llm=_ai_stub, corpus=CORPUS)
    plan = combined_to_plan(res, "New Crime Show", "USA", campaign_name="Paramount + - USA",
                            durations=[15, 30])
    assert plan["region"] == "USA" and plan["campaign"]["name"] == "Paramount + - USA"
    assert plan["showlist"] and plan["genres"] and plan["durations"] == [15, 30]
