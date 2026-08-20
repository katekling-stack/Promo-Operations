"""Historical corpus: harvest past FreeWheel IOs into plan rows (reverse-mapping targeting
IDs -> names), so the suggester can recommend by analogy to what actually ran."""

from __future__ import annotations

import json

from promo_ops import history
from promo_ops.suggest import suggest_history


def test_clean_title():
    assert history._clean_title("Walker - Stream Now - 30 (Tier 2) (My5) - UK") == "Walker"
    assert history._clean_title("Dexter: Resurrection S2 - USA") == "Dexter: Resurrection S2"


class _FakeClient:
    """Minimal stand-in: one IO, two placements whose targeting references known IDs."""
    def list_placements(self, io_id):
        return [{"id": "1"}, {"id": "2"}]

    def _invoke(self, tool, **kw):
        bodies = {
            1: {"relationship_targeting": {"set": [{"content_targeting": {"network_items":
                 {"include": {"set": [{"series": ["111111", "111222"]}, {"site_group": ["333333"]}]}}}}]}},
            2: {"relationship_targeting": {"set": [{"content_targeting": {"network_items":
                 {"include": {"set": [{"video_group": ["222222"]}]}}}}]}},
        }
        return {"data": {"placement": bodies[kw["placement_id"]]}}


def test_harvest_io_reverse_maps_ids_to_names():
    maps = ({"111111": "FBI", "111222": "NCIS"}, {"222222": "Crime Drama"}, {"333333": "Pluto TV Crime Drama"})
    row = history.harvest_io(_FakeClient(), "io9", "Tracker - USA", maps)
    assert row["promoted_title"] == "Tracker"
    assert row["region"] == "USA"
    assert set(row["showlist"]) == {"FBI", "NCIS"}
    assert row["genres"] == ["Crime Drama"]
    assert row["pluto"]["channels"] == ["Pluto TV Crime Drama"]


def test_history_prefers_same_region():
    corpus = [
        {"promoted_title": "US Crime A", "region": "USA", "genres": ["Crime"],
         "showlist": ["FBI"], "pluto": {"channels": ["Pluto TV Crime Drama"]}},
        {"promoted_title": "UK Crime B", "region": "UK", "genres": ["Crime"],
         "showlist": ["Broadchurch"], "pluto": {"channels": ["5 Crime"]}},
    ]
    us = suggest_history("New Crime", ["Crime"], corpus, region="USA")
    assert "FBI" in us.fields["showlist"].matched and "Broadchurch" not in us.fields["showlist"].matched
    uk = suggest_history("New Crime", ["Crime"], corpus, region="UK")
    assert "Broadchurch" in uk.fields["showlist"].matched and "FBI" not in uk.fields["showlist"].matched


def test_load_corpus_jsonl(tmp_path):
    p = tmp_path / "corpus.jsonl"
    rows = [{"promoted_title": "A", "genres": ["Crime"], "showlist": ["FBI"], "pluto": {"channels": ["CSI"]}},
            {"promoted_title": "B", "genres": ["Comedy"], "showlist": ["Frasier"], "pluto": {"channels": []}}]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = history.load_corpus(p)
    assert len(corpus) == 2 and corpus[0]["promoted_title"] == "A"


def test_corpus_feeds_suggest_history(tmp_path):
    p = tmp_path / "corpus.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"promoted_title": "Tracker", "genres": ["Crime", "Drama"], "showlist": ["FBI", "NCIS"],
         "pluto": {"channels": ["Pluto TV Crime Drama"]}},
        {"promoted_title": "Big Brother", "genres": ["Reality"], "showlist": ["Survivor"],
         "pluto": {"channels": ["Reality"]}},
    ]), encoding="utf-8")
    sug = suggest_history("New Crime Show", ["Crime", "Drama"], history.load_corpus(p), k=2)
    assert "FBI" in sug.fields["showlist"].matched and "Survivor" not in sug.fields["showlist"].matched
