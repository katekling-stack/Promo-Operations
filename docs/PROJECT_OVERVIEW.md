# Promo Operations Automation — Project Overview

*Paramount Global — Digital Promo Ad Operations*

A tool that turns a **campaign support plan** (targeting inputs from a Salesforce Case
or a planning sheet) into fully-built **FreeWheel Orders + Placements + tiered
targeting**, and layers on Video Dominations and Operative/GAM takeovers — following
the Promo Ad Ops tiered-targeting strategy, and mirroring how the live reference IOs are
already set up.

> **Status (Aug 2026): live against FreeWheel production, feature-complete for building.**
> From a plan it builds the full Order + per-tier Placements and creates them as
> NOT_BOOKED drafts that populate with the correct tiering, targeting, ad units, geo,
> and exclusions. Coverage is **15 regions / 79 promo brands**, each reverse-engineered
> from its live IOs and confirmed with production QA drafts. The end-to-end automation
> (Case → drafts → write-back) is built, hardened, and tested. The one remaining
> external dependency is the **Salesforce field/credential setup** (in progress).

---

## Why it matters

Promo campaigns are trafficked by hand today — a CM reads a plan and builds dozens of
placements per campaign across tiers, durations, formats, regions, and platforms, each
with precise targeting and exclusion rules. This tool encodes those rules once and
builds the whole structure deterministically, so a campaign that took significant manual
setup becomes a reviewed draft in seconds — consistent, rule-complete, and auditable.

## What it does (end to end)

```
Salesforce Case (or planning sheet)
        │   promoted title, region, campaign, flight, durations, products, targeting
        ▼
Targeting engine  ──►  Tier 1–4 structure applied to the inputs
        ▼
Order builder     ──►  one Placement per format × tier × duration, per the brand's
        │              live setup (ad units, main SGs, geo, all exclusion rules)
        ▼
FreeWheel         ──►  Insertion Order + Placements created as NOT_BOOKED drafts
        │              + Pluto Video Domination; Operative/GAM takeovers as booking specs
        ▼
Write-back        ──►  draft IO link + CM to-dos posted on the Case; Reason updated
```

A person still reviews and activates each draft in FreeWheel — the automation never goes
live on its own.

## Coverage — 15 regions, 79 brands

| Region | Brands |
|---|---|
| **USA** (11) | P+ Domestic, P+ Kids, CBS Sports / News / Network, MTVE, BET, Pluto TV, Pluto XCO, Pluto En Español (+ Kids) |
| **Canada** (6) | P+ EN (+ Kids), Pluto EN (+ Kids), Pluto FR, Nick EN Kids |
| **UK** (4) | P+ (+ Kids), Pluto TV, Paramount Pictures |
| **Ireland** (2) | P+ (+ Kids) |
| **Australia** (3) | P+, Nick (+ Nick Jr) Kids |
| **LATAM** (6) | P+, Pluto TV, P+ Kids, Nick (+ Nick Jr), Paramount Pictures |
| **Brazil** (8) | P+, Pluto TV, P+ Kids, Nick (+ Nick Jr), Paramount Pictures (+ Kids), Consumer Products Kids |
| **France / Italy / GSA** (6 each) | P+ (+ Kids), Pluto TV (+ Kids), Nick, Paramount Pictures |
| **Finland / Denmark / Norway / Sweden** (4 each) | Pluto TV (+ Kids), Nick, Paramount Pictures |
| **Spain** (5) | Pluto TV (+ Kids), Nick (+ Nick Jr), Paramount Pictures |

Every brand was reverse-engineered from its **live active IOs** and verified with
`[QA TEST]` NOT_BOOKED drafts in FreeWheel production (network 520311). Region nuances
are all handled — Canada language routing (EN tiered, FR/Kids not), UK/IE no-Tier-1
split, AU no-Pluto + Network 10 (10 Streaming) + DWH Summit Tier-1 segments, LATAM geo
region vs BR/EU per-country geo, and the EU house-unit setup.

## Global targeting rules (encoded once, applied everywhere)

- Tier label always in parentheses `(Tier N)`; per-region tier eligibility (no Tier 1 in UK/IE/EU).
- **Kids VG symmetry** — older-only excludes Nick Jr, younger-only excludes Nick, both include both; Kids COPPA always on.
- **Guaranteed Plan excludes** — Premium Pre-Roll excludes Format: Clips; Basic/Essential Bumper excludes Stream Type: Live.
- **Samsung TV Plus** excluded on all Pluto TV brand placements (US vs international SGs).
- **Self-exclusion** — the promoted show's own Video Series (underscored + spaced spellings) excluded everywhere; its Pluto channel excluded on Pluto TV campaigns only.
- **US Pluto DNR** (on all US brands except Pluto TV - USA); **LATAM/BR Promo Blocks** (on all adult Pluto placements except the Pluto TV - BR/LATAM campaigns).
- **Pause-ad excludes** region-scoped (US vs international key-values; no-Pluto regions drop the Pluto SG).
- **Products toggles** — Yes/No per product to add/drop it per campaign.

## The automation loop (built, hardened, tested)

A single Case flagged "Ready for Automation" drives the whole output, unattended:

- **Idempotent** — reuses an existing IO by name instead of creating duplicates (safe re-runs).
- **Add-ons** — pushes the Pluto Video Domination as its own draft; surfaces Operative VDs + takeovers (HPTO / FITO / Arena / 3-Peat) as precise CM booking specs.
- **Scheduled** — one-shot (cron) or `--watch` loop; a transient queue error is caught and the loop continues.
- **Retry/backoff** — transient FreeWheel failures (network, 429/5xx) retry with backoff; 4xx fail fast.
- **Observable** — a JSONL run log per cycle + a `poll-status` summary (audit trail).

## Architecture (config-driven)

The behavior lives in **config, not code** — adding a brand or region is a config entry,
not a code change, which is why 79 brands share one small engine.

- `config/` — brands → campaigns, regions, the tiering framework, placement templates, targeting rules, ad units, Pluto naming, video dominations, takeovers.
- `src/promo_ops/` — the targeting engine, order builder, resolvers (audience segments, series, site groups, ad units, geo), the add-on builder, the Case pipeline, and integration clients (FreeWheel live; Salesforce / GAM / Operative / Google Sheets).
- **155 automated tests** across 32 files cover the tiering, naming, ad units, geo, every global rule, the add-ons, and the full automation loop — all runnable with no credentials (design-first).

## Where each piece stands

| Area | Status |
|---|---|
| FreeWheel order/placement build | **Live** — verified in production across all regions |
| Video Dominations (Pluto) | **Live** — built directly in FreeWheel |
| Operative VDs + Takeovers | **Built** — emit booking specs for the manual Operative→GAM step |
| Case → FreeWheel automation loop | **Built + tested** — idempotent, scheduled, retrying, logged |
| Salesforce (Case → plan) | **Designed + tested; pending org config + credentials** |
| Google Ad Manager / Operative API | Scaffolded; live API automation is future work |

## What's next

1. **Salesforce go-live** — admin creates the Case fields (generated spec in
   `salesforce-case-fields.csv`) + a sandbox/Connected App; `promo-ops salesforce-check`
   verifies, then real Cases flow through. *(In progress.)*
2. **Pilot** — one brand, a handful of real Cases, human-reviewed; then roll out.
3. **Operative/GAM API automation** — replace the manual takeover booking + GAM push.

## Reference docs

- `README.md` — quick start + coverage
- `docs/SALESFORCE_PROPOSAL.md` + `salesforce-case-fields.csv` — the Salesforce ask
- `docs/SALESFORCE_GOLIVE.md` — go-live runbook (fields → creds → preflight → schedule)
- `docs/OPERATIVE_TAKEOVERS.md` — Video Domination + takeover booking runbook
- `docs/PLUTO_TARGETING_NAMES.md` — per-region Pluto category/channel names for CMs
- `docs/reference-ios.md` — the live IO extractions each brand was built from
