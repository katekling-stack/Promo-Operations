# Salesforce Automation — Where We Stand & What's Needed

**One-page handoff for the team helping us finish the Salesforce piece (or find a workaround).**

Repo: `github.com/katekling-stack/Promo-Operations` · working branch:
`claude/freewheel-order-placement-templates-p2rjzd`

---

## TL;DR

The tool that builds FreeWheel Insertion Orders + all placements (tiering, naming, ad
units, geo, frequency caps, time zones, self-exclusions, per-brand products) is **built,
tested (46 test files), and running against FreeWheel production** for **15 regions / 153
campaigns**. It already creates real `NOT_BOOKED` drafts end-to-end.

The **only** thing left for "fully automated" is letting a Case in Salesforce kick it off
instead of a person. **All of that code is already written and unit-tested** — the
remaining work is **Salesforce configuration + credentials**, not new engineering.

There is also a **zero-API workaround that already works today** (see §4) — so we are not
blocked on Salesforce to keep operating; the integration just removes the last manual step.

---

## 1. The target flow (what "fully automated" looks like)

```
Planner fills a Case ──▶ sets Status = "Ready for Automation"
                                  │  (poller runs every ~5 min, idempotent)
       Case core fields  +  attached "Targeting" sheet
                                  │
                       build_plan_dict()  ──▶  validated plan
                                  │
                    build Order + ~14 Placements
                                  │
                     create DRAFT IO in FreeWheel
                 ┌────────────────┴────────────────┐
            success:                           can't build:
   Reason = "Submitted to FreeWheel"      Status = "Needs Info"
   + comment w/ the IO link on the Case   + comment w/ the reason
```

**Salesforce is intake only** — no ad-ops logic lives there. It captures ~7 fields and a
status flag; the tool does everything else.

## 2. What's already built on our side (no more code needed)

All of this is committed and tested:

| Piece | What it does | Command / code |
|---|---|---|
| Case → plan transform | Reads Case fields + attached Targeting sheet → plan | `build_plan_dict()` — `tests/test_from_case.py` |
| Preflight / readiness check | Logs in, describes the Case object, reports every missing field or picklist value (green/red go-signal) | `promo-ops salesforce-check` — `tests/test_salesforce_preflight.py` |
| Run one Case | Validate + build + create the draft; comment the IO link back | `promo-ops from-case <ID> [--live]` |
| Poller (unattended) | Process every Case flagged "Ready for Automation"; **idempotent** (never duplicates an IO); watch-loop or cron | `promo-ops poll-cases [--live] [--watch --interval 300]` |
| Audit trail + digest | JSONL run log + shareable end-of-day summary | `poll-status`, `daily-digest` |
| SF client | login (user/token **or** Connected App), read Case, download Targeting attachment, write Status/Reason, post comment, retry/backoff | `integrations/salesforce.py` |

The **only** placeholders in the code are the field **API names** (`CASE_FIELD_MAP`) — if
the org standardizes names differently, we change them in **one file** and everything stays
in sync.

## 3. What we need from Salesforce (the whole ask)

This is the entire critical path. Detail in `SALESFORCE_ADMIN_ASKS.md` + the import-ready
`salesforce-case-fields.csv`.

1. **7 required Case fields** (minimal path): Promoted Title, Region, Language, Campaign
   Name, Flight Start, Flight End, Video Durations. *(30 more optional fields exist in the
   CSV for overrides/products — can follow later.)*
2. **3 picklist values** on existing Status/Reason fields: Status = `Ready for Automation`,
   Status = `Needs Info`, Reason = `Submitted to FreeWheel`.
3. A way to scope *which* Cases are ours — a **"Campaign Setup Form" Record Type or a
   checkbox**.
4. **A sandbox + an integration user** (username + password + security token) **or a
   Connected App** that can read Cases + these fields and write Status/Reason + a Case
   comment.
5. Confirm we can **attach & read a "Targeting" sheet** on a Case (holds the
   variable-length targeting lists).

**Acceptance gate:** once the above exist, `promo-ops salesforce-check` prints green/red in
one shot — that's the single go/no-go signal. Then we run one pilot Case (recommend USA)
end-to-end, then schedule the poller.

## 4. The workaround (works today, zero Salesforce API access)

If provisioning an integration user is slow, we are **not blocked**. The same Case → plan →
order pipeline runs from a **local file** — no Salesforce connection at all:

- `promo-ops from-case-file <case.json> [--targeting <targeting.csv>] [--live]` — one Case
  exported to JSON.
- `promo-ops batch <cases.csv> --out results.csv` — a whole day's campaigns at once
  (this is the interim form → Google Sheet → batch path already in use).

So the practical fallbacks, in order of effort:
1. **Now:** planner fills the form → export/paste rows → `batch`. (Live today.)
2. **Light-touch:** a Salesforce report/export of "Ready" Cases → CSV → `batch` on a
   schedule. No write-back, but fully drives the build.
3. **Full automation:** the API poller in §1–3 (write-back + comments + hands-off).

## 5. Open questions for the team

- **Targeting: attached sheet vs. more Case fields?** We recommend the attached sheet
  (lists vary in length). 
- **Picklist upkeep** — Campaign (153) + Brand lists grow as markets are added; regenerate
  from config on demand (`scripts/build_salesforce_fields.py`). Admin re-paste vs. automated
  sync — decide.
- **Trigger** — a Status value is simplest; a checkbox / Record Type / queue is an easy swap.
- **Pilot scope** — start with USA to prove the loop, then open all 15.

## 6. Files to hand the team

| File | For whom | What it is |
|---|---|---|
| `docs/SALESFORCE_HANDOFF.md` (this) | Everyone | Where we stand + the whole ask |
| `docs/SALESFORCE_ADMIN_ASKS.md` | SF admin | One-page build sheet (their tasks only) |
| `docs/salesforce-case-fields.csv` | SF admin | Import-ready field list (from live config) |
| `docs/SALESFORCE_FIELD_MAPPING.md` (+PDF) | Both | Full mapping: minimal 7, full 37, picklists, open Qs |
| `docs/SALESFORCE_IMPLEMENTATION_PLAN.md` (+PDF) | Both | Phased who-does-what-in-what-order |
| `docs/SALESFORCE_GOLIVE.md` | Us | Technical runbook: creds → preflight → schedule |
| `docs/salesforce-teammate-email.md` | You | Ready-to-send intro email/Slack |

---
*This page summarizes the current state. The engine specifics live in `docs/ARCHITECTURE.md`
and `docs/PROJECT_OVERVIEW.md`.*
