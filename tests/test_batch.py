"""Batch intake: one CSV, one row per Salesforce case → all drafts + a Case→IO summary.
Uses a fake FreeWheel client so the whole pipeline runs with no credentials/network."""

from __future__ import annotations

import csv

from promo_ops.batch import (BatchResult, load_batch_csv, process_batch,
                             render_batch_summary, row_to_plan_dict, write_results_csv)


class FakeFW:
    """Records create_order calls; assigns incrementing IO ids. Resolves every campaign to
    a fixed id (so the IO link builds). find_* returns nothing (no pre-existing IOs) unless
    `existing` is seeded {(campaign_id, name): io_id}."""
    CAMPAIGN_ID = "555"

    def __init__(self, existing=None):
        self.created: list = []
        self.existing = existing or {}
        self._n = 96000000

    def resolve_campaign_id(self, name):
        return self.CAMPAIGN_ID

    def find_insertion_order_by_name(self, campaign_id, name):
        return self.existing.get((str(campaign_id), name))

    def create_order(self, order, dry_run=True):
        self._n += 1
        self.created.append((order.name, dry_run))
        return {"campaign_id": self.CAMPAIGN_ID,
                "insertion_order": {"data": {"insertion_order": {"id": str(self._n)}}}}


def _row(**kw):
    base = {"Salesforce Case": "00100", "Region": "USA",
            "Campaign Name": "Paramount + - USA", "Promoted Title": "Yellowstone",
            "Content ID": "1", "Video Durations": "30"}
    base.update(kw)
    return base


def test_row_to_plan_dict_maps_fields_and_splits_lists():
    plan = row_to_plan_dict(_row(**{"Genres": "Drama;Westerns", "Showlist": "NCIS;FBI",
                                    "Pluto Channels": "Westerns", "Exclude Series": "Yellowstone",
                                    "Include Pause Ads": "Y"}))
    assert plan["salesforce_case"] == "00100"
    assert plan["region"] == "USA"
    assert plan["campaign"]["name"] == "Paramount + - USA"
    assert plan["durations"] == ["30"]
    assert plan["genres"] == ["Drama", "Westerns"]
    assert plan["showlist"] == ["NCIS", "FBI"]
    assert plan["pluto"]["channels"] == ["Westerns"]
    assert plan["exclude_series"] == ["Yellowstone"]
    assert plan["product_overrides"]["pause_ads"] is True


def test_header_qualifier_is_trimmed():
    plan = row_to_plan_dict({"Audience Segments (Tier 1)": "Adults 25-54",
                             "Region": "USA", "Campaign Name": "Paramount + - USA",
                             "Promoted Title": "X", "Content ID": "1", "Video Durations": "30"})
    assert plan["audience_segments"] == ["Adults 25-54"]


def test_process_batch_dry_run_builds_every_row_without_creating():
    fw = FakeFW()
    rows = [_row(**{"Salesforce Case": "00100"}),
            _row(**{"Salesforce Case": "00101", "Promoted Title": "Tulsa King"})]
    results = process_batch(rows, fw=fw, create=False)
    assert len(results) == 2
    assert all(r.status == "dry-run" and r.ok and r.placements > 0 for r in results)
    assert [r.salesforce_case for r in results] == ["00100", "00101"]
    assert all(dry is True for _, dry in fw.created)     # never a live create


def test_process_batch_live_creates_and_links_each_case():
    fw = FakeFW()
    results = process_batch([_row()], fw=fw, create=True)
    r = results[0]
    assert r.status == "created" and r.io_id and r.io_link
    assert "insertion_order_id" in r.io_link and FakeFW.CAMPAIGN_ID in r.io_link
    assert len(fw.created) == 1 and fw.created[0][1] is False


def test_idempotent_reuse_of_existing_io():
    # Build once to discover the campaign id + IO name the row produces, then seed an
    # existing IO under that key so the row reuses instead of creating a duplicate.
    from promo_ops.order_builder import OrderBuilder
    from promo_ops.plan_loader import support_plan_from_dict
    order = OrderBuilder().build(support_plan_from_dict(row_to_plan_dict(_row())))
    reuse_fw = FakeFW(existing={(FakeFW.CAMPAIGN_ID, order.name): "77777777"})
    r = process_batch([_row()], fw=reuse_fw, create=True)[0]
    assert r.status == "reused" and r.io_id == "77777777"
    assert reuse_fw.created == []                          # nothing new created


def test_needs_info_row_does_not_stop_the_batch():
    fw = FakeFW()
    good = _row(**{"Salesforce Case": "00100"})
    bad = _row(**{"Salesforce Case": "00999", "Region": "", "Campaign Name": ""})
    results = process_batch([good, bad], fw=fw, create=True)
    assert results[0].status == "created"
    assert results[1].status in ("needs-info", "error") and not results[1].ok
    # The good row still created despite the bad one.
    assert len(fw.created) == 1


def test_results_csv_roundtrip(tmp_path):
    fw = FakeFW()
    results = process_batch([_row(), _row(**{"Salesforce Case": "00101"})], fw=fw, create=True)
    out = tmp_path / "results.csv"
    write_results_csv(results, out)
    back = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["salesforce_case"] for r in back] == ["00100", "00101"]
    assert all(r["status"] == "created" and r["io_id"] for r in back)


def test_load_batch_csv_skips_blank_rows(tmp_path):
    p = tmp_path / "cases.csv"
    p.write_text("Salesforce Case,Region,Campaign Name,Promoted Title,Content ID,Video Durations\n"
                 "00100,USA,Paramount + - USA,Yellowstone,1,30\n"
                 ",,,,,\n", encoding="utf-8")
    rows = load_batch_csv(p)
    assert len(rows) == 1 and rows[0]["Salesforce Case"] == "00100"


def test_render_summary_has_counts_and_per_case_lines():
    results = [BatchResult(row=1, salesforce_case="00100", region="USA", status="created",
                           placements=14, io_link="http://io/1"),
               BatchResult(row=2, salesforce_case="00101", region="USA", status="needs-info",
                           problems=["missing campaign"])]
    text = render_batch_summary(results, create=True)
    assert "2 case(s)" in text and "1 created" in text and "1 needs-info" in text
    assert "00100" in text and "00101" in text
