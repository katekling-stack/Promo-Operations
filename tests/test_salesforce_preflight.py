"""Salesforce preflight schema check (design-first; no live Salesforce)."""

from promo_ops.integrations.salesforce import (
    EXPECTED_CASE_FIELDS,
    SalesforceClient,
    check_case_schema,
)


def _describe(field_names, status_values, reason_values):
    """Build a minimal Case describe() payload like the SF API returns."""
    fields = [{"name": n} for n in field_names]
    fields.append({"name": "Status",
                   "picklistValues": [{"value": v} for v in status_values]})
    fields.append({"name": "Reason",
                   "picklistValues": [{"value": v} for v in reason_values]})
    return {"fields": fields}


def test_fully_provisioned_org_passes():
    describe = _describe(
        EXPECTED_CASE_FIELDS,
        [SalesforceClient.READY_STATUS, SalesforceClient.NEEDS_INFO_STATUS, "New"],
        [SalesforceClient.SUBMITTED_REASON, "Other"],
    )
    report = check_case_schema(describe)
    assert report.ok
    assert report.missing_fields == []
    assert set(report.present_fields) == set(EXPECTED_CASE_FIELDS)


def test_missing_fields_and_picklist_values_are_reported():
    # Drop two required fields and both hand-off values.
    present = [f for f in EXPECTED_CASE_FIELDS
              if f not in ("Promoted_Title__c", "Takeover__c")]
    describe = _describe(present, ["New", "Working"], ["Other"])
    report = check_case_schema(describe)

    assert not report.ok
    assert "Promoted_Title__c" in report.missing_fields
    assert "Takeover__c" in report.missing_fields
    assert SalesforceClient.READY_STATUS in report.status_values_missing
    assert SalesforceClient.NEEDS_INFO_STATUS in report.status_values_missing
    assert SalesforceClient.SUBMITTED_REASON in report.reason_values_missing
    # The rendered report names the missing pieces so the admin can act.
    text = report.render()
    assert "Promoted_Title__c" in text
    assert "Submitted to FreeWheel" in text
