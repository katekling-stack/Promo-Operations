"""Brief parser: a promo brief (prose marketing brief OR clean labeled lists) is mined for
its key affinities and resolved against the catalogs into a draft plan. Matched terms fill
the plan; near-misses/unmatched are reported for a human to confirm — never guessed in."""

from __future__ import annotations

from pathlib import Path

from promo_ops.brief import parse_brief, resolve_brief, to_plan_dict

FIXTURE = Path(__file__).parent / "fixtures" / "dexter_brief.txt"


def _draft():
    return parse_brief(FIXTURE.read_text(encoding="utf-8"))


def test_extracts_comp_show_list():
    d = _draft()
    shows = [s.lower() for s in d.fields["showlist"]]
    # Internal + External COMP SHOW LIST titles are pulled
    assert "yellowstone" in shows and "criminal minds" in shows and "better call saul" in shows
    # a stray prose label must NOT run away and swallow the doc
    assert len(d.fields["pluto_categories"]) < 5


def test_extracts_logistics_and_dmas():
    d = _draft()
    assert d.logistics.get("brand") == "Paramount+"
    assert "Dexter" in (d.logistics.get("campaign_name") or "")
    assert d.logistics.get("premiere") == "10/30/26"
    assert d.logistics.get("budget", "").startswith("US:")          # first BUDGET wins, not a later table
    assert "New York" in d.fields["geo_dmas"] and "Chicago" in d.fields["geo_dmas"]


def test_mines_genres_without_prose_noise():
    d = _draft()
    g = {x.lower() for x in d.fields["genres"]}
    assert {"drama", "crime", "thriller"} <= g
    assert "news" not in g and "entertainment" not in g              # partner words, not content genres


def test_resolve_reports_matched_review_and_missed():
    d = _draft()
    res = resolve_brief(d, region="USA")
    shows = res["showlist"]
    assert "Yellowstone" in shows.matched or any("Yellowstone" in m for m in shows.matched)
    # external comps not in the P+ catalog are surfaced, never silently dropped
    assert shows.review or shows.missed
    assert res["genres"].matched                                    # genres resolve to VGs
    assert res["geo_dmas"].matched                                  # at least some DMAs resolve


def test_to_plan_dict_uses_only_confirmed_terms():
    d = _draft()
    res = resolve_brief(d, region="USA")
    plan = to_plan_dict(d, res, region="USA", campaign_name="Paramount + - USA")
    assert plan["region"] == "USA"
    assert plan["campaign"]["name"] == "Paramount + - USA"
    assert plan["showlist"] == res["showlist"].matched              # only matched shows go in
    assert plan["genres"] == res["genres"].matched
    # review/missed shows are NOT in the plan
    assert "Jessica Jones" not in plan["showlist"]


def test_labeled_brief_and_franchise_expansion():
    # The clean media-plan paste shape, with a franchise term + exception.
    text = ("Genres: Drama, Crime\n"
            "Shows/Titles: NCIS Franchise (except NCIS: Sydney), Watson\n"
            "Pluto TV Categories: True Crime\n")
    d = parse_brief(text)
    assert "Drama" in d.fields["genres"]
    assert any("NCIS" in s for s in d.fields["showlist"])
    res = resolve_brief(d, region="USA")
    ncis = [m for m in res["showlist"].matched if "NCIS" in m or "ncis" in m.lower()]
    assert len(ncis) >= 2                                           # franchise expanded to several NCIS series
    assert not any("sydney" in m.lower() for m in res["showlist"].matched)   # exception honored
