"""FreeWheel ↔ config brand reconciliation: classify, diff, and scaffold."""

from __future__ import annotations

from promo_ops import brand_sync
from promo_ops.config import brands_config


def test_region_and_family_classification():
    assert brand_sync.region_of("Pluto TV - FR") == "FR"
    assert brand_sync.region_of("Pluto TV (Cross-Company) - USA") == "USA"
    assert brand_sync.region_of("Paramount + - GSA") == "GSA"        # not shadowed by a shorter code
    assert brand_sync.region_of("A campaign with no region") is None
    assert brand_sync.brand_family("Nick Jr. - Kids - AU") == "nick_jr"
    assert brand_sync.brand_family("Nick - Kids - AU") == "nick"
    assert brand_sync.brand_family("Paramount + - Kids - FR") == "paramount_plus_kids"
    assert brand_sync.brand_family("Paramount + - FR") == "paramount_plus"
    assert brand_sync.brand_family("Pluto TV - Kids - FR") == "pluto_kids"


def test_looks_like_brand_campaign_filters_noise():
    assert brand_sync.looks_like_brand_campaign("Pluto TV - FR")
    assert not brand_sync.looks_like_brand_campaign("Q3 Sales House Campaign")   # no region/family
    assert not brand_sync.looks_like_brand_campaign("Pluto TV")                  # no region tail


def test_reconcile_finds_missing_in_config():
    brands = {
        "pluto_tv_fr": {"campaign_name": "Pluto TV - FR"},
        "paramount_plus_fr": {"campaign_name": "Paramount + - FR"},
    }
    fw = [
        {"name": "Pluto TV - FR", "id": 1},               # matched
        {"name": "Paramount + - FR", "id": 2},            # matched
        {"name": "Paramount + - Kids - FR", "id": 3},     # missing in config
        {"name": "Some Sales Campaign", "id": 9},         # ignored (not a brand campaign)
    ]
    res = brand_sync.reconcile(fw, brands)
    assert {r["campaign_name"] for r in res["matched"]} == {"Pluto TV - FR", "Paramount + - FR"}
    assert [r["campaign_name"] for r in res["missing_in_config"]] == ["Paramount + - Kids - FR"]
    assert res["missing_in_fw"] == []


def test_reconcile_flags_config_without_fw():
    brands = {"pluto_tv_zz": {"campaign_name": "Pluto TV - NO"}}
    res = brand_sync.reconcile([], brands)
    assert [r["brand_key"] for r in res["missing_in_fw"]] == ["pluto_tv_zz"]


def test_scaffold_clones_a_sibling_and_blanks_region_ids():
    brands = brands_config().get("brands", {})
    # A real family that exists in other regions but pretend it's missing for DK.
    row = {"campaign_name": "Paramount + - DK", "campaign_id": "999999",
           "region": "DK", "family": "paramount_plus"}
    key, entry = brand_sync.scaffold_entry(row, brands)
    assert key == "paramount_plus_dk"
    assert entry["campaign_name"] == "Paramount + - DK"
    assert entry["template_campaign_id"] == "999999"
    assert entry["display_name"] == "Paramount + (DK)"
    assert entry["_cloned_from"]                     # records provenance
    assert entry["formats"]                          # format set carried over from sibling
    # Region-specific FW ids are blanked with a TODO, never guessed.
    if "main_site_groups" in entry:
        assert str(entry["main_site_groups"]).startswith("TODO")


def test_scaffold_returns_none_without_sibling():
    assert brand_sync.scaffold_entry(
        {"campaign_name": "Mystery - FR", "region": "FR", "family": "nonexistent"},
        {}) is None
