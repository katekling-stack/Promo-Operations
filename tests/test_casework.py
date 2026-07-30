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
    READY_STATUS = "Ready for Automation"
    NEEDS_INFO_STATUS = "Needs Info"
    SUBMITTED_REASON = "Submitted to FreeWheel"

    def __init__(self, plan_dict, ready=("500ABC",)):
        self._plan = plan_dict
        self._ready = list(ready)
        self.comments = []
        self.status = {}
        self.reason = {}

    def case_to_plan_dict(self, cid):
        return dict(self._plan, salesforce_case=cid)

    def list_ready_cases(self):
        return self._ready

    def post_case_comment(self, cid, body):
        self.comments.append((cid, body))

    def update_case_status(self, cid, status):
        self.status[cid] = status

    def update_case_reason(self, cid, reason):
        self.reason[cid] = reason


class FakeFW:
    network_id = "520311"

    def __init__(self, existing_io=None):
        self.created = []
        self.addon_orders = []
        self._existing = existing_io or {}     # {io_name: io_id}

    def find_insertion_order_by_name(self, campaign_id, name, **kw):
        return self._existing.get(name)

    def create_order(self, order, dry_run=True):
        self.created.append((order, dry_run))
        return {"insertion_order": {"data": {"insertion_order": {"id": "95999001"}}}}

    def create_addon_order(self, campaign_id, io_name, bodies, flight=None, dry_run=True):
        self.addon_orders.append((campaign_id, io_name, bodies, dry_run))
        return {"insertion_order": {"data": {"insertion_order": {"id": "95999777"}}}}


def test_valid_case_builds_creates_and_comments():
    sf, fw = FakeSF(GOOD_PLAN), FakeFW()
    result = process_case("500ABC", sf=sf, fw=fw, create=True)
    assert result.ok and result.io_id == "95999001"
    assert "insertion_order_id=95999001" in result.io_link
    assert fw.created and fw.created[0][1] is False          # created live (not dry-run)
    assert sf.reason["500ABC"] == FakeSF.SUBMITTED_REASON    # Reason -> Submitted
    assert "500ABC" not in sf.status                         # Status untouched on success
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


def test_case_with_pluto_vd_and_takeover_addons():
    plan = dict(GOOD_PLAN, campaign={"name": "Pluto TV - USA", "resolved_id": "54413718"},
                brand="pluto_tv", video_domination="pluto",
                video_domination_targeting=["True Crime"], takeover="hpto",
                flight={"start": "2026-10-01", "end": "2026-10-07"})
    sf, fw = FakeSF(plan), FakeFW()
    result = process_case("500VD", sf=sf, fw=fw, create=True)
    assert result.ok
    # Pluto VD pushed as its own draft IO; link surfaced.
    assert fw.addon_orders and fw.addon_orders[0][3] is False
    body = sf.comments[0][1]
    assert "Pluto Video Domination draft" in body and "insertion_order_id=95999777" in body
    # Takeover surfaced as an Operative booking to-do.
    assert "Takeover" in body and "CBS Interactive" in body


def test_operative_vd_surfaces_booking_todo():
    plan = dict(GOOD_PLAN, region="FR", campaign={"name": "Paramount + - FR", "resolved_id": "72285968"},
                brand="paramount_plus_fr", video_domination="standard")
    sf, fw = FakeSF(plan), FakeFW()
    result = process_case("500OP", sf=sf, fw=fw, create=True)
    assert result.ok and not fw.addon_orders          # operative VD is not pushed to FW
    assert any("66933" in a for a in result.addons)   # copy-Operative-order instruction


def test_reprocessing_a_case_reuses_existing_io_no_duplicate():
    # An IO named "Frisco King - USA" already exists under the campaign -> no new create.
    fw = FakeFW(existing_io={"Frisco King - USA": "95990000"})
    sf = FakeSF(dict(GOOD_PLAN, promoted_title="Frisco King", region="USA"))
    result = process_case("500DUP", sf=sf, fw=fw, create=True)
    assert result.ok and result.io_id == "95990000"
    assert not fw.created                                    # nothing re-created
    assert sf.reason["500DUP"] == FakeSF.SUBMITTED_REASON
    assert "no duplicate" in sf.comments[0][1].lower()


def test_io_url():
    assert io_url("520311", "86543608", "95999001").endswith(
        "campaigns/86543608/?insertion_order_id=95999001")
