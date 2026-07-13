# Salesforce Sandbox — connection & first end-to-end run

The step-by-step for standing up the sandbox connection and running one Case
end-to-end (Frisco King) as a FreeWheel **draft**. Everything here is safe to do before
production — nothing books or launches.

## Prereqs (from the admin — see the proposal)

1. Custom fields created on the Case object per `docs/salesforce-case-fields.csv`.
2. Status values **"Ready for Automation"** + **"Needs Info"**, and Reason value
   **"Submitted to FreeWheel"** added.
3. An **API user** in the sandbox (integration user or your user) with:
   Read on Case + the new fields, Read on Files/ContentDocument, Create on CaseComment,
   Edit on Case Status/Reason.
4. (Optional) A **Connected App** if you're using OAuth instead of user+token.

## 1. Install the Salesforce extra

```bash
pip install -e '.[salesforce]'
```

## 2. Fill in `.env` (sandbox)

Copy `.env.example` → `.env` and set the Salesforce block:

```
SALESFORCE_DOMAIN=test                 # sandbox logs in at test.salesforce.com
SALESFORCE_USERNAME=you@company.com.sandboxname
SALESFORCE_PASSWORD=•••••
SALESFORCE_SECURITY_TOKEN=•••••        # Setup ▸ Reset My Security Token (emailed)
# Only if using a Connected App:
# SALESFORCE_CLIENT_ID=...
# SALESFORCE_CLIENT_SECRET=...
```

> **Sandbox username gotcha:** it's your prod username with the sandbox name appended,
> e.g. `jane@paramount.com.uatsandbox`. The security token is a *separate* token for the
> sandbox — reset it while logged into the sandbox.

## 3. Preflight — prove login + schema

```bash
promo-ops salesforce-check
```

This logs in (proving credentials/access) and describes the Case object, then reports:
- which of the required Case fields exist / are missing, and
- whether the Status/Reason values are present.

A clean run prints `✅ Schema OK — the org is ready.` Anything missing is listed by
API name so the admin can finish it (cross-reference `salesforce-case-fields.csv`). Fix
and re-run until green.

## 4. Dry-run one Case (no writes)

Create a test Case in the sandbox using the Frisco King example
(`docs/SALESFORCE_EXAMPLE_CASE.md`), attach the Targeting sheet, then:

```bash
promo-ops from-case <CASE_ID>          # dry-run: builds + validates, creates nothing
```

You'll see the validation result and the comment body that *would* be posted. This
exercises the full Case→plan→order path against real Case data without touching
FreeWheel or writing back to the Case.

## 5. Live end-to-end (creates a FreeWheel DRAFT)

With FreeWheel sandbox creds also set (`FREEWHEEL_*`, test network 520310):

```bash
promo-ops from-case <CASE_ID> --live   # creates the draft IO + comments back on the Case
```

Expected result:
- a **draft** Insertion Order + placements in FreeWheel (NOT booked),
- a Case **comment** with the draft IO link + CM to-dos,
- Case **Reason → "Submitted to FreeWheel."**

If the Case is missing something, instead you'll get a comment listing the problems and
**Status → "Needs Info."**

## 6. Poll mode (optional)

Once a few Cases look right, process every flagged Case in one shot:

```bash
promo-ops poll-cases            # dry-run all Cases with Status = "Ready for Automation"
promo-ops poll-cases --live     # create drafts for all of them
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `INVALID_LOGIN` | Wrong sandbox username (needs `.sandboxname` suffix) or stale token. Reset the security token **in the sandbox**. |
| `Could not connect` | `SALESFORCE_*` not set, or `SALESFORCE_DOMAIN` not `test` for a sandbox. |
| Preflight lists missing fields | Admin hasn't created those Case fields yet — see `salesforce-case-fields.csv`. |
| Targeting not picked up | The attached file's title must contain "Targeting"; export/save it as CSV. |
| `simple-salesforce not installed` | `pip install -e '.[salesforce]'`. |

*Code: connection + preflight in `src/promo_ops/integrations/salesforce.py`
(`_connect`, `preflight`, `check_case_schema`); the Case flow in `casework.py`; CLI in
`cli.py` (`salesforce-check`, `from-case`, `poll-cases`).*
