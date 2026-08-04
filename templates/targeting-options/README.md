# Targeting option lists — for form dropdowns + Salesforce picklists

Canonical, pre-defined values for the targeting fields, generated from FreeWheel so a
planner can only pick real values (no free-text typos). Regenerate any time with
`python scripts/build_targeting_options.py`.

## Files
| File | Keyed by | Rows |
|---|---|---|
| `genres.csv` | — (global) | value + type: **Genre** (~265) + **Franchise** (47) + **Daypart** (Daytime) |
| `pluto-categories-by-region.csv` | **our region** (Pluto regions only) | ~20–25 / region |
| `pluto-channels-by-region.csv` | **our region** (Pluto regions only) | ~80–1,000 / region |
| `audience-segments.csv` | — | segment_name + structure (~2,000) |
| `pluto-categories.csv` / `pluto-channels.csv` | raw Pluto market | reference |
| `REGION-MAP.md` | — | our region → Pluto market |

## How to implement each in Salesforce
| Field | Recommended SF field | Notes |
|---|---|---|
| **Genre** | Multi-select picklist | `genres.csv` — content Genres + **VG: Franchise** values + **Daypart: Daytime**. The `type` column tells them apart. Global, no region dependency. |
| **Pluto Categories** | **Dependent** multi-select picklist, controlled by **Region** | ~20–25 / region. From `pluto-categories-by-region.csv`. |
| **Pluto Channels** | Searchable field / lookup, not a picklist | ~80–1,000 / region — too many for a picklist. `pluto-channels-by-region.csv` is the value source. |
| **Audience Segments** | Multi-select picklist / lookup, refreshed daily | `audience-segments.csv`. Also auto-derivable from the Showlist. See refresh below. |
| **Showlist** | Free-text / type-to-search | FreeWheel has ~230k series — not a finite list. |

## Audience segments — daily refresh
Audience segments are added to FreeWheel **daily**. The picklist only keeps segments
matching the canonical **structures** (naming conventions) from the Promo Ops workbook:

- `GL-DDA-1P…` (DDA first-party)
- `AU - DWH - … - Summit - …` (Australia)
- `AAM-VCBS-… : … Paramount Wide` (VCBS Addressable Extension)
- `comScore …`

To ingest the day's new segments, run the sync then regenerate — schedule both daily
(cron), the same way the Case poller runs:

```bash
promo-ops sync-audience-items          # pull the live FreeWheel audience library
python scripts/build_targeting_options.py   # re-filter to the structures -> picklist
```

New segments in any of the structures above are picked up automatically; anything not
matching a structure is ignored. Add a structure in the script's `AUDIENCE_STRUCTURES`
if a new naming convention is introduced.

## Notes
- **Region drives the Pluto lists.** Regions that don't run Pluto (AU, IE) are omitted.
- **GSA/LATAM** use one primary Pluto market each (GSA→DE, LATAM→MX) — change in the
  script's `REGION_TO_PLUTO_MARKETS`.
- These lists change as FreeWheel inventory changes — re-run the generator and re-load
  the picklists periodically.
