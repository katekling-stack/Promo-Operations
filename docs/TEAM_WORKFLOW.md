# How our team creates FreeWheel drafts with Promo-Ops

Plain-English, end-to-end. There are **two ways** to submit campaigns. Use **Path A** for a
one-off; use **Path B** when you have a bunch at once. Both end the same way: a **NOT_BOOKED
draft** appears in FreeWheel, and a **Campaign Manager reviews and books it**.

> **Key idea:** for a single campaign (Path A) you now work entirely in the **Promo Ops tool**
> (https://promo-ops-tools.skydancepages.cloud/form, VPN on): no Terminal, no plan file, no Slack.
> Batches (Path B) still use a spreadsheet saved as CSV and the terminal.

---

## Who does what
| Role | Does |
|---|---|
| **Campaign Manager** | Fills out the campaign **form** in the Promo Ops tool (one per campaign), reviews it and **creates the draft**, marks the **Case Status as Ready for Automation**, and later **reviews + books** the draft in FreeWheel (the actual "go live") |
| **Ad Ops (you)** | **QA's the new IO** on the tool's QA page, and **comments on the Salesforce case** once the draft is ready |

**What "push the draft" means:** the tool only ever creates a **NOT_BOOKED draft** — nothing
serves. Booking/going-live is done by the CM in FreeWheel, never by this tool.

---

## Path A — one campaign at a time

**Campaign Manager** (step by step: [How to create an order](../site/create-an-order.html))
1. Open the form: **https://promo-ops-tools.skydancepages.cloud/form** (VPN on).
2. Fill it out.
3. Press **Review & create in tool**, read the review, type the IO name to confirm, and press **Create in FreeWheel**. You get the new **IO id**.
4. In the linked **Salesforce case**, mark the **Case Status as Ready for Automation**. (Ad Ops comments on the case once the draft is ready.)

**Ad Ops (you)** — paste the **IO id** into **QA an order** on the tool (https://promo-ops-tools.skydancepages.cloud/qa)
and check for **0 errors** while the draft is still NOT_BOOKED. Fix anything flagged ❌, then tell the CM the
draft is in FreeWheel for review. See [`QA_GUIDE.md`](QA_GUIDE.md) for how to read the report. Orders usually show
"no active creatives" right after creation; that's expected until the creatives are attached.

> Terminal still works as a backup (`promo-ops preview`, `promo-ops push ... --live`, `promo-ops qa <IO id>`),
> but the app is the normal way.

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
4. **QA each draft** before the CMs book them — run `promo-ops qa <IO id>` on the IO ids from
   `results.csv` (you can pass several at once: `promo-ops qa 111 222 333`).

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
| **QA a live order** (before booking) | `promo-ops qa <IO id>` |
| Set up the tool on a new computer | see [`CLONE_SETUP.md`](CLONE_SETUP.md) |
| Get the latest version | `./update.sh` |

*(`<file>` = the real name of the file you downloaded — drag the file onto Terminal instead
of typing it.)*
