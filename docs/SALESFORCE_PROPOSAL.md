# Salesforce → FreeWheel Automation — Proposal

**Audience:** Salesforce admin / rep, Promo Ad Ops.
**Goal:** Let a planner request a promo campaign entirely from a Salesforce **Case**,
and have the FreeWheel Insertion Order + Placements built automatically — with the
result (draft IO link + any to-dos) posted back on the Case.

This document is everything needed to scope the Salesforce side before we wire it up.

> **Where the build is today (Aug 2026).** The engine is live and verified end-to-end
> against **FreeWheel production**: from a campaign plan it builds the full Order +
> per-tier Placements and creates them as NOT_BOOKED drafts that populate with the
> correct tiering, targeting, ad units, geo, and exclusions. Coverage is **15 regions
> and ~80 promo brands** (US, CA, UK, IE, AU, LATAM, BR, and 8 EU markets — Paramount+,
> Pluto TV, CBS, MTVE, BET, Nick/Nick Jr, Paramount Pictures/Consumer Products), each
> reverse-engineered from its live IOs. Video Dominations + Operative takeovers are
> built too. **The only thing standing between "runs in tests" and "runs from a real
> Case" is the Salesforce configuration in this doc.**

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

- **Core fields → custom fields on the Case** (the "form"). A fixed set of scalars —
  title, region, campaign, flight dates, durations, products, etc. Picklists and text
  boxes on the Case layout. See §3.
- **Detailed targeting → one file attached to the Case.** The long, per-campaign lists
  (showlist, genres, Pluto channels/categories) go in the standard **Targeting** sheet
  and are attached to the Case. The automation downloads and parses it.

Why split it: the core is a stable set of fields worth making native (validation,
reporting, picklists); the targeting is dozens of free-text rows that would be painful
as Case fields and is already maintained as a sheet.

## 3. Custom fields to add to the Case

> **The authoritative field list is the attached [`salesforce-case-fields.csv`](salesforce-case-fields.csv).**
> It is **generated from the live automation config**, so it always lists every field
> the code reads, with the exact API name, type, and **current picklist values for all
> 15 regions and every campaign/brand/format**. The tables below summarize it by group;
> the CSV is what the admin builds from (regenerate any time with
> `python scripts/build_salesforce_fields.py`).

Picklist values are the exact keys the automation expects — create them verbatim.
"Required" = planner fills every time; "Override" = normally blank, only set to
override the value auto-derived from the Campaign.

### Required
| Label | API Name | Type | Notes |
|---|---|---|---|
| Promoted Title | `Promoted_Title__c` | Text(120) | The title being promoted. |
| Region | `Region__c` | Picklist | 15 values: `USA, CA, UK, IE, AU, LATAM, BR, FR, IT, GSA, FI, DK, NO, SE, ES`. |
| Campaign Name | `Campaign_Name__c` | Picklist | The existing FreeWheel campaign the IO nests under — **the key field** (drives Brand / Advertiser / default Formats). ~70 values; see CSV. |
| Language | `Language__c` | Picklist | `English`, `French` — routes multi-language regions (Canada) to the FR vs EN advertiser. |
| Flight Start / End | `Flight_Start__c` / `Flight_End__c` | Date | Campaign flight. |
| Video Durations | `Video_Durations__c` | Text(50) | Seconds, semicolon-separated (e.g. `30;15`). |

### Optional (fill when relevant)
| Label | API Name | Type | Notes |
|---|---|---|---|
| Season or Messaging | `Season_or_Messaging__c` | Text(80) | Middle segment of placement names. |
| Content Type / Content ID | `Content_Type__c` / `Content_ID__c` | Picklist / Text | `show`\|`movie`; ShowID/MovieID for guaranteed lines. |
| Recommended Show ID | `Recommended_Show_ID__c` | Text(40) | Defaults to Content ID. |
| Flight Code | `Flight_Code__c` | Text(20) | Launch beat / flight code. |
| **Kids Audience** | `Kids_Audience__c` | Multi-select | `older`, `younger` — Kids brands only; empty = no Kids IOs. |
| **Rating Restrictions** | `Rating_Restrictions__c` | Long Text | AU Network 10 only: VG rating-restriction values to exclude. |
| Video Domination | `Video_Domination__c` | Picklist | `pluto`, `standard`, `aus_10_streaming`, `uk_my5`. |
| Video Domination Targeting | `Video_Domination_Targeting__c` | Long Text | Pluto categories (Pluto VD only). |
| Takeover | `Takeover__c` | Picklist | `hpto`, `first_impression`, `arena_takeover`, `three_peat`. |

### Products (Yes / No toggles — blank = the brand's default set)
One picklist (`Yes; No`) per product; blank leaves the brand default. Lets a planner
add/drop a product per campaign without touching Formats.

`Include_Remnant_Video__c`, `Include_Pause_Ads__c`, `Include_Premium_Pre_Roll__c`,
`Include_Essential_Bumper__c`, `Include_CBS_Pre_Roll__c`,
`Include_After_Mid_Roll_Bumper__c`, `Include_1Z_Lockdown__c`, `Include_2Z_Lockdown__c`,
`Include_Pluto__c` (UK P+ only), `Include_Network_10__c` (AU only).

### Overrides (normally blank — auto-derived from the Campaign)
`Brand__c`, `Advertiser__c`, `Advertiser_ID__c`, `Campaign_ID__c`,
`Insertion_Order_Name__c`, `Recommended_Show__c`, `Exclude_Show__c`, `Formats__c`
(multi-select). Picking the Campaign auto-derives all of these — see the CSV for the
full picklist values.

> These API names are what the code maps today (`CASE_FIELD_MAP` in
> `integrations/salesforce.py`). If your org has naming conventions, we rename them
> there in one place — the CSV and parser stay in sync.

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
  Categories | Pluto Channels** (+ optional **Audience Segments** (Tier 1) and **Kids
  Audience** columns).
- Pluto category/channel names are **region-specific** — the CM uses the region's real
  names (reference: `docs/PLUTO_TARGETING_NAMES.md`).
- We provide the blank master sheet; the planner copies it per campaign, fills it, and
  attaches it. Excel is fine if saved/exported as CSV (or we add an xlsx reader).

## 6. What the automation posts back

On success, a Case comment with the **FreeWheel draft IO link**, the number of
placements created, and any **manual to-dos** for the assigned CM (e.g. "add the
`recommended_show` value in the UI"). The draft is created but **not launched** — a
person still reviews and activates it in FreeWheel, keeping a human in the loop.

## 7. What we need from the Salesforce side

1. **Create the fields in [`salesforce-case-fields.csv`](salesforce-case-fields.csv)**
   (§3) — approve the API names (or give us yours) and add the custom fields + picklist
   values on the Case object.
2. **Add the Status/Reason values in §4** (or point us at existing equivalents).
3. **API access** — a Connected App (OAuth) *or* an integration user + security token, with:
   Read on Case + custom fields, Read on Files/ContentDocument, Create on CaseComment,
   Edit on Case Status/Reason.
4. **A Sandbox** to build and test against before production.
5. Confirm the **Case record type / layout** planners will use.

We don't need any of this to keep building — the Case→plan transform is written and
unit-tested against sample Cases (design-first). Items 1–5 flip it from "runs in tests"
to "runs against your real org." Run `promo-ops salesforce-check` once creds land to
verify the org has every field + picklist value (see `docs/SALESFORCE_GOLIVE.md`).

## 8. Suggested phasing

1. **Now:** team reviews this proposal + the field CSV; we align on names.
2. **Sandbox:** admin creates fields/picklists + a test Connected App; `salesforce-check`
   goes green; we run a sample Case end-to-end (creating a FreeWheel *draft*).
3. **Pilot:** one brand (e.g. Paramount+ Domestic), a handful of real Cases, human-reviewed.
4. **Rollout:** enable remaining brands/regions; add the Operative→GAM VD + takeover path.

---

*Reference: field mapping + generated spec in `src/promo_ops/integrations/salesforce.py`
(`CASE_FIELD_MAP`, `CASE_FIELD_SPEC`); end-to-end Case flow in `src/promo_ops/casework.py`;
go-live runbook in `docs/SALESFORCE_GOLIVE.md`. The Case→plan transform is unit-tested
with no live Salesforce dependency.*
