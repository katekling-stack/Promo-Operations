"""Salesforce client — read the Case that originates a campaign.

Long-term, the Salesforce Case is the source of truth for campaign inputs. This
client reads a Case and normalizes its fields into the same dict shape that
plan_loader.support_plan_from_dict() consumes, so a Case and a YAML plan are
interchangeable downstream.

The field API names below are placeholders — map them to your Case layout. They are
marked `# MAP:`. Uses simple-salesforce (install with the `salesforce` extra).
"""

from __future__ import annotations

from typing import Any

from ..config import require_env


# MAP: Salesforce Case field API name -> support-plan key.
CASE_FIELD_MAP = {
    "Promoted_Title__c": "promoted_title",
    "Region__c": "region",
    "Brand__c": "brand",
    "Flight_Start__c": ("flight", "start"),
    "Flight_End__c": ("flight", "end"),
    "Video_Assets__c": ("formats_flag", "remnant_video"),
    "Pause_Ad_Assets__c": ("formats_flag", "pause_ads"),
    "Showlist__c": "showlist",           # expected multi-line / semicolon list
    "Genres__c": "genres",
    "Networks__c": "networks",
    "Pluto_Channels__c": ("pluto", "channels"),
    "Pluto_Categories__c": ("pluto", "categories"),
}


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
    def __init__(self):
        self._sf = _connect()

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._sf.Case.get(case_id)

    def case_to_plan_dict(self, case_id: str) -> dict[str, Any]:
        """Read a Case and normalize into a support-plan dict. CONFIRM field map."""
        case = self.get_case(case_id)
        plan: dict[str, Any] = {"salesforce_case": case_id, "formats": []}
        for sf_field, target in CASE_FIELD_MAP.items():
            value = case.get(sf_field)
            if value is None:
                continue
            if isinstance(target, tuple) and target[0] == "formats_flag":
                if value:
                    plan["formats"].append(target[1])
            elif isinstance(target, tuple):
                plan.setdefault(target[0], {})[target[1]] = _split(value)
            else:
                plan[target] = _split(value) if target in _LIST_FIELDS else value
        return plan


_LIST_FIELDS = {"showlist", "genres", "networks"}


def _split(value: Any) -> Any:
    """Split a Salesforce multi-value text field into a list."""
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("\n", ";").split(";")]
        return [p for p in parts if p]
    return value
