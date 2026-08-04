# Ad Ops Runbook — Form → FreeWheel draft (no Salesforce)

The self-serve path for creating a FreeWheel Insertion Order from the campaign-plan
**form** — no Salesforce, no connectors. A planner fills the form; Ad Ops runs three
commands; a NOT_BOOKED draft appears in FreeWheel for review.

> **Doing 20+ a day? Use the batch flow instead**, not this form one at a time — one sheet,
> one row per Salesforce case, one `promo-ops batch` run, results matched back to each Case #.
> See **`docs/BATCH_RUNBOOK.md`**. This form is for a single ad-hoc campaign.

> This is the primary intake today. The Salesforce → FreeWheel automation is a **phase-2**
> add-on for whenever a Salesforce API user + connector is provisioned by a developer —
> the tool's `from-case` / `poll-cases` pipeline is already built to plug in then, and the
> field-mapping doc is the spec for that work. Nothing here changes when that lands.

---

## Who does what
| Step | Who | What |
|---|---|---|
| 1 | **Planner** | Fill the form, download the plan file |
| 2 | **Ad Ops** | Preview + push the plan → FreeWheel draft |
| 3 | **Ad Ops** | Review + activate the draft in FreeWheel (as today) |

## 1. Planner — fill the form
Open **`templates/campaign-plan/campaign-plan-form.html`** in any browser.
- Pick **Region → Campaign** (brand, advertiser, products auto-fill).
- Fill Promoted Title, flight, durations; **type-to-search** the targeting (Showlist,
  Genres, Pluto Categories/Channels) and any **Excludes** — all pick-from-real-values.
- Click **Download plan file** → saves `‹title›-‹region›.plan.json`.
- Hand that file to Ad Ops (Slack/Drive/email).

## 2. Ad Ops — build the draft
On the machine where `promo-ops` is installed (with FreeWheel API access):

```bash
promo-ops preview  yellowstone-usa.plan.json          # human-readable tier breakdown — sanity check
promo-ops build    yellowstone-usa.plan.json --out order.json   # (optional) full order JSON
promo-ops push     yellowstone-usa.plan.json --target freewheel # DRY-RUN: shows exactly what it will create
promo-ops push     yellowstone-usa.plan.json --target freewheel --live   # creates the NOT_BOOKED draft
```
- **Always dry-run first** (omit `--live`) and eyeball the placements.
- `--live` resolves the parent campaign, creates the IO **NOT_BOOKED** (a draft — nothing
  serves), then creates every placement with targeting. It prints the IO + placement ids.

## 3. Ad Ops — review + activate
Open the new IO in FreeWheel, confirm it matches, and activate as you would a hand-built
order. The tool only ever creates drafts — a human always books.

---

## Where the tool runs
`promo-ops` must run somewhere with **FreeWheel API access** — an Ad Ops workstation or a
small internal box (Ad Ops already has FreeWheel access, so this is the same API-user
pattern, not a new approval). It should run **outside** any AI environment for production,
so it's a standard Paramount API integration.

**Setup (once):**
```bash
pip install -e .
cp .env.example .env      # fill FREEWHEEL_NETWORK_ID / USERNAME / PASSWORD
```

## Handy extras
- `promo-ops mirror plan.json --to GSA,IT,ES` — same title, other markets (one file each).
- `promo-ops booking-sheet plan.json` — the Operative/GAM booking worksheet for takeovers
  / Video Dominations (booked in their UIs).
- Refresh the targeting option lists (adds new segments/series/channels):
  `promo-ops sync-audience-items && python scripts/build_targeting_options.py`.

## Safety
- Drafts are **NOT_BOOKED** — reviewable and deletable; nothing serves until a human books.
- Every targeting field is **pick-from-real-values** (no free-text typos).
- The tool is **idempotent**: re-pushing the same title/region reuses the IO, never
  duplicates.
