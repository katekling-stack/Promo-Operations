"""Salesforce client — build a support plan from a Case (hybrid input).

The Salesforce Case is the source of truth for a campaign. We use a HYBRID model:
  * Core fields live on the Case record (title, region, brand, advertiser/campaign,
    flight, formats, IDs) — mapped by CASE_FIELD_MAP below.
  * The detailed targeting (showlist, genres, networks, Pluto channels/categories)
    is filled into the standard Targeting template and attached to the Case; we
    download and parse it with the same parser the sheet/YAML paths use.

Both are merged into the plan-dict shape `plan_loader.support_plan_from_dict()`
consumes, so a Case, a sheet, and a YAML plan are interchangeable downstream.

Design-first: the pure transform `build_plan_dict()` needs no Salesforce and is
unit-tested; the live fetch (`case_to_plan_dict`) wraps it. Field API names are
placeholders — map them to your Case layout (marked `# MAP:`). Uses
simple-salesforce (install with the `salesforce` extra).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Optional

from ..config import require_env
from .gsheets import parse_targeting_tab

# MAP: Salesforce Case field API name -> support-plan key (nested via tuple).
# Core (non-targeting) inputs; mirrors the Plan tab of the template.
CASE_FIELD_MAP: dict[str, Any] = {
    "Promoted_Title__c": "promoted_title",
    "Region__c": "region",
    "Brand__c": "brand",
    "Advertiser__c": ("advertiser", "name"),
    "Advertiser_ID__c": ("advertiser", "resolved_id"),
    "Campaign_Name__c": ("campaign", "name"),
    "Campaign_ID__c": ("campaign", "resolved_id"),
    "Insertion_Order_Name__c": "insertion_order_name",
    "Recommended_Show__c": "recommended_show",
    "Recommended_Show_ID__c": "recommended_show_id",
    "Exclude_Show__c": "exclude_show",
    "Season_or_Messaging__c": "season_or_messaging",
    "Video_Durations__c": "durations",          # list
    "Content_Type__c": "content_type",           # show | movie
    "Content_ID__c": "content_id",
    "Flight_Start__c": ("flight", "start"),
    "Flight_End__c": ("flight", "end"),
    "Formats__c": "formats",                     # list
    "Video_Domination__c": "video_domination",   # option key (pluto / standard / ...)
    "Video_Domination_Targeting__c": "video_domination_targeting",  # list (Pluto cats)
}

# Core fields that are semicolon/newline lists.
_LIST_FIELDS = {"durations", "formats", "video_domination_targeting"}


def _split(value: Any) -> Any:
    """Split a Salesforce multi-value text field into a trimmed list."""
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("\n", ";").split(";")]
        return [p for p in parts if p]
    return value


def build_plan_dict(case_fields: dict[str, Any],
                    targeting_rows: Optional[list[list[str]]] = None) -> dict[str, Any]:
    """Pure transform: Case fields (+ attached Targeting rows) -> plan dict.

    No Salesforce dependency, so this is the unit-tested core. `targeting_rows` is
    the attached Targeting sheet as rows (header + data), parsed by the shared
    `parse_targeting_tab`.
    """
    plan: dict[str, Any] = {}
    case_id = case_fields.get("Id") or case_fields.get("CaseNumber")
    if case_id:
        plan["salesforce_case"] = case_id

    for sf_field, target in CASE_FIELD_MAP.items():
        value = case_fields.get(sf_field)
        if value in (None, ""):
            continue
        if isinstance(target, tuple):
            plan.setdefault(target[0], {})[target[1]] = value
        else:
            plan[target] = _split(value) if target in _LIST_FIELDS else value

    # Merge the attached targeting sheet (showlist / genres / networks / pluto).
    if targeting_rows:
        targeting = parse_targeting_tab(targeting_rows)
        for key, value in targeting.items():
            if key == "pluto":
                plan.setdefault("pluto", {}).update(value)
            else:
                plan[key] = value
    return plan


def _connect():
    try:
        from simple_salesforce import Salesforce
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "simple-salesforce not installed. Run: pip install -e '.[salesforce]'"
        ) from exc
    return Salesforce(
        instance_url=require_env("SALESFORCE_INSTANCE_URL"),
        consumer_key=require_env("SALESFORCE_CLIENT_ID"),
        consumer_secret=require_env("SALESFORCE_CLIENT_SECRET"),
        username=require_env("SALESFORCE_USERNAME"),
        password=require_env("SALESFORCE_PASSWORD"),
        security_token=require_env("SALESFORCE_SECURITY_TOKEN"),
    )


class SalesforceClient:
    # MAP: the attached Targeting file is matched by this name fragment (Title).
    TARGETING_FILE_HINT = "Targeting"
    # MAP: the hand-off uses two Case fields:
    #   Status  — trigger: planner sets READY_STATUS when done; we set NEEDS_INFO_STATUS
    #             (+ a comment) if we can't build it.
    #   Reason  — outcome: we set SUBMITTED_REASON after creating the draft.
    STATUS_FIELD = "Status"
    REASON_FIELD = "Reason"
    READY_STATUS = "Ready for Automation"
    NEEDS_INFO_STATUS = "Needs Info"
    SUBMITTED_REASON = "Submitted to FreeWheel"

    def __init__(self):
        self._sf = _connect()

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._sf.Case.get(case_id)

    def list_ready_cases(self) -> list[str]:
        """Case IDs flagged ready for Ad Ops build. CONFIRM the Status value/field."""
        q = self._sf.query(
            f"SELECT Id FROM Case WHERE {self.STATUS_FIELD} = '{self.READY_STATUS}'")
        return [r["Id"] for r in q.get("records", [])]

    def post_case_comment(self, case_id: str, body: str) -> dict[str, Any]:
        """Post a comment back on the Case (IO link + to-dos). CONFIRM comment object."""
        return self._sf.CaseComment.create({"ParentId": case_id, "CommentBody": body})

    def update_case_status(self, case_id: str, status: str) -> dict[str, Any]:
        return self._sf.Case.update(case_id, {self.STATUS_FIELD: status})

    def update_case_reason(self, case_id: str, reason: str) -> dict[str, Any]:
        return self._sf.Case.update(case_id, {self.REASON_FIELD: reason})

    def _targeting_rows(self, case_id: str) -> Optional[list[list[str]]]:
        """Download the Case's attached Targeting sheet as CSV rows.

        CONFIRM: attachment retrieval for your org. Files attached to a Case are
        ContentDocuments linked via ContentDocumentLink; the latest ContentVersion
        holds the bytes. Excel attachments should be exported/saved as CSV, or add an
        xlsx parser here.
        """
        links = self._sf.query(
            "SELECT ContentDocumentId FROM ContentDocumentLink "
            f"WHERE LinkedEntityId = '{case_id}'"
        )
        for row in links.get("records", []):
            doc_id = row["ContentDocumentId"]
            ver = self._sf.query(
                "SELECT Id, Title, FileExtension, VersionData FROM ContentVersion "
                f"WHERE ContentDocumentId = '{doc_id}' AND IsLatest = true"
            )
            for v in ver.get("records", []):
                if self.TARGETING_FILE_HINT.lower() in str(v.get("Title", "")).lower():
                    raw = self._sf._call_salesforce("GET", self._sf.base_url.replace(
                        "/services/data/", "") + v["VersionData"]).content
                    text = raw.decode("utf-8-sig", errors="replace")
                    return list(csv.reader(io.StringIO(text)))
        return None

    def case_to_plan_dict(self, case_id: str) -> dict[str, Any]:
        """Read a Case (core fields) + its attached Targeting sheet -> plan dict."""
        return build_plan_dict(self.get_case(case_id), self._targeting_rows(case_id))
