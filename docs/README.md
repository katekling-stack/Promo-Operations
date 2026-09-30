# Promo-Ops — Team Handbook

Everything a campaign manager / Ad Ops needs, start to finish. Pick where you are:

| I want to… | Go to |
|---|---|
| **Set up the tool on my computer** (clone from GitHub, first time) | [`CLONE_SETUP.md`](CLONE_SETUP.md) |
| Shorter one-page setup (Python + `.env` + install) | [`INSTALL_CHECKLIST.md`](INSTALL_CHECKLIST.md) |
| **Build & push an order** (form → draft in FreeWheel) | [`TEAM_WORKFLOW.md`](TEAM_WORKFLOW.md) |
| Filling out the campaign **form** | [`AD_OPS_FORM_RUNBOOK.md`](AD_OPS_FORM_RUNBOOK.md) |
| **QA a live order** before booking | [`QA_GUIDE.md`](QA_GUIDE.md) |
| Keep the tool up to date | run `./update.sh` |

---

## The whole flow at a glance

```
          ┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐     ┌───────────────┐
  CM  →   │ Fill the FORM│  →  │ Ad Ops: PREVIEW + │  →  │ QA the live IO   │  →  │ CM reviews &  │
          │ (per campaign)│     │ PUSH the draft    │     │ (promo-ops qa)   │     │ BOOKS it live │
          └──────────────┘     └───────────────────┘     └──────────────────┘     └───────────────┘
              browser              Terminal                  Terminal                 FreeWheel
```

Everything the tool creates is a **NOT_BOOKED draft** — nothing serves until a Campaign Manager
books it in FreeWheel. The tool never books or goes live on its own.

---

## 1. One-time setup (each person, once)
Clone the code from GitHub, create your own `.env` with the FreeWheel login, and install the
tool. Full steps: **[`CLONE_SETUP.md`](CLONE_SETUP.md)**. When done, `promo-ops --help` works in
your terminal.

Keep current anytime with:
```
./update.sh
```

## 2. Build & push an order
The day-to-day flow (fill the form → download the plan → preview → push a NOT_BOOKED draft),
for one campaign or a whole batch: **[`TEAM_WORKFLOW.md`](TEAM_WORKFLOW.md)**.

Core commands (run from inside the `Promo-Operations` folder):
```
promo-ops preview <file>.plan.json                                  # eyeball it — creates nothing
promo-ops push    <file>.plan.json --target freewheel --live       # push the NOT_BOOKED draft
promo-ops batch   <file>.csv --live --out results.csv              # push a whole batch
```

## 3. QA before it goes live
Run the pre-launch review on the new IO id (the push prints it) to catch mistakes — ad units,
creative duration, time zone, targeting/relationships, frequency caps, priority, naming, geo —
while it's still a draft: **[`QA_GUIDE.md`](QA_GUIDE.md)**.
```
promo-ops qa <IO id>               # review one order
promo-ops qa <IO id> --out qa.md   # + a shareable report file
```
Fix anything flagged ❌, then hand off to the CM to review and book.

---

## Handy reference

| Command | What it does |
|---|---|
| `./update.sh` | Get the latest tool + form |
| `promo-ops preview <file>.plan.json` | Show the tiers/targeting for one plan (creates nothing) |
| `promo-ops push <file>.plan.json --target freewheel --live` | Create one NOT_BOOKED draft |
| `promo-ops batch <file>.csv --live --out results.csv` | Create drafts for a whole sheet |
| `promo-ops qa <IO id>` | Audit a live order against the rules before booking |
| `promo-ops doctor` | Preflight check (login + data files) before pushing |
| `promo-ops --help` | List every command |

> Golden rule: always run the **preview / no-`--live`** version first, and re-running is safe —
> existing drafts are reused, never duplicated.
