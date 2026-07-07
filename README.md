# Promo Operations — FreeWheel / GAM Order Automation

A tool to turn a **campaign support plan** (targeting inputs from a Salesforce Case
or a planning sheet) into a fully-built **Order + Placements + tiered targeting**,
and push it into **FreeWheel** and **Google Ad Manager** — following the Paramount
Digital Promo Ad Operations tiered targeting strategy.

> Status: **Foundation / starting point.** The deterministic core (support plan →
> tiered targeting → order + placement spec) is implemented and runnable today in
> dry-run mode. The external-system push clients (FreeWheel, Salesforce, GAM,
> Operative) are scaffolded against their documented APIs and gated on credentials.
> See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what is live vs. pending.

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
