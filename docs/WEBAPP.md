# The hosted team app (Skydance Pages App)

One web address for the whole team, no installs: **QA an order** (paste an IO id, get the QA report)
and the **campaign plan form** with its ✨ Suggest button working for everyone.

**Version 1 only reads from FreeWheel.** It cannot create or change anything there. Pushing orders
stays on the command line for now.

| Page | What it does |
|---|---|
| `/` | two buttons: QA, form |
| `/qa` | paste up to 5 IO ids, optional "include finished placements", get the report; "Copy report" copies it as markdown |
| `/form` | the campaign plan form, served by the app so Suggest works (no API key in the browser) |
| `/healthz` | "ok" (for the platform's health check) |

Code: `src/promo_ops/webapp.py`. Tests: `tests/test_webapp.py` (no network, fake auditor).

## How it behaves

- One QA at a time; a big IO takes minutes, the page shows progress. A fifth waiting run gets "busy".
- Every run is logged as one JSON line with **who** ran it (`X-Pages-User`): `qa_start`, `qa_done`
  (error/warning counts), `qa_failed`, `suggest`, `denied`. The pasted brief text is never logged.
- Results are shown as plain text only (never built into HTML), with a strict content policy.
- Optional extra lock: set `PROMO_ALLOWED_GROUPS` (`;`-separated group names). Anyone whose
  `X-Pages-Groups` doesn't include one gets 403. The portal's own access setting is the main lock.

## One-time setup in the Pages portal

1. **New site** (Source: *Off / storage only*), e.g. `promo-ops-app-source`. This only holds the files.
2. On that site: **Deploy keys** -> add the public key of a **new** key pair:
   `ssh-keygen -t ed25519 -N "" -f ~/.ssh/skydance_pages_promo_ops_app`, paste the `.pub` line.
   The portal shows a `site-key-...` account name; it is the default in `scripts/publish_site.py`
   (override with `SKY_PAGES_APP_USER`).
3. Connect once so the host key is known (same as the first site, see `SITE_PUBLISHING.md`).
4. Publish the files: `python3 scripts/publish_site.py --app` (add `--dry-run` first to see the list).
5. **New App** on a site of its own (Source: *Python, from a site*, pointing at the source site above).
   Size: Medium (QA uses about 170 MB). Entry point is `app.py` (already at the top of the bundle).
6. **Settings -> secrets** on the App: `FREEWHEEL_USERNAME`, `FREEWHEEL_PASSWORD`,
   `FREEWHEEL_NETWORK_ID` (and `FREEWHEEL_HUB_URL` / `FREEWHEEL_ENVIRONMENT` only if yours differ from
   the defaults). Use a read-only FreeWheel user if one exists. Optional: `ANTHROPIC_API_KEY`
   (turns on the AI layer in Suggest), `PROMO_ALLOWED_GROUPS`.
7. **Access -> Restricted**, and add the promo team's group.
8. Open it, paste an IO id, check the report matches `promo-ops qa <id>` on your Mac.

## Keeping it current

`scripts/refresh_data.sh` (7am) republishes the app source after refreshing the data, as long as
the app's deploy key (`~/.ssh/skydance_pages_promo_ops_app`) exists on that Mac. Pages redeploys when the files change. By hand:
`python3 scripts/publish_site.py --app`.

What goes in the bundle (tested): `app.py`, `requirements.txt`, `src/`, `config/`, `data/`, the form,
and the `templates/targeting-options/*.csv` lists. Never `.env`, hidden files, keys, logs or plans.

## If something's off

- **"The FreeWheel login isn't set up on this app yet"** -> step 6 secrets are missing.
- **"The QA is busy"** -> four runs are already waiting; try again in a few minutes.
- **Page loads but Suggest says it can't reach the helper** -> the form must be opened from the app's
  `/form`, not from the Drive copy.
- **Did not start** in the portal -> check the App's logs; the app must listen on `$PORT` (it does).
