"""Affinity suggester: for a thin brief (title + description, no lists) propose targeting
from OUR real inventory. AI picks are grounded (invented values dropped); the historical
engine recommends by analogy to past plans. Both return matched/review/missed for review."""

from __future__ import annotations

import json

from promo_ops.suggest import (inventory_for, suggest_ai, suggest_history,
                               load_past_plans, suggestion_to_fields)


def test_ai_grounds_every_pick_to_real_inventory():
    inv = inventory_for("USA")
    real_genre = inv["genres"][0]
    real_cat = inv["pluto_categories"][0]
    real_chan = inv["pluto_channels"][0]

    # A stub LLM that returns a mix of REAL inventory values and invented ones.
    def stub(system, user):
        return json.dumps({
            "genres": [real_genre, "Totally Made Up Genre"],
            "pluto_categories": [real_cat, "Nonexistent Category"],
            "pluto_channels": [real_chan, "Zzzq Fake Channel 999"],
            "comp_shows": ["NCIS", "Zzzq Nonexistent Series 999"],
        })

    sug = suggest_ai("Some Crime Drama", "A gritty detective hunts a serial killer.",
                     region="USA", llm=stub)
    g = sug.fields["genres"]
    assert real_genre in g.matched and "Totally Made Up Genre" in g.missed
    c = sug.fields["pluto_categories"]
    assert real_cat in c.matched and "Nonexistent Category" in c.missed
    ch = sug.fields["pluto_channels"]
    assert real_chan in ch.matched                              # exact real channel kept
    assert not any("Zzzq Fake Channel 999" == x for x in ch.matched)   # invented never auto-added
    s = sug.fields["showlist"]
    assert any("NCIS" in m for m in s.matched)                  # real series grounded
    assert "Zzzq Nonexistent Series 999" in s.missed           # invented series flagged


def test_ai_confirmed_fields_only():
    inv = inventory_for("USA")
    def stub(system, user):
        return json.dumps({"genres": [inv["genres"][0]], "pluto_categories": [],
                           "pluto_channels": [], "comp_shows": ["NCIS"]})
    sug = suggest_ai("X", "desc", region="USA", llm=stub)
    fields = suggestion_to_fields(sug)
    assert inv["genres"][0] in fields["genres"]
    assert "pluto_categories" not in fields                     # empty fields excluded


CORPUS = [
    {"promoted_title": "Tracker", "genres": ["Drama", "Crime"],
     "showlist": ["FBI", "NCIS"], "pluto": {"channels": ["CSI"], "categories": ["Drama"]}},
    {"promoted_title": "Watson", "genres": ["Crime", "Mystery"],
     "showlist": ["Elsbeth", "NCIS"], "pluto": {"channels": ["CSI", "True Crime"], "categories": ["True Crime"]}},
    {"promoted_title": "Big Brother", "genres": ["Reality"],
     "showlist": ["Survivor"], "pluto": {"channels": ["Reality"], "categories": ["Reality"]}},
]


def test_history_recommends_from_similar_titles():
    sug = suggest_history("A New Crime Show", ["Crime", "Drama"], CORPUS, k=2)
    # crime/drama titles (Tracker, Watson) dominate — Reality's Survivor must not surface
    shows = sug.fields["showlist"].matched
    assert "NCIS" in shows and "Survivor" not in shows
    assert "CSI" in sug.fields["pluto_channels"].matched
    assert sug.notes and "Modeled on" in sug.notes[0]


def test_history_handles_no_match():
    sug = suggest_history("Cooking Competition", ["Food"], CORPUS, k=3)
    assert sug.fields["showlist"].matched == [] or "Survivor" not in sug.fields["showlist"].matched
    assert sug.notes


def test_load_past_plans(tmp_path):
    (tmp_path / "a.plan.json").write_text(json.dumps(CORPUS[0]), encoding="utf-8")
    (tmp_path / "b.plan.json").write_text(json.dumps(CORPUS[1]), encoding="utf-8")
    (tmp_path / "notaplan.txt").write_text("ignore me", encoding="utf-8")
    plans = load_past_plans(tmp_path)
    assert len(plans) == 2 and plans[0]["promoted_title"] == "Tracker"
