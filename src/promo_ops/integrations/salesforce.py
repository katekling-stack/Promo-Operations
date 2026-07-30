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
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import env, require_env
from .gsheets import parse_targeting_tab

# MAP: Salesforce Case field API name -> support-plan key (nested via tuple).
# Core (non-targeting) inputs; mirrors the Plan tab of the template.
CASE_FIELD_MAP: dict[str, Any] = {
    "Promoted_Title__c": "promoted_title",
    "Region__c": "region",
    "Language__c": "language",          # English | French (CA routing)
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
    "Flight_Code__c": ("flight", "code"),
    "Formats__c": "formats",                     # list
    "Video_Domination__c": "video_domination",   # option key (pluto / standard / ...)
    "Video_Domination_Targeting__c": "video_domination_targeting",  # list (Pluto cats)
    "Kids_Audience__c": "kids_audience",          # list: older / younger (Kids brands)
    "Rating_Restrictions__c": "rating_restrictions",  # list: VG values (AU Network 10)
    "Takeover__c": "takeover",                    # hpto / first_impression / ...
    # Products section — Yes/No/(blank) toggles; blank leaves the brand default.
    "Include_Remnant_Video__c": ("product_overrides", "remnant_video"),
    "Include_Pause_Ads__c": ("product_overrides", "pause_ads"),
    "Include_Premium_Pre_Roll__c": ("product_overrides", "premium_preroll"),
    "Include_Essential_Bumper__c": ("product_overrides", "essential_bumper"),
    "Include_CBS_Pre_Roll__c": ("product_overrides", "cbs_preroll"),
    "Include_After_Mid_Roll_Bumper__c": ("product_overrides", "after_midroll_bumper"),
    "Include_1Z_Lockdown__c": ("product_overrides", "cbs_1z_lockdown"),
    "Include_2Z_Lockdown__c": ("product_overrides", "cbs_2z_lockdown"),
    "Include_Pluto__c": ("product_overrides", "pluto_breakout"),   # UK P+ only
    "Include_Network_10__c": ("product_overrides", "network_10"),  # AU P+ only
}

# Tuple targets under this key hold Yes/No/(blank) toggles -> bool.
_BOOL_TARGET_ROOT = "product_overrides"
_TRUE_TEXT = {"yes", "y", "true", "1", "x", "✓", "checked"}

# --------------------------------------------------------------------------- #
# Case field SPEC — the admin build sheet, generated from the live config so it
# never drifts. Each entry: (API name, Section, Label, Data Type, picklist source,
# Required, Help). `picklist` is either a literal "a; b" string, or a dynamic key
# resolved from config at build time: regions | campaigns | brands | formats.
# `build_case_field_rows()` fills the dynamic ones. Keys mirror CASE_FIELD_MAP.
# --------------------------------------------------------------------------- #
CASE_FIELD_SPEC: list[dict[str, Any]] = [
    dict(api="Promoted_Title__c", section="Required", label="Promoted Title", type="Text",
         picklist="120", required="Yes", help="The title being promoted."),
    dict(api="Region__c", section="Required", label="Region", type="Picklist",
         picklist="regions", required="Yes", help="Campaign region."),
    dict(api="Language__c", section="Required", label="Language", type="Picklist",
         picklist="English; French", required="No",
         help="Routes multi-language regions (Canada) to the FR vs EN advertiser/campaign."),
    dict(api="Campaign_Name__c", section="Required", label="Campaign Name", type="Picklist",
         picklist="campaigns", required="Yes",
         help="Existing FreeWheel campaign the new IO nests under. Drives Brand / Advertiser / default Formats."),
    dict(api="Flight_Start__c", section="Required", label="Flight Start", type="Date",
         picklist="", required="Yes", help="Campaign flight start."),
    dict(api="Flight_End__c", section="Required", label="Flight End", type="Date",
         picklist="", required="Yes", help="Campaign flight end."),
    dict(api="Video_Durations__c", section="Required", label="Video Durations", type="Text",
         picklist="50", required="Yes",
         help="Seconds; semicolon-separated (e.g. 30;15). One placement per tier per duration."),
    dict(api="Season_or_Messaging__c", section="Optional", label="Season or Messaging", type="Text",
         picklist="80", required="No", help="Middle segment of placement names."),
    dict(api="Content_Type__c", section="Optional", label="Content Type", type="Picklist",
         picklist="show; movie", required="No", help="Selects guaranteed token [ShowID:] vs [MovieID:]."),
    dict(api="Content_ID__c", section="Optional", label="Content ID", type="Text",
         picklist="40", required="No", help="ShowID / MovieID for guaranteed placements."),
    dict(api="Recommended_Show_ID__c", section="Optional", label="Recommended Show ID", type="Text",
         picklist="40", required="No", help="recommended_show key-value; defaults to Content ID."),
    dict(api="Flight_Code__c", section="Optional", label="Flight Code", type="Text",
         picklist="20", required="No", help="Launch beat / flight code; used in placement names."),
    dict(api="Kids_Audience__c", section="Optional", label="Kids Audience", type="Multi-Select Picklist",
         picklist="older; younger", required="No",
         help="Kids brands only: which age group(s) to build. Empty = no Kids IOs."),
    dict(api="Rating_Restrictions__c", section="Optional", label="Rating Restrictions",
         type="Long Text Area", picklist="255", required="No",
         help="AU Network 10 only: VG rating-restriction values to exclude; semicolon-separated."),
    dict(api="Video_Domination__c", section="Optional", label="Video Domination", type="Picklist",
         picklist="pluto; standard; aus_10_streaming; uk_my5", required="No",
         help="Video Domination product selector."),
    dict(api="Video_Domination_Targeting__c", section="Optional", label="Video Domination Targeting",
         type="Long Text Area", picklist="255", required="No",
         help="Pluto categories; semicolon-separated (Pluto VD only)."),
    dict(api="Takeover__c", section="Optional", label="Takeover", type="Picklist",
         picklist="hpto; first_impression; arena_takeover; three_peat", required="No",
         help="Operative to GAM takeover type."),
    # Products — one Yes/No toggle each (blank = brand default).
    dict(api="Include_Remnant_Video__c", section="Products", label="Include Remnant Video"),
    dict(api="Include_Pause_Ads__c", section="Products", label="Include Pause Ads"),
    dict(api="Include_Premium_Pre_Roll__c", section="Products", label="Include Premium Pre-Roll"),
    dict(api="Include_Essential_Bumper__c", section="Products", label="Include Essential Bumper"),
    dict(api="Include_CBS_Pre_Roll__c", section="Products", label="Include CBS Pre-Roll"),
    dict(api="Include_After_Mid_Roll_Bumper__c", section="Products", label="Include After Mid-Roll Bumper"),
    dict(api="Include_1Z_Lockdown__c", section="Products", label="Include 1Z Lockdown"),
    dict(api="Include_2Z_Lockdown__c", section="Products", label="Include 2Z Lockdown"),
    dict(api="Include_Pluto__c", section="Products", label="Include Pluto (UK P+ only)"),
    dict(api="Include_Network_10__c", section="Products", label="Include Network 10 (AU only)"),
    # Overrides — auto-derived; set only if needed.
    dict(api="Brand__c", section="Override", label="Brand", type="Picklist",
         picklist="brands", required="No", help="Auto-derived from Campaign; override only if needed."),
    dict(api="Advertiser__c", section="Override", label="Advertiser", type="Text",
         picklist="120", required="No", help="Auto-derived from Brand; exact advertiser name."),
    dict(api="Advertiser_ID__c", section="Override", label="Advertiser ID", type="Text",
         picklist="40", required="No", help="Auto-derived; FreeWheel advertiser id."),
    dict(api="Campaign_ID__c", section="Override", label="Campaign ID", type="Text",
         picklist="40", required="No", help="Auto-derived from Campaign Name; use when name is ambiguous."),
    dict(api="Insertion_Order_Name__c", section="Override", label="Insertion Order Name", type="Text",
         picklist="160", required="No", help="Auto-derived; defaults to {Title} - {Region}."),
    dict(api="Recommended_Show__c", section="Override", label="Recommended Show", type="Text",
         picklist="120", required="No", help="Auto-derived; defaults to Promoted Title."),
    dict(api="Exclude_Show__c", section="Override", label="Exclude Show", type="Text",
         picklist="120", required="No", help="Auto-derived; defaults to Promoted Title (self-exclusion)."),
    dict(api="Formats__c", section="Override", label="Formats", type="Multi-Select Picklist",
         picklist="formats", required="No", help="Auto-derived from Brand's format set; override the full set only if needed."),
]

# Status/Reason picklist VALUES the automation needs added (not fields).
CASE_STATUS_REASON_VALUES = [
    ("Status", "Ready for Automation", "Planner sets this to trigger the automation."),
    ("Status", "Needs Info", "Automation sets this (+ comment) when a Case can't be built."),
    ("Reason", "Submitted to FreeWheel", "Automation sets this after the draft IO is created."),
]


def _dynamic_picklist(source: str) -> str:
    """Resolve a dynamic picklist source key to a '; '-joined value string from config."""
    from ..config import brands_config, regions_config, placement_templates_config
    if source == "regions":
        return "; ".join(regions_config().get("regions", {}).keys())
    if source == "brands":
        return "; ".join(brands_config().get("brands", {}).keys())
    if source == "campaigns":
        names = [b.get("campaign_name") for b in brands_config().get("brands", {}).values()
                 if b.get("campaign_name")]
        return "; ".join(sorted(set(names)))
    if source == "formats":
        return "; ".join(placement_templates_config().get("formats", {}).keys())
    return source


def build_case_field_rows() -> list[dict[str, str]]:
    """The admin build sheet rows, with dynamic picklists resolved from the live config.

    Single source of truth for docs/salesforce-case-fields.csv — regenerate whenever
    brands/regions/formats change so the Salesforce object spec never drifts."""
    dynamic = {"regions", "brands", "campaigns", "formats"}
    rows: list[dict[str, str]] = []
    for spec in CASE_FIELD_SPEC:
        if spec["section"] == "Products":                     # Yes/No toggle defaults
            spec = {**spec, "type": "Picklist", "picklist": "Yes; No", "required": "No",
                    "help": "Products toggle; blank = brand default."}
        picklist = spec.get("picklist", "")
        values = _dynamic_picklist(picklist) if picklist in dynamic else picklist
        rows.append({
            "Object": "Case", "Section": spec["section"], "Field Label": spec["label"],
            "API Name": spec["api"], "Data Type": spec.get("type", "Text"),
            "Length / Picklist Values": values, "Required (planner)": spec.get("required", "No"),
            "Help Text": spec.get("help", ""),
        })
    return rows

# Core fields that are semicolon/newline lists.
_LIST_FIELDS = {"durations", "formats", "video_domination_targeting", "kids_audience",
                "rating_restrictions"}


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
            if target[0] == _BOOL_TARGET_ROOT:
                value = value is True or str(value).strip().lower() in _TRUE_TEXT
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
    # Sandbox vs production is a login-domain switch: sandbox logs in at
    # test.salesforce.com (domain="test"). Set SALESFORCE_DOMAIN=test for the sandbox.
    kwargs: dict[str, Any] = {
        "username": require_env("SALESFORCE_USERNAME"),
        "password": require_env("SALESFORCE_PASSWORD"),
        "domain": env("SALESFORCE_DOMAIN", "login"),
    }
    # Security token is optional (orgs with IP relaxation don't need it).
    token = env("SALESFORCE_SECURITY_TOKEN")
    if token:
        kwargs["security_token"] = token
    # A Connected App (consumer key/secret) is optional; include it when provided.
    if env("SALESFORCE_CLIENT_ID"):
        kwargs["consumer_key"] = env("SALESFORCE_CLIENT_ID")
    if env("SALESFORCE_CLIENT_SECRET"):
        kwargs["consumer_secret"] = env("SALESFORCE_CLIENT_SECRET")
    if env("SALESFORCE_INSTANCE_URL"):
        kwargs["instance_url"] = env("SALESFORCE_INSTANCE_URL")
    return Salesforce(**kwargs)


# The Case fields the automation reads (API names) = the keys of CASE_FIELD_MAP.
EXPECTED_CASE_FIELDS: list[str] = list(CASE_FIELD_MAP.keys())


@dataclass
class SchemaReport:
    """Result of checking a Case describe payload against what the automation needs."""
    present_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    status_values_missing: list[str] = field(default_factory=list)
    reason_values_missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_fields or self.status_values_missing
                    or self.reason_values_missing)

    def render(self) -> str:
        lines = []
        lines.append(f"Case fields: {len(self.present_fields)}/"
                     f"{len(self.present_fields) + len(self.missing_fields)} present.")
        if self.missing_fields:
            lines.append("  MISSING fields (create these on the Case object):")
            lines += [f"    - {f}" for f in self.missing_fields]
        if self.status_values_missing:
            lines.append("  MISSING Status picklist values: "
                         + ", ".join(self.status_values_missing))
        if self.reason_values_missing:
            lines.append("  MISSING Reason picklist values: "
                         + ", ".join(self.reason_values_missing))
        lines.append("✅ Schema OK — the org is ready." if self.ok
                     else "⚠️  Schema incomplete — see above (share docs/salesforce-case-fields.csv).")
        return "\n".join(lines)


def _picklist_values(describe: dict[str, Any], field_name: str) -> set[str]:
    for f in describe.get("fields", []):
        if f.get("name") == field_name:
            return {p.get("value") for p in (f.get("picklistValues") or [])}
    return set()


def check_case_schema(describe: dict[str, Any],
                      status_field: str = "Status", reason_field: str = "Reason",
                      required_status: Optional[list[str]] = None,
                      required_reason: Optional[list[str]] = None) -> SchemaReport:
    """Pure check: does a Case `describe()` payload have the fields + picklist values?

    No Salesforce dependency, so it's unit-tested against a fake describe payload.
    """
    field_names = {f.get("name") for f in describe.get("fields", [])}
    present = [f for f in EXPECTED_CASE_FIELDS if f in field_names]
    missing = [f for f in EXPECTED_CASE_FIELDS if f not in field_names]

    status_vals = _picklist_values(describe, status_field)
    reason_vals = _picklist_values(describe, reason_field)
    req_status = required_status or [SalesforceClient.READY_STATUS,
                                     SalesforceClient.NEEDS_INFO_STATUS]
    req_reason = required_reason or [SalesforceClient.SUBMITTED_REASON]
    return SchemaReport(
        present_fields=present,
        missing_fields=missing,
        status_values_missing=[v for v in req_status if v not in status_vals],
        reason_values_missing=[v for v in req_reason if v not in reason_vals],
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

    def __init__(self, sf: Any = None):
        # `sf` is injectable for tests; otherwise connect for real.
        self._sf = sf if sf is not None else _connect()
        import time as _t
        self._sleep = _t.sleep
        self._retry_attempts = int(env("SALESFORCE_RETRY_ATTEMPTS", "4"))
        self._retry_base_delay = float(env("SALESFORCE_RETRY_BASE_DELAY", "2"))

    def _call(self, fn: Any) -> Any:
        """Run a Salesforce call, retrying transient failures (network, 429/5xx) with
        backoff. Permanent errors (bad SOQL, auth, 4xx) raise immediately."""
        from ..retry import is_transient_exception, with_retries
        return with_retries(fn, attempts=self._retry_attempts,
                            base_delay=self._retry_base_delay,
                            retry_on=is_transient_exception, sleep=self._sleep)

    def preflight(self) -> SchemaReport:
        """Connect and verify the Case has the fields + Status/Reason values we need.

        Run this once the sandbox creds land: `promo-ops salesforce-check`. It logs in
        (proving credentials/access) and describes the Case object (proving the admin
        created the fields and picklist values from docs/salesforce-case-fields.csv).
        """
        describe = self._call(lambda: self._sf.Case.describe())
        return check_case_schema(describe, self.STATUS_FIELD, self.REASON_FIELD)

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._call(lambda: self._sf.Case.get(case_id))

    def list_ready_cases(self) -> list[str]:
        """Case IDs flagged ready for Ad Ops build. CONFIRM the Status value/field."""
        q = self._call(lambda: self._sf.query(
            f"SELECT Id FROM Case WHERE {self.STATUS_FIELD} = '{self.READY_STATUS}'"))
        return [r["Id"] for r in q.get("records", [])]

    def post_case_comment(self, case_id: str, body: str) -> dict[str, Any]:
        """Post a comment back on the Case (IO link + to-dos). CONFIRM comment object."""
        return self._call(lambda: self._sf.CaseComment.create(
            {"ParentId": case_id, "CommentBody": body}))

    def update_case_status(self, case_id: str, status: str) -> dict[str, Any]:
        return self._call(lambda: self._sf.Case.update(case_id, {self.STATUS_FIELD: status}))

    def update_case_reason(self, case_id: str, reason: str) -> dict[str, Any]:
        return self._call(lambda: self._sf.Case.update(case_id, {self.REASON_FIELD: reason}))

    def _targeting_rows(self, case_id: str) -> Optional[list[list[str]]]:
        """Download the Case's attached Targeting sheet as CSV rows.

        CONFIRM: attachment retrieval for your org. Files attached to a Case are
        ContentDocuments linked via ContentDocumentLink; the latest ContentVersion
        holds the bytes. Excel attachments should be exported/saved as CSV, or add an
        xlsx parser here.
        """
        links = self._call(lambda: self._sf.query(
            "SELECT ContentDocumentId FROM ContentDocumentLink "
            f"WHERE LinkedEntityId = '{case_id}'"
        ))
        for row in links.get("records", []):
            doc_id = row["ContentDocumentId"]
            ver = self._call(lambda doc_id=doc_id: self._sf.query(
                "SELECT Id, Title, FileExtension, VersionData FROM ContentVersion "
                f"WHERE ContentDocumentId = '{doc_id}' AND IsLatest = true"
            ))
            for v in ver.get("records", []):
                if self.TARGETING_FILE_HINT.lower() in str(v.get("Title", "")).lower():
                    raw = self._call(lambda v=v: self._sf._call_salesforce(
                        "GET", self._sf.base_url.replace("/services/data/", "")
                        + v["VersionData"]).content)
                    text = raw.decode("utf-8-sig", errors="replace")
                    return list(csv.reader(io.StringIO(text)))
        return None

    def case_to_plan_dict(self, case_id: str) -> dict[str, Any]:
        """Read a Case (core fields) + its attached Targeting sheet -> plan dict."""
        return build_plan_dict(self.get_case(case_id), self._targeting_rows(case_id))
