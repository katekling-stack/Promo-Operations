# Targeting option lists — for form dropdowns + Salesforce picklists

Canonical, pre-defined values for the targeting fields, generated from FreeWheel so a
planner can only pick real values (no free-text typos). Regenerate any time with
`python scripts/build_targeting_options.py`.

## Files
| File | Keyed by | Rows |
|---|---|---|
| `genres.csv` | — (global) | 270 genres |
| `pluto-categories-by-region.csv` | **our region** (USA, UK, GSA…) | ~20–25 / region |
| `pluto-channels-by-region.csv` | **our region** | ~80–1,000 / region |
| `audience-segments.csv` | — | 6,218 DDA segments |
| `pluto-categories.csv` / `pluto-channels.csv` | raw Pluto market (US, DE, MX…) | reference |
| `REGION-MAP.md` | — | our region → Pluto market |

`*-by-region.csv` are the directly-usable ones. GSA and LATAM span several Pluto
markets, so they use one **primary market** (GSA → DE, LATAM → MX) — change in the
script's `REGION_TO_PLUTO_MARKETS` if a different lead market is preferred.

## How to implement each in Salesforce
| Field | Recommended SF field | Notes |
|---|---|---|
| **Genre** | Multi-select picklist | Load the 270 values from `genres.csv`. Global — no region dependency. |
| **Pluto Categories** | **Dependent** multi-select picklist, controlled by **Region** | ~20–25 per region — a good fit for a dependent picklist. Load from `pluto-categories-by-region.csv`. |
| **Pluto Channels** | Searchable field / lookup, **not** a picklist | ~80–1,000 per region exceeds what a picklist handles cleanly. Better as a type-to-search control (the plan form) or a lookup object. `pluto-channels-by-region.csv` is the value source. |
| **Audience Segments** | Leave off the Case | The automation **auto-derives** these from the Showlist (`GL-DDA-1P-SHOW_<show>`). Expose only as an advanced override if ever needed. |
| **Showlist** | Free-text / type-to-search | FreeWheel has ~230k series — not a finite picklist. The tool keyword-matches and selects all real series; a typo surfaces "no match" rather than mis-targeting. |

## Notes
- **Region drives the Pluto lists.** Category/channel values differ per market, so the
  Region field must be set first; the dependent picklist then shows only that region's
  values.
- These lists change as FreeWheel inventory changes — re-run the generator and re-load
  the picklists periodically (same cadence as the campaign picklist refresh).
