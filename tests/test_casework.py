"""Salesforce-driven case pipeline (design-first, fake clients)."""

import csv

from promo_ops.casework import process_case, process_ready_cases, io_url
from promo_ops.config import REPO_ROOT


def _targeting_rows():
    with (REPO_ROOT / "templates" / "campaign-plan" / "Targeting.csv").open(
            encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


GOOD_PLAN = {
    "promoted_title": "Frisco King", "region": "USA", "brand": "paramount_plus_domestic",
    "formats": ["remnant_video"], "durations": [30],
    "campaign": {"name": "Paramount + - USA", "resolved_id": "86543608"},
    "genres": ["Drama"], "showlist": ["FBI"],
    "pluto": {"channels": ["Westerns"], "categories": ["True Crime"]},
}


class FakeSF:
    READY_STATUS = "Ready for Ad Ops"
    BUILT_STATUS = "Submitted to FreeWheel"
    NEEDS_INFO_STATUS = "Needs Info"

    def __init__(self, plan_dict, ready=("500ABC",)):
        self._plan = plan_dict
        self._ready = list(ready)
        self.comments = []
        self.status = {}

    def case_to_plan_dict(self, cid):
        return dict(self._plan, salesforce_case=cid)

    def list_ready_cases(self):
        return self._ready

    def post_case_comment(self, cid, body):
        self.comments.append((cid, body))

    def update_case_status(self, cid, status):
        self.status[cid] = status


class FakeFW:
    network_id = "520311"

    def __init__(self):
        self.created = []

    def create_order(self, order, dry_run=True):
        self.created.append((order, dry_run))
        return {"insertion_order": {"data": {"insertion_order": {"id": "95999001"}}}}


def test_valid_case_builds_creates_and_comments():
    sf, fw = FakeSF(GOOD_PLAN), FakeFW()
    result = process_case("500ABC", sf=sf, fw=fw, create=True)
    assert result.ok and result.io_id == "95999001"
    assert "insertion_order_id=95999001" in result.io_link
    assert fw.created and fw.created[0][1] is False          # created live (not dry-run)
    assert sf.status["500ABC"] == FakeSF.BUILT_STATUS
    body = sf.comments[0][1]
    assert "FreeWheel draft created" in body and "Map/create the Brand" in body


def test_invalid_case_comments_problems_and_sets_needs_info():
    bad = dict(GOOD_PLAN, region="ZZ", brand="nope")
    sf, fw = FakeSF(bad), FakeFW()
    result = process_case("500BAD", sf=sf, fw=fw)
    assert not result.ok and result.validation
    assert not fw.created                                    # never built/created
    assert sf.status["500BAD"] == FakeSF.NEEDS_INFO_STATUS
    assert "could not build" in sf.comments[0][1]


def test_process_ready_cases_iterates():
    sf, fw = FakeSF(GOOD_PLAN, ready=("A", "B")), FakeFW()
    results = process_ready_cases(sf=sf, fw=fw, create=False)
    assert len(results) == 2 and all(r.ok for r in results)
    assert all(dry is True for _, dry in fw.created)         # create=False -> dry run


def test_io_url():
    assert io_url("520311", "86543608", "95999001").endswith(
        "campaigns/86543608/?insertion_order_id=95999001")
