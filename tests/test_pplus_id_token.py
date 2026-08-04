"""Paramount+ campaigns stamp the [ShowID:]/[MovieID:] token on EVERY placement name."""

from __future__ import annotations

from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.order_builder import OrderBuilder


def _names(campaign, region, **over):
    raw = {"promoted_title": "Frisco King", "region": region,
           "campaign": {"name": campaign}, "season_or_messaging": "Season 1",
           "durations": [30, 15], "showlist": ["NCIS"], "genres": ["Drama"], **over}
    return [p.name for p in OrderBuilder().build(support_plan_from_dict(raw)).placements]


def test_pplus_stamps_showid_on_every_placement():
    names = _names("Paramount + - FR", "FR", content_type="show", content_id="12345")
    assert names  # sanity
    # EVERY placement — remnant tiers, Pause Ad, and the guaranteed Plan lines.
    assert all(n.endswith("[ShowID:12345]") for n in names), names


def test_pplus_movie_uses_movieid():
    names = _names("Paramount + - GSA", "GSA", content_type="movie", content_id="98765")
    assert all(n.endswith("[MovieID:98765]") for n in names), names


def test_pplus_blank_id_still_stamps_token_for_cm():
    names = _names("Paramount + - IT", "IT")           # no content_id
    assert all(n.endswith("[ShowID:]") for n in names), names


def test_pplus_kids_also_stamped():
    names = _names("Paramount + - Kids - FR", "FR", showlist=["Dora"],
                   kids_audience=["younger"], content_id="555")
    assert names and all("[ShowID:555]" in n for n in names), names


def test_non_pplus_campaigns_get_no_token():
    for campaign, region in [("Pluto TV - FR", "FR"), ("CBS Network - USA", "USA"),
                             ("Nick - Kids - AU", "AU"), ("MTVE - FR", "FR")]:
        names = _names(campaign, region, content_id="12345",
                       kids_audience=["older"] if "Nick" in campaign else [])
        assert not any("ShowID" in n or "MovieID" in n for n in names), (campaign, names)
