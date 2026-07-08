# Campaign Plan Sheet — the interim input template

This is the "fill out a sheet per campaign" workflow we start with before moving to
Salesforce-driven input. A filled sheet produces the **exact same order** as a YAML
plan (there's a test that proves the Frisco King template round-trips identically).

Importable starter files live in [`templates/campaign-plan/`](../templates/campaign-plan/),
pre-filled with the Frisco King - USA example.

## Structure — two tabs

### Tab `Plan` (scalar fields, one per row)

| Field | Example | Notes |
|---|---|---|
| Promoted Title | `Frisco King` | The title being promoted. |
| Region | `USA` | Must match a key in `config/regions.yaml` (USA, CA, AU, LATAM, BR, UK). |
| Salesforce Case | | Optional; the originating Case #. |
| **Advertiser** | `VCBS English - USA - Adult (Promo)` | The **exact** advertiser this nests under. |
| **Advertiser ID** | `1000520` | The exact advertiser id (preferred — unambiguous). |
| **Campaign Name** | `Paramount + - USA` | The **existing** FreeWheel campaign the new IO nests under. |
| **Campaign ID** | `86543608` | The exact campaign id (preferred — there can be duplicate names). |
| **Insertion Order Name** | `Frisco King - USA` | The new IO created for this show/flight. Defaults to `Promoted Title - Region`. |
| **Recommended Show** | `Frisco King` | FreeWheel "Recommended Show" Key Value. Feeds Tier 1 carousel targeting **and** the Premium Pre-Roll / Essential recommended-show argument. Defaults to Promoted Title. |
| **Exclude Show** | `Frisco King` | Label excluded from **every** placement so the show never promos against itself. Defaults to Promoted Title. |
| **Season or Messaging** | `Season 1` | Middle segment of placement names: `{Title} - {Season/Messaging} - {Duration} - Tier N - {Region}`. |
| **Video Durations** | `30; 15` | Semicolon list of seconds. Each video tier becomes one placement **per duration**. |
| **Content Type** | `show` | `show` or `movie` — selects the guaranteed-placement token (`[ShowID:]` vs `[MovieID:]`). |
| **Content ID** | | The ShowID/MovieID for guaranteed placements. Blank → `[ShowID:]` left as a fill-in marker. |
| Flight Start / End | `2026-07-14` | Dates. |
| Flight Code | `L1` | Launch beat / flight code, used in placement names. |
| Formats | `remnant_video; pause_ads; premium_preroll; essential_bumper` | Semicolon list; must match `config/placement_templates.yaml`. Guaranteed formats (`premium_preroll`, `essential_bumper`) are built from genre + recommended show and flagged as living in the existing guaranteed order. |
| P+ User States | `New; Light; Medium; Heavy` | Tier-1 P+ user-state targeting. |
| Demographics Age / Gender | | Optional Tier-3 refinement. |

Rows whose label isn't recognized are ignored, so you can add comment/instruction
rows freely. List values are **semicolon-separated**.

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
- The parsers (`parse_plan_tab`, `parse_targeting_tab`, `assemble_plan_template`) are
  pure functions over rows, so they're unit-tested without needing the live Sheets
  API (`tests/test_plan_template.py`).
