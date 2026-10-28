# The hosted team app (Skydance Pages App)

One web address for the whole team, no installs: **QA an order** (paste an IO id, get the QA report)
and the **campaign plan form** with its ✨ Suggest button working for everyone.

**Version 1 only reads from FreeWheel.** It cannot create or change anything there. Pushing orders
stays on the command line for now.

| Page | What it does |
|---|---|
| `/` | two buttons: QA, form |
| `/review` | **Review a plan:** upload (or paste) a `.plan.json`, or click **Review in tool** on the form, and see exactly what a push would build: placements, tiers, targeting counts, and the Tier 1 audience alerts. Creates nothing and never calls FreeWheel |
| `/qa` | paste up to 5 IO ids, optional "include finished placements", get the report; "Copy report" copies it as markdown |
| `/form` | the campaign plan form, served by the app so Suggest works (no API key in the browser) |
| `/healthz` | "ok" (for the platform's health check) |

Code: `src/promo_ops/webapp.py`. Tests: `tests/test_webapp.py` (no network, fake auditor).

## How it behaves

- One QA at a time; a big IO takes minutes, the page shows progress. A fifth waiting run gets "busy".
- Every run is logged as one JSON line with **who** ran it (`X-Pages-User`): `qa_start`, `qa_done`
  (error/warning counts), `qa_failed`, `suggest`, `denied`. The pasted brief text is never logged.
- Results are shown as plain text only (never built into HTML), with a strict content policy.
- The home page shows who you're signed in as **and the groups the platform sent**, so you can copy the
  exact group name (e.g. `Promo Operations Team`) before turning the allow-list on.
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
   Size: Medium (QA uses about 170 MB). **Set the maximum instances to 1**: QA runs are tracked in the
   app's memory, so a second copy of the app would not know about a run started on the first. Entry point is `app.py` (already at the top of the bundle).
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


## The daily data refresh as a Pages Job (moves the 7am refresh off the Mac)

`jobs/refresh.py` (code in `src/promo_ops/refresh_job.py`) does what the Mac's 7am job does: sync
FreeWheel (series, audience items, attributes), rebuild the picker lists and the form. It works in a
**scratch copy**, checks the result (audience list, series list, segment list and form must all be
complete), and uploads **only the files that changed** to the app's source site, where the app rebuilds
on its own. If a check fails it uploads nothing and the app keeps yesterday's data.

One-time setup in the Pages portal (button names follow the Pages docs; tell me if one differs):

1. **Jobs -> Create.** Name it `promo-ops-refresh`. Source: **Python, from a site**, pointing at
   `promo-ops-app-source` (the same site the app uses). Command: `python jobs/refresh.py`.
2. **Schedule:** `0 7 * * *` with time zone **America/Denver** (7am Mountain).
3. **Settings -> secrets** on the *Job* (it has its own, separate from the app's): `FREEWHEEL_USERNAME`,
   `FREEWHEEL_PASSWORD`, `FREEWHEEL_NETWORK_ID`. Size: Medium.
4. **Let the Job update the source site.** Open the site `promo-ops-app-source` -> **Access** -> **Give
   access** -> **An app or a job of Pages** -> pick `promo-ops-refresh` as an **editor**.
5. **Give the Job its token.** Open the Job -> **Identity** tab -> under **Acting on Pages** press
   **Mount**. Every run then carries a short-lived token at `/var/run/secrets/pages/token`.
6. **Run now**, then read the run's log: it ends with either "Published N file(s)" or "the app's data is
   already current". Anything starting with `!!` says why nothing was published.

Settings the job reads (all optional): `PAGES_API_BASE` (default `https://skydancepages.cloud`),
`PAGES_SITE` (default `promo-ops-app-source`), `PAGES_TOKEN_FILE`.

Keep the Mac's 7am job as a backup for about a week. After that, remove step 4b (the app publish) from
`scripts/refresh_data.sh` so two writers don't compete.

## If something's off

- **"The FreeWheel login isn't set up on this app yet"** -> step 6 secrets are missing.
- **"The QA is busy"** -> four runs are already waiting; try again in a few minutes.
- **Page loads but Suggest says it can't reach the helper** -> the form must be opened from the app's
  `/form`, not from the Drive copy.
- **Did not start** in the portal -> check the App's logs; the app must listen on `$PORT` (it does).
