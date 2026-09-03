# Promo Operations — Current Status

*Snapshot as of 2026-09-03. Branch: `claude/freewheel-order-placement-templates-p2rjzd`
(latest commit `fda1f18`). Tests: **389 passing**.*

---

## Where the system stands

- **Live against FreeWheel production, feature-complete for building.** From a plan it builds
  the full Insertion Order + per-tier Placements as `NOT_BOOKED` drafts with correct tiering,
  targeting, ad units, geo, and exclusions. A human reviews and activates.
- **Coverage:** 15 regions / ~79 promo brands, reverse-engineered from live IOs.
- **Two ways in:** the self-serve HTML **Campaign Plan form**, and the `promo-ops` **CLI**
  (build / preview / push / from-case / sync / refresh-form).
- **Suggest targeting** works in historicals-only mode today; hosting it for the team is the
  next step (see `docs/ENGINEERING_HANDOFF.md`).

## What shipped recently (this working session)

| Area | Change |
|---|---|
| **Flight validation** | A plan now requires **both** a start and an end date; the form blocks submit and the builder flags a half-filled flight. *(Fixed the South Park USA push.)* |
| **Tier 2 targeting** | The promoted title's own series is dropped from the Tier 2 affinity **include** so it can't clash with the self-**exclude** (which silently killed only Tier 2). *(Fixed Primate GSA.)* |
| **P+ Plan placements** | Premium Pre-Roll / Essential Bumper (+ kids variants) now push at **HIGHEST** precedence, not HIGH. |
| **BET Media Group** | Main inventory now targets the VCBS **Cable Adults VGs (BET + VH1)** instead of the BET+ site group, matching live BET IOs. |
| **Placement names** | The `(P+/Pluto)` marker is dropped from names in every region; real `(Pluto)` breakout labels and `(10 Streaming)`/`(My5)` are kept. |
| **AU Kids Network 10** | (10 Streaming) toggle added to Paramount + - Kids - AU (and the adult AU brands earlier). |
| **UK Kids Pluto** | Folded into the standard remnant (one line, P+ + Pluto UK inventory) instead of a separate breakout. |
| **Kids DK** | Removed from the form (nothing active there). |
| **IE content ratings** | Ireland now resolves the UK/BBFC rating VGs; short rating labels (`15`/`18`) can no longer leak as raw VG ids. *(Fixed the Yellowjackets IE 422.)* |
| **AU Tier 1** | AU uses the regular global GL-DDA-1P audience segment when a show/movie has one (plus its DWH segments). |
| **Targeting Catalog** | Standalone searchable page of targeting options by region. |

## In flight / dependencies

- **Salesforce field + credential setup** — needed for full Case→drafts automation (building
  from a plan/form does not depend on it).
- **FreeWheel MRM client-credentials** not yet provisioned — IO Brand is set by hand on push
  until then; everything else works.
- **Suggest helper hosting** — pending the engineering discussion this doc supports.
- **Housekeeping:** placement hard-delete isn't supported by our FreeWheel gateway, so stray
  placements are cleaned up in the FreeWheel UI.

## Immediate next steps

1. **Engineering:** decide on hosting for the Suggest helper (historicals-only to start) and
   the daily refresh job — see `docs/ENGINEERING_HANDOFF.md` §5.
2. **API-key sign-off** to later enable the Suggest AI layer (one server-side key).
3. **Salesforce** field/credential provisioning to close the loop on Case automation.
4. Team continues building/pushing orders from the form + CLI in the meantime.
