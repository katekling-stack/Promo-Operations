# Salesforce meeting — demo + ask (Friday)

A tight script to show the automation working today and align on the Salesforce build.
Goal of the meeting: get the admin to **create the Case fields + a sandbox/Connected
App** so we can flip the switch.

## 1. The one-line pitch
"A planner fills a Salesforce Case and flags it Ready; the automation reads it, builds
the FreeWheel Insertion Order + all placements as a draft, and posts the draft link back
on the Case. It's built and running against FreeWheel production for 15 regions today —
the only thing left is wiring it to Salesforce."

## 2. Live demo — Case → FreeWheel order (no Salesforce needed)
Show the exact transform a real Case will drive, from a local Case file:

```bash
promo-ops from-case-file examples/case-frisco-king-usa.json \
  --targeting templates/campaign-plan/Targeting.csv
```
→ prints the built order: **14 placements** (remnant Tiers 1–4 × durations, Pause Ads,
Premium Pre-Roll + Essential Bumper) from a handful of Case fields + the attached
Targeting sheet. Talking points:
- The Case has ~10 fields; **everything else is derived** from the Campaign (brand,
  advertiser, formats, all targeting + exclusion rules).
- Add `--live` to actually create the NOT_BOOKED draft in FreeWheel (optional — we
  already have real QA drafts to show, see below).

Then show a **real production draft** already created by the tool (any `[QA TEST]` IO)
so they see it end-to-end in FreeWheel.

## 3. What the Case looks like
- Open `examples/case-frisco-king-usa.json` (the "form") and
  `docs/SALESFORCE_EXAMPLE_CASE.md` (the same, annotated: what the planner fills vs. what
  the automation derives).
- The hand-off is one flag: **Status = "Ready for Automation."**

## 4. The ask (hand these over)
- **`docs/salesforce-case-fields.csv`** — the exact fields to create (API names, types,
  picklist values for all 15 regions / every campaign). It's generated from the live
  config, so it's complete and current.
- **`docs/SALESFORCE_PROPOSAL.md`** — the full write-up (also as PDF/Word for notes).
- **`docs/SALESFORCE_GOLIVE.md`** — the go-live runbook (fields → creds → preflight →
  schedule).
- Concretely, we need: the custom fields created, the **Status/Reason** picklist values,
  a **sandbox + Connected App** (or integration user), and confirmation of the Case
  layout. Offer to rename API names to their conventions.

## 5. What happens right after they say yes
```bash
promo-ops salesforce-check          # proves creds + that every field/picklist exists
promo-ops from-case <CASE_ID>       # dry-run one real Case (no writes)
promo-ops from-case <CASE_ID> --live  # create the draft + comment back
promo-ops poll-cases --live --watch   # unattended: process every Ready Case on an interval
```
`salesforce-check` turns green when the org is built — that's the go/no-go signal.

## 6. If asked "what's NOT automated yet"
- **Operative takeovers / Video Dominations** book through Operative's UI (no API); the
  tool prints a step-by-step booking worksheet (`promo-ops booking-sheet`). GAM is
  ready to wire (`gam-check`) if/when API access is granted.
- Go-live is human-in-the-loop by design — drafts are created NOT_BOOKED; a person
  reviews and activates in FreeWheel.
