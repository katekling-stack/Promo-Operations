# Campaign Plan Sheet — the interim input template

This is the "fill out a sheet per campaign" workflow we start with before moving to
Salesforce-driven input. A filled sheet produces the **exact same order** as a YAML
plan (there's a test that proves the Frisco King template round-trips identically).

Importable starter files live in [`templates/campaign-plan/`](../templates/campaign-plan/),
pre-filled with the Frisco King - USA example.

## Structure — two tabs

### Tab `Plan` (scalar fields, one per row)

The Plan tab is a three-column, grouped key/value layout: **Field | Value | Notes /
Allowed values**. The Notes column lists the allowed values inline so a planner
rarely has to leave the sheet. Section-header rows (`— CAMPAIGN —`, `— CREATIVE /
NAMING —`, etc.) are ignored by the parser; they only organize the sheet.

The design is **lean**: a planner fills the campaign, creative, flighting and any
optional targeting, and everything else is **auto-derived**. In particular, picking
the **Campaign** is enough to derive the **Brand**, **Advertiser**, and default
**Formats** — so those live in a trailing *Overrides* section and are normally left
blank.

**Filled by the planner**

| Field | Example | Notes |
|---|---|---|
| Promoted Title | `Frisco King` | The title being promoted. (required) |
| Region | `USA` | Must match a key in `config/regions.yaml` (USA, CA, AU, LATAM, BR, UK). (required) |
| Campaign Name | `Paramount + - USA` | The **existing** FreeWheel campaign the new IO nests under. Drives Brand / Advertiser / default Formats. (required) |
| Salesforce Case | | The originating Case # (auto-filled on the Salesforce path). |
| Season or Messaging | `Season 1` | Middle segment of placement names: `{Title} - {Season/Messaging} - {Duration} - Tier N - {Region}`. |
| Video Durations | `30; 15` | Semicolon list of seconds. Each video tier becomes one placement **per duration**. (required for video) |
| Content Type | `show` | `show` or `movie` — selects the guaranteed token (`[ShowID:]` vs `[MovieID:]`). |
| Content ID | | ShowID/MovieID for guaranteed placements; also fills Recommended Show ID. (CM) |
| Recommended Show ID | | Value for the `recommended_show=<id>` key-value on Tier 1 + guaranteed Plan placements. Defaults to Content ID; blank → CM adds it in the UI. (CM) |
| Flight Start / End | `2026-07-14` | Dates (YYYY-MM-DD). (required) |
| Flight Code | `L1` | Launch beat / flight code, used in placement names. |
| Video Domination | | Optional: `pluto` \| `standard` \| `aus_10_streaming` \| `uk_my5`. |
| Video Domination Targeting | | Pluto categories (semicolon list) — **Pluto VD only**. |
| Takeover | | Optional Operative→GAM takeover: `hpto` \| `first_impression` \| `arena_takeover` \| `three_peat`. |
| P+ User States | `New; Light; Medium; Heavy` | Tier-1 P+ user-state targeting. |
| Demographics Age / Gender | | Optional Tier-3 refinement. |

**Overrides — usually blank, auto-derived** (`— OVERRIDES —` section)

| Field | Auto-derived from | Override when |
|---|---|---|
| Brand | Campaign Name | The campaign→brand mapping doesn't cover this campaign. |
| Advertiser / Advertiser ID | Brand | Nesting under a non-default advertiser. |
| Campaign ID | Campaign Name | The name is ambiguous (duplicate campaigns). |
| Insertion Order Name | `{Title} - {Region}` | A non-standard IO name is needed. |
| Recommended Show | Promoted Title | The carousel/recommended-show label differs from the title. |
| Exclude Show | Promoted Title | The show excludes under a different label. |
| Formats | Brand's format set | This campaign runs a non-default format mix. |

Rows whose label isn't recognized (including the `— SECTION —` headers) are ignored,
so you can add comment/instruction rows freely. List values are
**semicolon-separated**.

### Tab `Targeting` (lists, one per column)

One column per targeting list; values run **down** each column. Leave cells blank to
end a list. Recognized headers:

| Column | Feeds |
|---|---|
| Audience Segments (Tier 1) | Tier 1 audience segments, added directly (in addition to any auto-matched from the showlist) |
| Networks | Tier 3 network/brand |
| Genres | Tier 3 genre (also the genre argument for guaranteed placements) |
| Showlist | Tier 2 content affinity **and** Tier 1 audience segments (auto-resolved per show) |
| Pluto Categories | Tier 3 Pluto category |
| Pluto Channels | Tier 2 Pluto channel list |

Column headers are matched by prefix, so `Audience Segments (Tier 1)` works.

## How to use it

1. **Create the sheet.** Make a Google Sheet with two tabs named exactly `Plan` and
   `Targeting`. Import `templates/campaign-plan/Plan.csv` into the first and
   `Targeting.csv` into the second (File → Import → Replace current sheet), or copy
   the master sheet once we create it.
2. **Fill it in** per campaign.
3. **Build from it:**
   ```bash
   promo-ops build-from-sheet <SHEET_ID>          # (wired via read_plan_template)
   ```
   or, offline, export both tabs to CSV and load them through
   `assemble_plan_template()`.

## Mapping to code

- Field/column → plan-key mappings live in `PLAN_TAB_FIELDS` and
  `TARGETING_TAB_COLUMNS` in `integrations/gsheets.py`. Add a field by adding one
  entry there.
- Auto-derivation happens in `plan_loader._apply_defaults()` (Brand from the
  Campaign via `config.brand_for_campaign()`, Formats from the brand's format set);
  the remaining defaults (IO name, recommended/exclude show) are filled by
  `OrderBuilder`. This is why the lean sheet round-trips to the same order as the
  fully-specified YAML.
- The parsers (`parse_plan_tab`, `parse_targeting_tab`, `assemble_plan_template`) are
  pure functions over rows, so they're unit-tested without needing the live Sheets
  API (`tests/test_plan_template.py`).
