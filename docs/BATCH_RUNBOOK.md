# Batch Runbook — 20+ cases a day from ONE spreadsheet

The answer to "we set 20+ cases live per day — do we do them one at a time?" **No.** The
one-at-a-time form is for a single ad-hoc campaign. For daily volume you keep **one sheet**,
**one row per Salesforce case**, and run **one command** — every FreeWheel draft gets built
and the results come back **matched to each Salesforce Case #**.

---

## The flow (what it actually looks like)

```
 Salesforce cases           ONE sheet (one row = one case)          FreeWheel
 ┌───────────┐   copy the   ┌───────────────────────────┐  one run   ┌──────────────┐
 │ Case 00123│  key fields  │ Case | Region | Campaign … │  ───────▶  │ 14-pl draft  │
 │ Case 00124│  ─────────▶  │ 00123| USA    | P+ - USA  …│  promo-ops │ 10-pl draft  │
 │ Case 00125│              │ 00124| USA    | P+ - USA  …│   batch    │ 10-pl draft  │
 └───────────┘              └───────────────────────────┘            └──────────────┘
                                          │                                  │
                                          └──────── results.csv ─────────────┘
                                   Case 00123 → IO link ✅ · 00124 → IO link ✅ …
```

You fill the sheet once, run once, and get a **results CSV that maps every Salesforce Case
number to its FreeWheel IO link + status**. Paste that column straight back onto the cases.

## How the rows get into the sheet (the form still does the heavy lifting)
Two ways to add a case row — use whichever fits:

1. **From the form (best for real targeting).** The planner fills the same
   `campaign-plan-form.html` they already know — including the 188k-show / channel
   type-to-search — enters the **Salesforce Case #**, then clicks **"Copy row for Sheet"**
   and pastes into the next empty line of the Sheet. The form builds the row in the exact
   column order; the paste drops it across the columns. The form is the row-builder; the
   Sheet is the queue.
2. **Straight into the Sheet (best for simple cases).** Type into the columns, using the
   dropdown pick-lists on Region / Campaign / targeting. No form needed.

Either way the Sheet ends up with one row per case, and the batch command reads them all.

## 1. Fill the sheet (one row per case)
Start from **`templates/batch/cases-batch-template.csv`** (importable to Google Sheets).
One row = one case. Columns are the same friendly fields as the form; list fields
(durations, genres, showlist, Pluto channels, audience segments, excludes) hold
**`;`-separated** values in a single cell.

| Column | Example |
|---|---|
| Salesforce Case | `00123456` |
| Region | `USA` |
| Campaign Name | `Paramount + - USA` |
| Promoted Title | `Yellowstone` |
| Content Type / Content ID | `show` / `54321` |
| Video Durations | `15;30` |
| Flight Start / End | `2026-08-10` / `2026-09-10` |
| Genres | `Drama;Westerns` |
| Showlist | `NCIS;FBI` |
| Pluto Categories / Channels | `Drama` / `Westerns` |
| Audience Segments | `Adults 25-54` |
| Exclude Series / Channels | `Yellowstone` / `Westerns` |
| Include Pause Ads | `Y` |

> This can be a **Google Sheet** (approved connector) exported to CSV, or a CSV kept in
> Drive. The team maintains it like any tracker; the tool reads a row per case.

## 2. Dry-run the whole batch (nothing is created)
```bash
promo-ops batch cases.csv --out results.csv                 # from a CSV export
promo-ops batch --sheet <GOOGLE_SHEET_ID> --out results.csv  # straight from the live Sheet
```
Prints one line per case — region, placement count, and the IO name it *would* create —
plus a `results.csv`. **Nothing is written to FreeWheel.** Eyeball it like a hand-built order.

```
Batch DRY-RUN: 3 case(s)
  3 would-create

  • 00123456   USA    14 pl  dry-run   Yellowstone - USA
  • 00123457   USA    10 pl  dry-run   Tulsa King - USA
  • 00123458   LATAM  10 pl  dry-run   Land of Women - LATAM
```

## 3. Go live — create every draft
```bash
promo-ops batch cases.csv --live --out results.csv                 # CSV
promo-ops batch --sheet <GOOGLE_SHEET_ID> --live --out results.csv  # live Sheet
```
Builds + creates every row's IO **NOT_BOOKED** (a draft — nothing serves) and writes the
Case→IO map:

```
row,salesforce_case,title,region,campaign,io_name,status,io_id,io_link,placements,note
1,00123456,Yellowstone,USA,Paramount + - USA,Yellowstone - USA,created,96015290,https://mrm.freewheel.tv/…,14,
2,00123457,Tulsa King,USA,Paramount + - USA,Tulsa King - USA,created,96015310,https://mrm.freewheel.tv/…,10,
```

Copy the `io_link` column back onto the Salesforce cases. Done.

## 4. Review + book in FreeWheel
Each IO is a NOT_BOOKED draft. A human reviews and activates it in FreeWheel exactly as
today. The tool never books.

---

## Matching to Salesforce
- Every row carries its **Salesforce Case #**; every result line carries it back. That IS
  the match — no connector required today.
- When the Salesforce API user + connector land later, the **same builder** runs straight
  off the cases (`promo-ops poll-cases`) with no sheet in the middle. The batch sheet is the
  bridge until then, not a throwaway.

## Automatic rules applied to every IO
- **Order-level frequency caps** (set on the IO, no input needed): **adult USA** = 1 per 30 min
  **and** 20 per month; **adult international** = 1 per 30 min; **kids** = 1 per 15 min.
  (Config: `config/frequency_caps.yaml`; verified against production USA adult IOs.)
- **Self-exclusion:** the promoted title's own Video Series is excluded on its targeted
  placements so a promo never runs against itself.

## Safety + re-runs
- **Idempotent:** re-running the same sheet **reuses** each IO (status `reused`) instead of
  duplicating. Fix two rows and re-run the whole file safely — only genuinely new IOs are
  created.
- A row that's missing something doesn't stop the batch: it comes back `needs-info` with the
  reason in the `note` column; every good row still goes through. Fix those rows, re-run.
- Statuses: `created` (new draft) · `reused` (already existed) · `dry-run` (preview) ·
  `needs-info` (couldn't build — see note) · `error` (see note).

## One-liner for the team
> Keep one sheet, one row per case. `promo-ops batch cases.csv` to preview them all,
> `--live` to create every draft, then paste the IO links back onto the cases. Re-running is
> safe — it never duplicates.
