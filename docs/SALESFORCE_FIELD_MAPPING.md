# Salesforce → FreeWheel Automation — Field Mapping

**Purpose:** what needs to be built on the Salesforce **Case** object so a planner can
fill out a Case, flag it, and the automation creates the FreeWheel draft Order +
Placements automatically. This is the up-to-date spec (generated from the live config —
153 campaigns across 15 regions).

**Companion file:** `docs/salesforce-case-fields.csv` — the same 35 fields as an
import-ready sheet for the SF admin (Object, Section, API Name, Data Type, Picklist
Values, Required, Help Text).

---

## 1. How it works (the flow)

```
Planner fills a Case  ──▶  sets Status = "Ready for Automation"
                                     │
                     (poller picks it up, every ~5 min)
                                     │
        Case core fields  +  attached "Targeting" sheet
                                     │
                          build_plan_dict()  ──▶  plan
                                     │
                     validate ▸ build Order+Placements
                                     │
                        create DRAFT IO in FreeWheel
                                     │
        ┌────────────────────────────┴───────────────────────────┐
   success:                                             can't build:
   Reason = "Submitted to FreeWheel"                    Status = "Needs Info"
   + comment with the IO link                           + comment with the reason
```

Key point for the discussion: **Salesforce is only the intake form.** All the ad-ops
logic (tiering, naming, ad units, geo, exclusions, per-brand products) already lives in
the tool and is unit-tested. SF's only job is to capture ~7 required fields cleanly and
hold a status flag. We are **not** asking SF to compute anything.

---

## 2. The minimal path (build these 7 first)

If we do nothing else, these 7 fields let the automation build a standard order. Every
other field is optional polish or an override.

| Field Label | API Name | Type | Picklist |
|---|---|---|---|
| Promoted Title | `Promoted_Title__c` | Text | — |
| Region | `Region__c` | Picklist | USA, CA, AU, LATAM, BR, UK, IE, FR, IT, GSA, FI, DK, NO, SE, ES |
| Language | `Language__c` | Picklist | English, French *(routes Canada to FR vs EN)* |
| Campaign Name | `Campaign_Name__c` | Picklist | the 153 FreeWheel campaigns *(drives Brand/Advertiser/default products)* |
| Flight Start | `Flight_Start__c` | Date | — |
| Flight End | `Flight_End__c` | Date | — |
| Video Durations | `Video_Durations__c` | Text | e.g. `30;15` (semicolon-separated) |

Everything derives from **Campaign Name** — pick the campaign and the brand, advertiser,
default product set, ad units, geo, and naming all resolve automatically.

---

## 3. Full field list (35 fields)

Grouped by section. **Required** = planner must fill; everything else defaults or is an
override that's normally left blank. Product toggles are `Yes / No / (blank)`, where
blank = "use the brand's standard set."

### Required (7)
| Field | API Name | Type |
|---|---|---|
| Promoted Title | `Promoted_Title__c` | Text |
| Region | `Region__c` | Picklist |
| Language | `Language__c` | Picklist (English; French) |
| Campaign Name | `Campaign_Name__c` | Picklist |
| Flight Start | `Flight_Start__c` | Date |
| Flight End | `Flight_End__c` | Date |
| Video Durations | `Video_Durations__c` | Text |

### Optional creative / product selectors (10)
| Field | API Name | Type | Values |
|---|---|---|---|
| Season or Messaging | `Season_or_Messaging__c` | Text | middle of the placement name |
| Content Type | `Content_Type__c` | Picklist | show; movie |
| Content ID | `Content_ID__c` | Text | ShowID / MovieID |
| Recommended Show ID | `Recommended_Show_ID__c` | Text | defaults to Content ID |
| Primary Trafficker | `Primary_Trafficker__c` | Text | submitting CM → IO's Primary Trafficker |
| Kids Audience | `Kids_Audience__c` | Multi-Select | older; younger *(Kids brands)* |
| Rating Restrictions | `Rating_Restrictions__c` | Long Text | *(AU Network 10 only)* |
| Video Domination | `Video_Domination__c` | Picklist | pluto; standard; aus_10_streaming; uk_my5 |
| Video Domination Targeting | `Video_Domination_Targeting__c` | Long Text | Pluto categories *(Pluto VD only)* |
| Takeover | `Takeover__c` | Picklist | hpto; first_impression; arena_takeover; three_peat |
| Series to Exclude | `Exclude_Series__c` | Lookup / Multi-Select | keep the promo OUT of these series on every placement |
| Pluto Channels to Exclude | `Exclude_Channels__c` | Lookup / Multi-Select | keep the promo OUT of these channels (Region-scoped) |

### Products — Yes / No toggles (10)  *(blank = brand default)*
`Include_Remnant_Video__c`, `Include_Pause_Ads__c`, `Include_Premium_Pre_Roll__c`,
`Include_Essential_Bumper__c`, `Include_CBS_Pre_Roll__c`, `Include_After_Mid_Roll_Bumper__c`,
`Include_1Z_Lockdown__c`, `Include_2Z_Lockdown__c`, `Include_Pluto__c` *(UK P+ only)*,
`Include_Network_10__c` *(AU only)* — all Picklist `Yes; No`.

### Overrides — auto-derived, set only if needed (8)
`Brand__c`, `Advertiser__c`, `Advertiser_ID__c`, `Campaign_ID__c`,
`Insertion_Order_Name__c`, `Recommended_Show__c`, `Exclude_Show__c`, `Formats__c`.
These normally stay blank; they exist as escape hatches when the auto-derivation needs a
manual nudge.

---

## 4. Status / Reason picklist values (add to existing fields)

These are **not new fields** — they're picklist *values* the automation reads/writes on
the Case's existing Status/Reason fields.

| Field | Value | Who sets it |
|---|---|---|
| Status | **Ready for Automation** | Planner — this is the trigger |
| Status | **Needs Info** | Automation, when a Case can't be built (+ comment) |
| Reason | **Submitted to FreeWheel** | Automation, after the draft IO is created (+ IO link) |

**Trigger / Record Type (recommended).** So the automation reliably knows *which* Cases
are promo-setup requests, add a **Record Type "Campaign Setup Form"** (or a checkbox
`Campaign_Setup_Form__c`). That scopes which Cases we process (the layout + these fields);
**Status = "Ready for Automation"** then says *when* to run. The poller filters on both.

---

## 4b. Targeting values are pre-defined — no free text

Every targeting field draws from canonical lists generated from FreeWheel (see
`templates/targeting-options/`), so a planner can only pick real values:

| Field | SF control | Source |
|---|---|---|
| Genre (+ Franchise + Daypart) | Multi-select picklist | `genres.csv` |
| Pluto Categories | **Region-dependent** picklist | `pluto-categories-by-region.csv` |
| Pluto Channels | **Lookup / type-to-search** (Region-scoped) | `pluto-channels-by-region.csv` |
| Audience Segments | Lookup / type-to-search (refreshed daily) | `audience-segments.csv` |
| **Showlist / Series to Exclude** | **Lookup / type-to-search** | `shows.csv` (~188k FW series) |
| **Pluto Channels to Exclude** | **Lookup / type-to-search** (Region-scoped) | `pluto-channels-by-region.csv` |

Small finite lists = picklists; large lists (Showlist, Channels, Audience, the two
Exclude fields) = **lookups to synced objects** — type-to-search, only real records, no
typos. Refreshed on the daily sync. Full guidance: `templates/targeting-options/README.md`.

---

## 5. The attached "Targeting" sheet (7 columns)

Detailed targeting lists are captured on a standard **Targeting** sheet attached to the
Case (not as Case fields — they're variable-length lists). The automation reads these
columns:

`Audience Segments` (Tier 1), `Kids Audience`, `Networks`, `Genres`, `Showlist`,
`Pluto Categories`, `Pluto Channels`.

Most of these auto-resolve (e.g. Tier-1 audience segments derive from the Showlist), so
the planner usually only fills Showlist + a couple of genre/category lists.

---

## 6. What we need from the Salesforce admin

1. Create the **37 Case fields** above (CSV is import-ready). *Or* start with just the
   **7 required** to prove the loop, and add the rest incrementally.
2. Add the **3 Status/Reason picklist values** in §4, and a **"Campaign Setup Form"
   Record Type (or checkbox)** so the automation knows which Cases are ours.
3. Confirm the API user + permissions the automation will authenticate as (read Case +
   fields, write Status/Reason + comments).
4. Confirm we can attach / read the **Targeting** sheet on a Case (or whether targeting
   should instead be additional Case fields — see open question below).

Once those exist, `promo-ops salesforce-check` logs in and reports any missing field or
picklist value, so we get a green/red readiness check before running a real Case.

---

## 7. Open questions to decide together

- **Targeting sheet vs. fields** — keep detailed targeting on an attached sheet (flexible,
  variable-length) or model a few as Case fields? Recommend: attached sheet, since lists
  vary in length and the planner form already handles it.
- **Picklist upkeep** — Campaign Name (153 values) and Brand change as we add markets. We
  can regenerate the picklist from config on demand; decide whether the admin pastes the
  refreshed list or we wire an automated sync later.
- **Trigger mechanism** — a Status value ("Ready for Automation") is simplest. If the team
  prefers a checkbox or a specific Record Type/queue, that's an easy swap.
- **Scope for phase 1** — which regions/brands go live first? The tool supports all 15
  regions today, but we can pilot with one (e.g. USA) to validate the loop before opening
  it up.

---

*Generated from the live config. Regenerate the field list any time with*
`python -c "from promo_ops.integrations.salesforce import build_case_field_rows"` *→
`docs/salesforce-case-fields.csv`.*
