# Salesforce Admin — Build Sheet (one page)

Everything the Salesforce admin needs to do to enable the Case → FreeWheel automation.
The tool is built and running; this is the only Salesforce-side work.

## A. Create fields on the **Case** object
Import from **`docs/salesforce-case-fields.csv`** (API names, types, picklist values,
help text — generated from live config). Start with the **7 required**; the rest can
follow.

**Minimal (7 — do these first):**
| Field Label | API Name | Type | Picklist |
|---|---|---|---|
| Promoted Title | `Promoted_Title__c` | Text (120) | — |
| Region | `Region__c` | Picklist | USA, CA, AU, LATAM, BR, UK, IE, FR, IT, GSA, FI, DK, NO, SE, ES |
| Language | `Language__c` | Picklist | English, French |
| Campaign Name | `Campaign_Name__c` | Picklist | 153 values (in CSV) |
| Flight Start | `Flight_Start__c` | Date | — |
| Flight End | `Flight_End__c` | Date | — |
| Video Durations | `Video_Durations__c` | Text (50) | e.g. `30;15` |

**Then (28 more):** 10 optional creative/product selectors, 10 Yes/No product toggles,
8 auto-derived override fields — all in the CSV.

## B. Add picklist **values** (to existing Status/Reason fields — not new fields)
| Field | Value |
|---|---|
| Status | `Ready for Automation` |
| Status | `Needs Info` |
| Reason | `Submitted to FreeWheel` |

## C. Access for the integration
- A **sandbox** to build/test in.
- A **Connected App** *or* integration user (username + password + security token) that
  can: read Cases + these fields, and write Status/Reason + add a Case comment.

## D. Confirm
- We can **attach and read a "Targeting" sheet** on a Case (holds the variable-length
  targeting lists: showlist, genres, Pluto channels/categories).
- Any **API-name conventions** to follow — if so, tell us and we map them on our side
  (one file), no rework for you.

## Acceptance check (how we know it's done)
We run `promo-ops salesforce-check` — it logs in and reports any missing field or
picklist value. **Green = ready.** That's the single go/no-go signal.

---
*Fields regenerate from config any time with `python scripts/build_salesforce_fields.py`
→ `docs/salesforce-case-fields.csv`. Full detail + rationale in
`docs/SALESFORCE_FIELD_MAPPING.md`.*
