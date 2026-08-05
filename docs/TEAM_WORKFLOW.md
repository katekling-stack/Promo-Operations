# How our team creates FreeWheel drafts with Promo-Ops

Plain-English, end-to-end. There are **two ways** to submit campaigns. Use **Path A** for a
one-off; use **Path B** when you have a bunch at once. Both end the same way: a **NOT_BOOKED
draft** appears in FreeWheel, and a **Campaign Manager reviews and books it**.

> **Key idea:** the terminal always works on a **file** — either one downloaded plan file
> (Path A) or one downloaded spreadsheet saved as CSV (Path B). You **never paste rows into
> the terminal.** You paste rows into the *spreadsheet*; the terminal reads the *file*.

---

## Who does what
| Role | Does |
|---|---|
| **Campaign Manager** | Fills out the campaign **form** (one per campaign), posts the plan file to Slack **#promo-order-automations-submissions**, sets the Salesforce case **Status → Ready for Automation**, and later **reviews + books** the draft in FreeWheel (the actual "go live") |
| **Ad Ops (you)** | Picks the file up from Slack, runs `promo-ops` to **push the draft** into FreeWheel, and **comments on the Salesforce case** once the draft is ready |

**What "push the draft" means:** the tool only ever creates a **NOT_BOOKED draft** — nothing
serves. Booking/going-live is done by the CM in FreeWheel, never by this tool.

---

## Path A — one campaign at a time

**Campaign Manager**
1. Open the form: `templates/campaign-plan/campaign-plan-form.html` (double-click it).
2. Fill it out.
3. Click **Download plan file** → a file lands in Downloads, e.g. `tulsa-king-usa.plan.json`.
4. Post that plan file to the Slack channel **#promo-order-automations-submissions**.
5. In the linked **Salesforce case**, set **Status → Ready for Automation**. (Ad Ops comments on the case once the draft is ready.)

**Ad Ops (you)** — grab the plan file from **#promo-order-automations-submissions** (download to your
Downloads folder), then in Terminal:
```
cd /Users/klemley/Desktop/Promo-Operations          # be in the folder first
promo-ops preview  ~/Downloads/tulsa-king-usa.plan.json                         # 1) eyeball it (creates nothing)
promo-ops push     ~/Downloads/tulsa-king-usa.plan.json --target freewheel --live   # 2) push the NOT_BOOKED draft
```
> **Tip — don't type file paths.** In step 2, type `promo-ops push ` (with a space), then
> **drag the downloaded file from Finder onto the Terminal window** — it pastes the path for
> you — then type ` --target freewheel --live` and press Return.

Then tell the CM the draft is in FreeWheel for review.

---

## Path B — many campaigns at once (the batch sheet)

**Campaign Manager (for each campaign)**
1. Fill the **form**.
2. Click **Copy row for Sheet** (this copies one row to the clipboard).
3. Open the **shared team Google Sheet** → click the next empty row → paste (**Cmd + V**).
   The values drop into the right columns.
   *(Simple campaigns can be typed straight into the sheet instead.)*

**Ad Ops (you), when it's time to push a batch**
1. In the Google Sheet: **File → Download → Comma-separated values (.csv)**.
   It saves to Downloads, e.g. `promo-batch-2026-08-11.csv`.
2. In Terminal:
   ```
   cd /Users/klemley/Desktop/Promo-Operations
   promo-ops batch ~/Downloads/promo-batch-2026-08-11.csv --out results.csv               # preview ALL rows (creates nothing)
   promo-ops batch ~/Downloads/promo-batch-2026-08-11.csv --live --out results.csv        # push ALL drafts
   ```
3. `results.csv` maps each **Salesforce Case #** to its **FreeWheel draft link + status** —
   paste that back onto the cases so the CM knows what to review.

> Again: you download the sheet **as a file** and give the tool the *file*. You do **not**
> copy rows out of the sheet into the terminal.

---

## The golden rules
- **Always run the preview / no-`--live` version first** and eyeball it.
- **`--live` = "push the real draft."** It does **not** book or serve anything — every draft
  is NOT_BOOKED until a CM books it in FreeWheel.
- **Re-running is safe.** If you fix a couple rows and run again, existing drafts are
  **reused, never duplicated**.
- If a command says **"does not exist,"** you're probably not in the folder — run
  `cd /Users/klemley/Desktop/Promo-Operations` first. (Your prompt shows `Promo-Operations %`
  when you're in the right place, `~ %` when you're not.)

---

## Quick reference
| I want to… | Command |
|---|---|
| Check one plan | `promo-ops preview <file>.plan.json` |
| Push one draft | `promo-ops push <file>.plan.json --target freewheel --live` |
| Preview a whole batch | `promo-ops batch <file>.csv --out results.csv` |
| Push a whole batch | `promo-ops batch <file>.csv --live --out results.csv` |

*(`<file>` = the real name of the file you downloaded — drag the file onto Terminal instead
of typing it.)*
