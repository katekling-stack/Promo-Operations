# Salesforce Integration — Implementation Plan

The one-page "who does what, in what order" to get the Case → FreeWheel automation
live. The tool is **built, tested (180 tests), and running against FreeWheel production
for 15 regions / 153 campaigns today** — this plan covers only the Salesforce wiring,
which is configuration + credentials, not new code.

**Owners:** 🟦 *SF Admin* (Salesforce config) · 🟩 *Ad Ops / us* (the tool) · 🟨 *Together*

---

## Phase 0 — Align (this meeting)
| # | Step | Owner | Done when |
|---|---|---|---|
| 0.1 | Agree Salesforce is the **intake only** — no ad-ops logic in SF | 🟨 | Shared understanding |
| 0.2 | Decide the **4 open questions** (targeting sheet vs fields; picklist upkeep; trigger mechanism; pilot region) — see `SALESFORCE_FIELD_MAPPING.md` §7 | 🟨 | Answers recorded |
| 0.3 | Pick the **pilot region** (recommend USA) | 🟨 | Chosen |
| 0.4 | Confirm who the **integration user** is + sandbox availability | 🟦 | Named |

## Phase 1 — Build the Case object 🟦
| # | Step | Reference | Done when |
|---|---|---|---|
| 1.1 | Create the **7 required fields** (minimal path) | `salesforce-case-fields.csv` (Required rows) | Fields exist in sandbox |
| 1.2 | Add the **3 Status/Reason picklist values** (Ready for Automation, Needs Info, Submitted to FreeWheel) | `SALESFORCE_FIELD_MAPPING.md` §4 | Values added |
| 1.3 | *(Optional now / later)* create the remaining **28 fields** (optional, products, overrides) | full CSV | Full spec built |
| 1.4 | Confirm we can **attach + read** a "Targeting" sheet on a Case | §5 | Attachment readable |
| 1.5 | Flag any **API-name conventions** to change | — | We update `CASE_FIELD_MAP` (one file) |

## Phase 2 — Connect 🟦→🟩
| # | Step | Reference | Done when |
|---|---|---|---|
| 2.1 | Provision **sandbox + Connected App** (or integration user + token) | `SALESFORCE_GOLIVE.md` §2 | Creds issued |
| 2.2 | Drop creds into `.env`; `pip install -e '.[salesforce]'` | §2 | Installed |
| 2.3 | Run `promo-ops salesforce-check` | §3 | **Green** = every field + picklist present |

> `salesforce-check` is the go/no-go gate. Red output lists exactly what's missing, so
> Phase 1 and 2 loop until it's green — no guesswork.

## Phase 3 — Pilot one Case 🟩
| # | Step | Command | Done when |
|---|---|---|---|
| 3.1 | Create one **test Case** in the pilot region + attach Targeting | — | Case flagged "Ready for Automation" |
| 3.2 | **Dry-run** (no writes) | `promo-ops from-case <ID>` | Order previews correctly |
| 3.3 | **Live** — create the NOT_BOOKED draft | `promo-ops from-case <ID> --live` | Draft IO in FreeWheel + link commented on the Case |
| 3.4 | A human **reviews + activates** the draft in FreeWheel | — | Confirms parity with a hand-built order |

## Phase 4 — Automate + roll out 🟩
| # | Step | Command | Done when |
|---|---|---|---|
| 4.1 | Schedule the **poller** (cron every ~5 min, idempotent) | `SALESFORCE_GOLIVE.md` §6 | Ready Cases process unattended |
| 4.2 | Turn on the **run-log + daily digest** | `poll-status`, `daily-digest` | Audit trail + EOD summary |
| 4.3 | **Expand** from pilot region to all 15 | — | Planners submit Cases for any market |

---

## The critical path (shortest route to a live draft)
**7 fields (1.1) → 3 picklist values (1.2) → creds (2.1–2.2) → `salesforce-check` green (2.3) → one live Case (3.3).**
Everything else (remaining fields, poller, rollout) can follow once that loop works once.

## What each side needs from the other
- **SF Admin needs from us:** `salesforce-case-fields.csv` (fields), the Status/Reason
  values, and the field mapping doc. All provided, generated from live config.
- **We need from SF Admin:** the fields created, the picklist values, a sandbox +
  integration creds, and confirmation the Targeting attachment is readable.

## Reference docs (hand over)
| Doc | For | What it is |
|---|---|---|
| `SALESFORCE_FIELD_MAPPING.md` (+PDF) | 🟦 Admin | What to build: minimal 7, full 35, picklists, open Qs |
| `salesforce-case-fields.csv` | 🟦 Admin | Import-ready field list (live config) |
| `SALESFORCE_GOLIVE.md` | 🟩 Us | Technical runbook: creds → preflight → schedule |
| `SALESFORCE_EXAMPLE_CASE.md` | 🟨 Both | An annotated example Case (planner fills vs. derived) |
| `FRIDAY_DEMO.md` | 🟨 Both | Live demo script (form, automation, mirror) |

## Risks / decisions to watch
- **Picklist drift** — Campaign (153) / Brand lists change as markets are added. We can
  regenerate the CSV on demand (`python scripts/build_salesforce_fields.py`); decide
  whether admin re-pastes or we automate a sync later.
- **API-name conventions** — if the org standardizes names, they change in one file
  (`CASE_FIELD_MAP`) and the CSV + parser stay in sync.
- **Targeting model** — recommend the attached sheet (variable-length lists) over
  modeling every list as a field.
- **Scope creep** — keep phase 1 to the pilot region + 7 fields; prove the loop before
  building all 35 fields × 15 regions.
