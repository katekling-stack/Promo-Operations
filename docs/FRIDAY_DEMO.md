# Team demo — script + ask

A tight script to show what the tool does today and align on the Salesforce build.
Everything below runs against **FreeWheel production, 15 regions, 153 campaigns** (full
parity with what's live in FreeWheel). Goal of the meeting: get the admin to **create the
Case fields + a sandbox/Connected App** so we can flip the switch on automated intake.

## 1. The one-line pitch
"A planner fills out a simple form; the tool builds the FreeWheel Insertion Order + every
placement — correct tiering, naming, ad units, geo, and exclusions — as a draft, and can
duplicate a title across markets in one click. It's running against FreeWheel production
for 15 regions today. The last mile is wiring the intake to Salesforce."

## 2. Demo A — the interactive intake form (what planners touch)
Open `templates/campaign-plan/campaign-plan-form.html` in any browser (no login, no
install). Walk through:
- Pick **Region → Campaign** — brand, advertiser, and the products that campaign runs
  fill in automatically. Conditional fields appear only when relevant (Language for CA,
  Kids Audience for kids brands, Rating Restrictions for AU Network 10).
- Real dropdowns + chip inputs — hard to enter anything invalid. Every one of the 153
  campaigns is selectable, per country.
- Click **Download plan file** → a JSON the tool consumes directly.

Talking point: this replaced the "clunky spreadsheet." It's the same intake a Salesforce
Case will capture — so the form doubles as the spec for the SF fields.

## 3. Demo B — form/Case → FreeWheel order (the automation)
Show the exact transform a real Case will drive, from a local Case file:

```bash
promo-ops from-case-file examples/case-frisco-king-usa.json \
  --targeting templates/campaign-plan/Targeting.csv
```
→ builds **14 placements** (remnant Tiers 1–4 × durations, Pause Ads, Premium Pre-Roll +
Essential Bumper) from ~10 Case fields + the attached Targeting sheet. Talking points:
- The Case has ~10 fields; **everything else is derived** from the Campaign (brand,
  advertiser, formats, all targeting + exclusion rules).
- Add `--live` to create the NOT_BOOKED draft in FreeWheel. Then show a **real production
  draft** already created by the tool (any `[QA TEST]` IO) so they see it end-to-end.

## 4. Demo C — duplicate a title to other markets (the time-saver)
Same title, many countries — one action instead of rebuilding each by hand:

```bash
promo-ops mirror frisco-king-fr.plan.json --to GSA,IT,ES
```
→ writes a ready plan for each market, re-pointed at that country's equivalent brand,
with naming, ad units, geo, and placements re-derived. Markets with no equivalent brand
are skipped with a reason (never guessed). Same feature is in the form as **"Duplicate to
another market."**

## 5. What the Case looks like
- Open `examples/case-frisco-king-usa.json` (the "form") and
  `docs/SALESFORCE_EXAMPLE_CASE.md` (the same, annotated: what the planner fills vs. what
  the automation derives).
- The hand-off is one flag: **Status = "Ready for Automation."**

## 6. The ask (hand these over)
- **`docs/SALESFORCE_FIELD_MAPPING.md`** (+ PDF) — the field mapping: the minimal 7-field
  path, the full 35-field spec, the Status/Reason values, and the open questions.
- **`docs/salesforce-case-fields.csv`** — the exact fields to create (API names, types,
  picklist values for all 15 regions / 153 campaigns). Generated from live config, so
  it's complete and current.
- **`docs/SALESFORCE_GOLIVE.md`** — the go-live runbook (fields → creds → preflight →
  schedule).
- Concretely we need: the custom fields created, the **Status/Reason** picklist values, a
  **sandbox + Connected App** (or integration user), and confirmation of the Case layout.
  Offer to rename API names to their conventions.

## 7. What happens right after they say yes
```bash
promo-ops salesforce-check          # proves creds + that every field/picklist exists
promo-ops from-case <CASE_ID>       # dry-run one real Case (no writes)
promo-ops from-case <CASE_ID> --live  # create the draft + comment back
promo-ops poll-cases --live --watch   # unattended: process every Ready Case on an interval
```
`salesforce-check` turns green when the org is built — that's the go/no-go signal. Suggest
piloting **one region (e.g. USA)** first to prove the loop, then open up all 15.

## 8. If asked "what's NOT automated yet"
- **Operative takeovers / Video Dominations** book through Operative's UI (no API); the
  tool prints a step-by-step booking worksheet (`promo-ops booking-sheet`). GAM is ready
  to wire (`gam-check`) if/when API access is granted.
- Go-live is human-in-the-loop by design — drafts are created NOT_BOOKED; a person
  reviews and activates in FreeWheel.

## 9. Proof points (numbers to cite)
- **15 regions, 153 campaigns** — full parity with FreeWheel (every brand-campaign that
  exists under the advertisers is selectable).
- **180 automated tests** covering tiering, naming, ad units, geo, every exclusion rule,
  the add-ons, mirroring, and the automation loop — all runnable with no credentials.
- Reverse-engineered and verified against live reference IOs; site-groups confirmed
  against production.
