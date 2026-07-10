# Salesforce → FreeWheel Automation — Proposal

**Audience:** Salesforce admin / rep, Promo Ad Ops.
**Goal:** Let a planner request a promo campaign entirely from a Salesforce **Case**,
and have the FreeWheel Insertion Order + Placements built automatically — with the
result (draft IO link + any to-dos) posted back on the Case.

This document is everything needed to scope the Salesforce side before we wire it up.

---

## 1. How it works (the workflow)

```
Planner fills the Case  ─►  sets Status = "Ready for Automation"
        │                            │
        │                            ▼
        │                 Automation picks it up
        │                            │
        │          ┌─────────────────┴─────────────────┐
        │      success                              can't build
        │          │                                     │
        ▼          ▼                                     ▼
  Case Reason = "Submitted to FreeWheel"        Status = "Needs Info"
  + comment with the FreeWheel IO link          + comment explaining what's missing
    and any manual to-dos for the CM
```

Nothing is created until the planner flips **Status → "Ready for Automation."** That
one flag is the only trigger; everything else is read off the Case.

## 2. Hybrid input model — form + one attachment

The Case captures the request in two parts (this mirrors the two-tab template the
team already reviewed):

- **Core fields → custom fields on the Case** (the "form"). A short, fixed set of
  scalars — title, region, campaign, flight dates, durations, etc. These are picklists
  and text boxes on the Case layout. See §3.
- **Detailed targeting → one file attached to the Case.** The long, per-campaign lists
  (showlist, genres, Pluto channels/categories) go in the standard **Targeting** sheet
  and are attached to the Case. The automation downloads and parses it.

Why split it: the core is ~20 stable fields worth making native (validation,
reporting, picklists); the targeting is dozens of free-text rows that would be painful
as Case fields and is already maintained as a sheet.

## 3. Custom fields to add to the Case

Picklist values below are the exact keys/names the automation expects — please create
them verbatim. "Required" = planner must fill; "Override" = normally blank, only set to
override the value auto-derived from the Campaign.

### Required (planner fills every time)

| Label | API Name | Type | Picklist values / format |
|---|---|---|---|
| Promoted Title | `Promoted_Title__c` | Text(120) | free text |
| Region | `Region__c` | Picklist | `USA`, `CA`, `AU`, `LATAM`, `BR`, `UK` |
| Campaign Name | `Campaign_Name__c` | Picklist | `Paramount + - USA`, `CBS Sports - USA`, `CBS News - USA`, `CBS Network - USA`, `MTVE - USA`, `BET Media Group - USA`, `Pluto TV - USA`, `Pluto TV (Cross-Company) - USA` |
| Flight Start | `Flight_Start__c` | Date | — |
| Flight End | `Flight_End__c` | Date | — |
| Video Durations | `Video_Durations__c` | Text(50) | seconds, semicolon-separated (e.g. `30;15`) |

> **Campaign Name is the key field.** Picking it auto-derives the Brand, Advertiser,
> and default Formats — so the planner rarely touches the Override fields below.

### Optional (planner fills when relevant)

| Label | API Name | Type | Picklist values / format |
|---|---|---|---|
| Season or Messaging | `Season_or_Messaging__c` | Text(80) | free text (goes in placement names) |
| Content Type | `Content_Type__c` | Picklist | `show`, `movie` |
| Content ID | `Content_ID__c` | Text(40) | ShowID / MovieID |
| Recommended Show ID | `Recommended_Show_ID__c` | Text(40) | key-value; defaults to Content ID |
| Flight Code | `Flight_Code__c` | Text(20) | launch beat / flight code |
| Video Domination | `Video_Domination__c` | Picklist | `pluto`, `standard`, `aus_10_streaming`, `uk_my5` |
| Video Domination Targeting | `Video_Domination_Targeting__c` | Long Text | Pluto categories, semicolon-separated (Pluto VD only) |
| Takeover | `Takeover__c` | Picklist | `hpto`, `first_impression`, `arena_takeover`, `three_peat` |

### Overrides (normally blank — auto-derived from the Campaign)

| Label | API Name | Type | Picklist values / format |
|---|---|---|---|
| Brand | `Brand__c` | Picklist | `paramount_plus_domestic`, `cbs_sports`, `cbs_news`, `cbs_network`, `mtve`, `bet`, `pluto_tv`, `pluto_tv_xco` |
| Advertiser | `Advertiser__c` | Text(120) | exact advertiser name |
| Advertiser ID | `Advertiser_ID__c` | Text(40) | FreeWheel advertiser id |
| Campaign ID | `Campaign_ID__c` | Text(40) | FreeWheel campaign id (use when the name is ambiguous) |
| Insertion Order Name | `Insertion_Order_Name__c` | Text(160) | defaults to `{Title} - {Region}` |
| Recommended Show | `Recommended_Show__c` | Text(120) | defaults to Title |
| Exclude Show | `Exclude_Show__c` | Text(120) | defaults to Title |
| Formats | `Formats__c` | Multi-select Picklist | `remnant_video`, `pause_ads`, `premium_preroll`, `essential_bumper`, `cbs_preroll`, `cbs_after_midroll_bumper`, `cbs_1z_lockdown`, `cbs_2z_lockdown`, `mtve_after_midroll_bumper`, `bet_after_midroll_bumper`, `remnant_display`, `podcast` |

> These field API names are what the code maps today (`CASE_FIELD_MAP` in
> `integrations/salesforce.py`). If your org has naming conventions, we can rename them
> there — the API names just need to match on both sides.

## 4. Status / Reason model (the hand-off)

We reuse the standard Case **Status** and **Reason** picklists — please add these values:

| Field | Value to add | Meaning |
|---|---|---|
| Status | **Ready for Automation** | Planner sets this → the automation trigger. |
| Status | **Needs Info** | *Automation sets this* if the Case can't be built; a comment explains why. |
| Reason | **Submitted to FreeWheel** | *Automation sets this* after the draft IO is created. |

(If Ad Ops already has an equivalent Status like "Ready for Trafficking," we can point
the automation at that instead — just tell us the exact label.)

## 5. The attached Targeting sheet

- One file per Case, attached as a Salesforce **File** (ContentDocument). We match it by
  a title containing **"Targeting"**.
- Columns (lists run down each column): **Networks | Genres | Showlist | Pluto
  Categories | Pluto Channels** (+ an optional Tier-1 Audience Segments column, usually
  left blank — segments auto-resolve from the Showlist).
- We'll provide the blank master sheet; the planner copies it per campaign, fills it,
  and attaches it. Excel is fine if it's saved/exported as CSV (or we add an xlsx reader).

## 6. What the automation posts back

On success, a Case comment with:
- the **FreeWheel draft IO link**,
- the number of placements created, and
- any **manual to-dos** for the assigned CM (e.g. "add the `recommended_show` value in
  the UI," "confirm creative durations").

The draft is created but **not launched** — a person still reviews and activates it in
FreeWheel. This keeps a human in the loop for go-live.

## 7. What we need from the Salesforce side

To move forward, from the admin/rep:

1. **Confirm the fields in §3** — approve the API names (or give us your preferred
   names) and create the custom fields + picklist values on the Case object.
2. **Add the Status/Reason values in §4** (or point us at existing equivalents).
3. **API access** — a Connected App (OAuth) *or* an integration user + security token,
   with:
   - Read on Case + the custom fields,
   - Read on Files/ContentDocument (to fetch the attached Targeting sheet),
   - Create on CaseComment, and Edit on Case Status/Reason (to write results back).
4. **A Sandbox** to build and test against before touching production.
5. Confirm the **Case record type / layout** planners will use, so the fields land on
   the right page layout.

We don't need any of the above to keep building — the transform that turns a Case into
a FreeWheel order is already written and unit-tested against fake Case data
(design-first). Items 1–5 are what flip it from "runs in tests" to "runs against your
real org."

## 8. Suggested phasing

1. **Now:** rep reviews this proposal + the field list; we align on names.
2. **Sandbox:** admin creates fields/picklists + a test Connected App; we connect and
   run end-to-end against a sample Case (creating a FreeWheel *draft*).
3. **Pilot:** one brand (Paramount+ Domestic), a handful of real Cases, human-reviewed.
4. **Rollout:** enable remaining brands; optionally add the Operative→GAM takeover path.

---

*Reference: field mapping lives in `src/promo_ops/integrations/salesforce.py`
(`CASE_FIELD_MAP`, `STATUS_FIELD`/`REASON_FIELD`); the end-to-end Case flow is in
`src/promo_ops/casework.py`. The pure Case→plan transform is unit-tested with no live
Salesforce dependency.*
