# Promo Operations — FreeWheel / GAM Order Automation

A tool to turn a **campaign support plan** (targeting inputs from a Salesforce Case
or a planning sheet) into a fully-built **Order + Placements + tiered targeting**,
and push it into **FreeWheel** and **Google Ad Manager** — following the Paramount
Digital Promo Ad Operations tiered targeting strategy.

> Status: **Live against FreeWheel production, building out coverage.** The
> deterministic core (support plan → tiered targeting → Order + Placements) is
> implemented, and the **FreeWheel integration is verified end-to-end against
> production** (network 520311): the tool creates real Orders + Placements as
> NOT_BOOKED `[QA TEST]` drafts under existing Advertisers/Campaigns and they
> populate with the correct tiering, targeting, ad units, geo, and exclusions.
> **15 regions and 40+ promo brands** are modeled from their live reference IOs.
> Salesforce (case → plan) and GAM/Operative (video dominations, takeovers) are
> designed and scaffolded, gated on credentials. See the coverage table below and
> [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Coverage (built + verified in production drafts)

| Region | Brands modeled |
|---|---|
| **USA** | P+ (adult + Kids), CBS Sports / News / Network, MTVE, BET, Pluto TV, Pluto XCO, Pluto En Español (+ Kids) |
| **Canada** | P+ EN (+ Kids), Pluto EN (+ Kids), Pluto FR, Nick EN Kids — English tiered; French + Kids not tiered; language routing |
| **UK** | P+ (+ Kids), Pluto TV — P+/Pluto split, "Include Pluto" toggle |
| **Ireland** | P+ (+ Kids) — no Pluto |
| **Australia** | P+, Nick (+ Nick Jr) Kids — no Pluto; "Include Network 10" (10 Streaming); rating restrictions; DWH Summit Tier-1 segments |
| **LATAM** | P+, Pluto TV, P+ Kids, Nick (+ Nick Jr) — geo region 1069 |
| **Brazil** | P+, Pluto TV, P+ Kids, Nick (+ Nick Jr) — geo country 21 |
| **Europe** (FR, IT, GSA, FI, DK, NO, SE, ES) | P+ (+ Kids) where present, Pluto TV (+ Kids), Nick (+ Nick Jr ES) — per-country geo; GSA = DE+CH+AT |

Each region was reverse-engineered from its live active IOs and confirmed with QA
drafts in production. **130 automated tests** cover the tiering, naming, ad units,
geo, and every global rule below.

### Global targeting rules encoded (config-driven, applied everywhere)
- Tier label always in parentheses `(Tier N)`; per-region tier eligibility (no Tier 1 in UK/IE/EU).
- **Kids VG symmetry** — older-only excludes Nick Jr, younger-only excludes Nick, both include both, Kids COPPA always on.
- **Guaranteed Plan excludes** — Premium Pre-Roll excludes Format: Clips; Basic/Essential Bumper excludes Stream Type: Live.
- **Samsung TV Plus** excluded on all Pluto TV brand placements (US vs international SGs).
- **Self-exclusion** — the promoted show's own Video Series (underscored + spaced) and Channel SGs excluded everywhere.
- **US Pluto DNR** (951172) on all US brands except Pluto TV - USA; **LATAM/BR Promo Blocks** (1258011) on all adult Pluto placements except Pluto TV - BR/LATAM.
- **Pause-ad excludes** region-scoped (US vs international key-values; no-Pluto regions drop the Pluto SG).
- **Products toggles** (Yes/No) to include/exclude each product per campaign.

---

## What it does

1. **Reads a support plan** — the campaign inputs: promoted title, brand/advertiser,
   region, flight, formats, and targeting inputs (showlist, genres, networks,
   Pluto categories/channels). Today from a YAML file; designed to also read a
   Google Sheet template and, ultimately, a Salesforce Case.
2. **Builds tiered targeting** — applies the Tier 1–4 structure from the
   *Inventory & Targeting Strategy* deck (Slide 5) to the plan inputs:
   - **Tier 1** (USA, AU, CA, LATAM, BR): audience segments (DDA/AAM), prior-season
     viewer, home-page carousel recommendations, P+ user states — resolved from the
     **Audience Segments** doc by matching the showlist.
   - **Tier 2** (global): content-affinity showlist, Pluto channel list, AI similar.
   - **Tier 3** (global): genre / network / Pluto category, geo, demo.
   - **Tier 4** (global): filler — everywhere except the promoted title.
3. **Builds an Order and Placements** — one Order per campaign, one Placement per
   format × region, from reusable **region-code templates** per brand (VCBS
   advertisers).
4. **Pushes** the built Order/Placements into FreeWheel and GAM (scaffolded).

## The Frisco King - USA worked example

`plans/frisco-king-usa.yaml` is the seeded example (modeled on the FreeWheel
campaign referenced in the kickoff). Build it end-to-end in dry-run:

```bash
pip install -e .
promo-ops build plans/frisco-king-usa.yaml --out build/frisco-king-usa.json
promo-ops preview plans/frisco-king-usa.yaml     # human-readable tier breakdown
```

This produces the full Order + Placement + per-tier targeting spec as JSON — no
credentials required — so the mapping can be reviewed before anything is pushed.

## Filling out a campaign (the sheet template)

Until input is Salesforce-driven, campaigns are entered in a two-tab Google Sheet
(`Plan` + `Targeting`). Importable starter files, pre-filled with Frisco King, are in
[`templates/campaign-plan/`](templates/campaign-plan/); the field reference is in
[`docs/PLAN_TEMPLATE.md`](docs/PLAN_TEMPLATE.md). A filled sheet builds the identical
order to the YAML plan (proven by `tests/test_plan_template.py`):

```bash
promo-ops build-from-sheet <SHEET_ID> --out build/campaign.json
```

## Layout

```
config/     brand → VCBS advertiser map, regions, the tiering framework, placement templates
plans/      per-campaign support plans (the Frisco King example lives here)
src/promo_ops/
  models.py            domain dataclasses (SupportPlan, Order, Placement, Targeting)
  targeting.py         the tiering engine (support plan → tiered targeting)
  audience_segments.py Tier-1 resolver: show title → FW audience segment (syncs from the Drive doc)
  order_builder.py     Order + Placement assembly from templates
  cli.py               build / preview / push entrypoints
  integrations/        freewheel, salesforce, gam, operative, gsheets clients (credential-gated)
docs/       ARCHITECTURE.md, ROADMAP.md
tests/      targeting engine tests
```

## Configuration / credentials

Copy `.env.example` to `.env` and fill in credentials for the systems you want to
push to. Nothing in the repo contains secrets; every client reads from the
environment. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
