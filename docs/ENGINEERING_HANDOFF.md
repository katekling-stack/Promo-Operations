# Promo Operations — Engineering Handoff

*Prepared for the engineering hosting / "Suggest targeting" enablement discussion.*
*Owner: Kate Kling (promo ad ops). Repo branch of record: `claude/freewheel-order-placement-templates-p2rjzd`.*

This document is the single starting point for the eng team. It covers **what the system
is**, **what we're asking engineering to do** (host it + enable the Suggest helper), the
**deployment options**, and the **credentials / security posture**. Deeper references are
linked inline.

---

## 1. TL;DR — what we want out of the meeting

Two decisions + one build task:

1. **Host the tool on a shared internal service** so the 5-person promo-ops team uses one URL
   instead of each person running Python on their laptop. *(Today it's laptop-local.)*
2. **Enable the "✨ Suggest targeting" helper** on that host — start in **historicals-only
   mode** (zero external calls, no approval needed), add the optional AI layer later behind a
   single server-side API key.
3. **Own the deploy + refresh** — a small always-on process (systemd unit or container) plus a
   daily data-refresh job we already have scripted.

Nothing here requires new infrastructure beyond **one small Linux VM/container** and a
scheduled job. No database. See §5 for the concrete ask.

---

## 2. What the system is (one screen)

A Python tool (`promo-ops`) that turns a **campaign plan** (title, region, campaign, flight,
durations, products, targeting) into fully-built **FreeWheel Insertion Orders + Placements +
tiered targeting**, created as `NOT_BOOKED` drafts a human then reviews and activates. It never
goes live on its own.

```
 Campaign plan  ─────────────────────────────────────────────┐
 (Salesforce Case · self-serve HTML form · planning sheet)    │
        │  promoted title, region, campaign, flight, products, targeting
        ▼
 Targeting engine  ──►  Tier 1–4 structure applied to the inputs
        ▼
 Order builder     ──►  one Placement per format × tier × duration, per the brand's
        │               live setup (ad units, main SGs / VGs, geo, all exclusions)
        ▼
 FreeWheel API     ──►  IO + Placements created as NOT_BOOKED drafts
        ▼
 Human review      ──►  a CM QAs and activates each draft in FreeWheel
```

- **Coverage:** 15 regions / ~79 promo brands, each reverse-engineered from its live IOs.
- **Language/stack:** Python 3.10+, standard library + `PyYAML`, `requests`, `python-dotenv`.
  No web framework, no DB. (`pyproject.toml` for the full list.)
- **Tests:** 389 passing (`python -m pytest`).
- **Interfaces today:**
  - **CLI** `promo-ops` (build / preview / push / from-case / sync-* / refresh-form / …).
  - **Self-contained HTML form** (`templates/campaign-plan/campaign-plan-form.html`) that CMs
    fill in to produce a plan — this is what the Suggest helper serves.
- Deeper reference: `docs/PROJECT_OVERVIEW.md`, `docs/ARCHITECTURE.md`, `docs/FREEWHEEL.md`.

---

## 3. The two things to host

There are **two separable pieces**. You can host either or both.

### 3a. The Suggest helper (the immediate ask)

The HTML form has a **✨ Suggest targeting** button. Given a title (+ optional description or
pasted brief) it proposes grounded targeting — comp shows, Pluto channels, genres, Pluto
categories — matched to real FreeWheel inventory and to what similar past campaigns in that
region actually ran.

- **What it is:** a ~130-line stdlib Python HTTP server (`src/promo_ops/suggest_server.py`,
  `ThreadingHTTPServer`). It does two jobs from one process: **serves the form** and
  **answers `POST /suggest`**. No database.
- **Two modes (this is the key security point):**
  - **Historicals-only (default, no key):** suggestions come only from our own past-campaign
    corpus (`data/history/corpus.jsonl`). **Zero external calls — no data leaves our
    environment.** Works today.
  - **AI-enhanced (optional):** set one `ANTHROPIC_API_KEY` on the host and it adds an AI
    layer that helps most on brand-new titles with no history. The key lives **only on the
    server**, never in a browser. This is the item that needs the API-key sign-off.
- **Start command:**
  ```bash
  PROMO_SUGGEST_HOST=0.0.0.0 PROMO_SUGGEST_PORT=8770 PYTHONPATH=src \
    python3 -m promo_ops.suggest_server
  ```
- Full IT-facing writeup: **`docs/SUGGEST_HELPER_HOSTING.md`**.

### 3b. The order-building CLI (the pushes to FreeWheel)

Building/pushing orders (`promo-ops push … --live`, `from-case`, batch) talks to the FreeWheel
production API and needs **FreeWheel credentials** (see §4). This is separate from the Suggest
helper: the Suggest helper needs **no** FreeWheel credentials.

Options for where the pushes run:
- **Keep on operator machines** for now (status quo) and only host the Suggest helper. Lowest
  lift; unblocks the team's immediate pain.
- **Or** run the CLI on the same host (or a scheduled worker) for Case-driven automation
  (`poll-cases` → drafts). Needs FreeWheel creds on the host + Salesforce wiring (in progress).

**Recommended sequence:** host the Suggest helper first (§3a), keep pushes operator-side, then
move the CLI/automation server-side once Salesforce + credential storage are settled.

---

## 4. Credentials & configuration

All config is via environment variables (a `.env` file is supported via `python-dotenv`).
Nothing is hard-coded; nothing is stored in the browser.

| Variable | Used by | Needed for |
|---|---|---|
| `ANTHROPIC_API_KEY` | Suggest helper | **Optional.** Enables the AI layer. Absent → historicals-only. |
| `PROMO_SUGGEST_HOST` / `PROMO_SUGGEST_PORT` | Suggest helper | Bind address / port (default `127.0.0.1:8770`; use `0.0.0.0` to share). |
| `FREEWHEEL_USERNAME` / `FREEWHEEL_PASSWORD` | CLI push/sync | FreeWheel Streaming Hub login (OAuth 2.1 PKCE → JWT). **Works today.** |
| `FREEWHEEL_NETWORK_ID`, `FREEWHEEL_ENVIRONMENT`, `FREEWHEEL_HUB_URL` | CLI | FreeWheel environment routing. |
| `FREEWHEEL_MRM_CLIENT_ID` / `FREEWHEEL_MRM_CLIENT_SECRET` | CLI | MRM API (client-credentials) — used to auto-create the IO Brand on push. **Not yet provisioned**; without it the IO Brand is set by hand. |
| `FREEWHEEL_ADVERTISER_NAME_FILTER`, `FREEWHEEL_RETRY_*` | CLI | Optional tuning. |

**Auth model:** FreeWheel login is username/password → OAuth PKCE → short-lived JWT, refreshed
automatically by the client. Credentials should live in the host's secret store / env, not in
the repo. Run `promo-ops doctor` to verify connectivity + which creds are present.

---

## 5. The concrete ask for engineering

| Item | Requirement |
|---|---|
| **Host** | One small always-on Linux VM or container. **1 vCPU, 512 MB–1 GB RAM** is plenty for 5 users. No GPU, no DB. |
| **Runtime** | Python 3.10+. `pip install -e .` (or `PYTHONPATH=src`). |
| **Network (Suggest)** | Reachable by the 5 users **behind VPN/SSO**. **Not** public. One TCP port (default 8770). |
| **Outbound** | Suggest historicals-only: **none.** Suggest AI layer: HTTPS to the Anthropic API only. CLI push: HTTPS to FreeWheel. |
| **Process mgmt** | Run under `systemd` or a container so it auto-restarts. (Sample launchd plist for the daily refresh: `deploy/com.paramount.promoops.refresh.plist`.) |
| **Scheduled refresh** | A daily job runs `promo-ops refresh-form` to pull the latest FreeWheel series/audiences/site-groups into the form dropdowns + historicals corpus. See `docs/SCHEDULED_REFRESH.md`. Needs FreeWheel creds. |
| **Secrets** | Env/secret store for `ANTHROPIC_API_KEY` (if AI on) and `FREEWHEEL_*` (if the CLI runs on the host). |

### Suggested rollout order
1. **Now:** stand up the Suggest helper in **historicals-only** mode behind VPN. Immediate
   value, no approval blockers, no external traffic.
2. **Then:** once the API-key sign-off lands, add `ANTHROPIC_API_KEY` on the same host — no
   rework, just a restart.
3. **Later:** move order-building / Case automation server-side once Salesforce field setup +
   FreeWheel MRM credentials are provisioned.

---

## 6. Security posture (for the review)

- **Internal-only.** Place behind VPN/SSO; do not expose to the public internet.
- **No inbound data storage, no database.** The helper holds nothing between requests.
- **No credentials in the browser**, ever. All secrets are server-side env.
- **Historicals-only mode makes zero external calls** — nothing leaves our environment.
- **AI layer:** the only outbound traffic is HTTPS to the Anthropic API using **one
  server-side key** (not per-user keys). It sends the title/description/brief text for the
  campaign being planned; it does not send FreeWheel credentials or bulk data.
- **FreeWheel pushes** (CLI) create **NOT_BOOKED drafts only** — a human reviews/activates.
  The tool never books or serves anything on its own.

---

## 7. Open dependencies / not-yet-done

- **Salesforce field + credential setup** (in progress) — needed for full Case→drafts
  automation. Building/pushing from a plan/form does **not** depend on it. See the `docs/SALESFORCE_*` set.
- **FreeWheel MRM client-credentials** not yet provisioned — without them the IO Brand is set
  by hand on push (everything else works).
- **Placement hard-delete** isn't cleanly supported by the FreeWheel gateway we use; cleanup
  of stray placements is done in the FreeWheel UI today.

---

## 8. Pointers (repo map)

| Path | What |
|---|---|
| `src/promo_ops/suggest_server.py` | The Suggest helper (serves form + `/suggest`). |
| `src/promo_ops/suggest.py` | Suggest logic (brief + AI + historicals, grounded to inventory). |
| `src/promo_ops/order_builder.py`, `targeting.py` | Order + tiered-targeting builders. |
| `src/promo_ops/integrations/freewheel.py` | FreeWheel Streaming Hub client (auth, create, sync). |
| `templates/campaign-plan/campaign-plan-form.html` | The self-serve intake form (generated). |
| `scripts/build_plan_form.py` | Regenerates the form from config. |
| `config/*.yaml` | Brands, placement templates, regions, campaign repoints, etc. |
| `data/history/corpus.jsonl` | Historicals corpus that powers Suggest's grounding. |
| `docs/SUGGEST_HELPER_HOSTING.md` | IT-facing hosting request for the Suggest helper. |
| `docs/SCHEDULED_REFRESH.md` | The daily data-refresh job. |
| `docs/PROJECT_OVERVIEW.md` / `docs/ARCHITECTURE.md` / `docs/FREEWHEEL.md` | System deep-dives. |
| `docs/INSTALL_CHECKLIST.md` | Step-by-step local/host install. |
