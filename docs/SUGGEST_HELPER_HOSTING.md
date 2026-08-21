# ✨ Suggest Targeting — Hosting Request

**What we're asking for:** a small, always-on internal host to run one lightweight web
helper so our 5-person promo-ops team can use the "Suggest targeting" feature in the
Campaign Plan form from a single shared URL — instead of each person installing and running
it on their own laptop.

---

## What it is

The Campaign Plan form has a **✨ Suggest targeting** button. Given a title (and optionally a
description or a pasted brief), it proposes grounded targeting — comp shows, Pluto channels,
genres, Pluto categories — all matched to our real FreeWheel inventory and to what similar
past campaigns in that region actually ran. It saves the team from building targeting by hand.

That button needs a small backend ("the helper"). The helper does two jobs from one process:
1. **Serves the form** (the web page itself), and
2. **Answers the button** (a single `POST /suggest` endpoint).

It's a ~100-line Python program using only the standard library (plus, optionally, the
Anthropic SDK — see "API key" below). No database. No external services except an optional
outbound call to the Anthropic API when the AI layer is enabled.

## Why we need a shared host

Today the helper runs on **each person's laptop** (`localhost`), which means every user must
clone the repo, install Python 3, install a package, and start a server — and it only works
for whoever set that up. For a team of 5 all creating orders, that doesn't scale.

Running the **one** helper on a shared internal host fixes this: the team opens a single URL,
with **no local setup and no credentials on anyone's machine.**

## What we need from IT

| Item | Requirement |
|---|---|
| **Host** | A small always-on Linux VM (or container). Sizing: **1 vCPU, ~512 MB–1 GB RAM** is plenty for 5 users. No GPU. |
| **Runtime** | Python 3.10+. |
| **Network** | Reachable by the 5 team members **behind our VPN / SSO** — this is an internal tool and should **not** be exposed to the public internet. It listens on one TCP port (default **8770**, configurable). |
| **Outbound** | Only needed **if** we enable the AI layer: HTTPS to the Anthropic API. If we run historicals-only (no key), it needs **no outbound access at all.** |
| **Deploy** | Pull our repo to the host and run one command (below). Can run under `systemd` / a container so it restarts automatically. |

**Start command** (bind on all interfaces so the team can reach it):
```
PROMO_SUGGEST_HOST=0.0.0.0 PROMO_SUGGEST_PORT=8770 PYTHONPATH=src python3 -m promo_ops.suggest_server
```

## API key — optional, and a separate decision

The helper works in **two modes**, and this is the key point for the security review:

- **Historicals-only mode (no API key, no sign-off needed):** suggestions come purely from
  our own past-campaign data. **No data leaves our environment.** This works today and is a
  fine starting point.
- **AI-enhanced mode (optional):** if we set a single **`ANTHROPIC_API_KEY`** on the host, the
  helper adds an AI layer that helps most on **brand-new titles with no prior campaign
  history**. The key lives **only on the server**, never in anyone's browser. Enabling this is
  the item that needs the API-key sign-off we've discussed.

Recommended sequence: **stand it up in historicals-only mode now** (immediate value, no
approval blockers), and **add the API key later** once it's approved — same server, no rework.

## Security summary (for the review)

- Internal-only tool; place it behind VPN/SSO. No public exposure.
- No inbound data storage; no database.
- No credentials in the browser at any point.
- Historicals-only mode makes **zero external calls.**
- With the AI layer on, the only outbound traffic is HTTPS to the Anthropic API, using **one
  server-side key** (not per-user keys).

## Bottom line

One small internal VM + one command gets all 5 of us the feature from a shared link, with no
laptop setup. It's safe to start with no API key (nothing leaves our environment); we can turn
on the optional AI layer later with a single server-side key once that sign-off lands.
