# Pre-launch QA — how to use it

`promo-ops qa` reviews a **live** FreeWheel Insertion Order (and all of its placements) against
the tool's own rules and tells you what looks wrong **before you set it live**. You give it an
**IO ID**; it does the rest. Nothing is changed in FreeWheel — it only *reads* and reports.

---

## Quick start

Open a terminal **inside the `Promo-Operations` folder** (same place you run pushes from), then:

```
promo-ops qa 80271357                  # review one IO
promo-ops qa 80271357 96525273         # review several at once
promo-ops qa 80271357 --out qa.md      # also save a shareable report file (qa.md)
promo-ops qa 80271357 --only "Tier 4"  # only show placements whose name contains this text
```

The **IO ID** is the number in the FreeWheel URL for the order, e.g.
`…/insertion_order_id=80271357…` → `80271357`.

---

## What it checks (every placement)

- **Ad units** — correct ad-unit group for the brand + format; **pre-roll dropped at :30+**;
  bumper units present; never empty.
- **Creative duration** — the creative length matches the duration the line is named for
  (a "…30 (Tier 1)…" line should carry a :30).
- **Time zone** — the placement schedule is in the market's time zone.
- **Targeting / relationships** — right main inventory; no Pluto in no-Pluto regions; Samsung
  excluded for Pluto TV brands; Recommended Show only on P+/Pluto TV; AU Tier 4 UFC set present.
- **Frequency caps** — order-level (per region) and placement-level (per tier).
- **Priority / precedence**, **naming**, and **geo**.

## How to read the report

Each line is tagged:

| Tag | Meaning |
|---|---|
| ❌ **error** | Almost certainly wrong — fix before going live. |
| ⚠️ **warn** | Likely wrong — check it. |
| ℹ️ **info** | Couldn't read that field from FreeWheel — verify by hand. |
| ✅ **ok** | Verified correct. |

The summary line at the bottom says how many errors/warnings were found. If there are **0
errors**, the structure matches what the tool would have built.

> Tip: `--out qa.md` writes a tidy table you can drop into Slack or a ticket.

---

## Does it have to be in Terminal?

**For now, yes** — it's a command-line tool, run the same way as the build/push commands. It has
to run on a machine that holds the FreeWheel API login (that login can't live in a web browser),
which is why it's a terminal command today. A web page where you paste an IO ID is on the
roadmap for when the tool is hosted on a shared server — the QA engine is already written so it
can sit behind that page later with no rework.

---

## Getting it onto each campaign manager's computer

`promo-ops qa` is part of the **same `promo-ops` tool** the team already uses to build/push
orders. So:

- **If a CM already runs `promo-ops` (build/push):** they already have it. They just need the
  latest code:
  ```
  ./update.sh
  ```
  Then `promo-ops qa <IO id>` works immediately.

- **If a CM is brand new to the tool:** they do the **one-time setup** in
  [`docs/INSTALL_CHECKLIST.md`](INSTALL_CHECKLIST.md) — about 15 minutes, copy/paste, no coding:
  1. Install Python.
  2. Get the `Promo-Operations` code (clone or unzip the repo).
  3. Create their `.env` with the FreeWheel API login (the same `AdOps.api@520311` access Ad Ops
     already uses — see `.env.example`).
  4. Install the tool from inside the folder:
     ```
     python -m pip install -e .
     ```
  After that, `promo-ops qa <IO id>` (and every other `promo-ops` command) works for them.

### What each CM needs
- The `Promo-Operations` code (kept current with `./update.sh`).
- A `.env` file with the FreeWheel API login (read access is all QA needs).
- Python 3.10+.

They do **not** need the form or Google Drive to run QA — just the terminal and an IO ID.
