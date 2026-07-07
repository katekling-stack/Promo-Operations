# Architecture

## Flow

```
                 ┌─────────────┐
  Salesforce ───▶│             │
  Google Sheet ─▶│ SupportPlan │──▶ TargetingEngine ──▶ OrderBuilder ──▶ Order
  YAML plan ────▶│             │      (config/tiers)     (templates)      │
                 └─────────────┘                                          │
                                                          ┌───────────────┼───────────────┐
                                                          ▼               ▼               ▼
                                                     FreeWheel          GAM         (dry-run JSON)
```

Everything funnels through one internal representation — `SupportPlan` in, `Order`
out — so the *source* of a plan (YAML, sheet, or Salesforce Case) and the *target*
of a push (FreeWheel, GAM) are pluggable without touching the core logic.

## Modules

| Module | Responsibility |
|---|---|
| `models.py` | Domain dataclasses. Pure data; JSON-serializable. |
| `config.py` | Loads `config/*.yaml`; reads credentials from env. |
| `plan_loader.py` | Normalizes any source into a `SupportPlan`. |
| `targeting.py` | **The engine.** Applies `config/tiers.yaml` to a plan → tiered targeting. Deterministic. |
| `audience_segments.py` | Tier-1 resolver: show title → FreeWheel audience segment. Never guesses IDs. |
| `order_builder.py` | Assembles `Order` + one `Placement` per format from templates. |
| `cli.py` | `build` / `preview` / `push` / `from-case` / `sync-segments`. |
| `integrations/` | FreeWheel, Salesforce, GAM, Operative, Google Sheets clients. |

## Why config-driven tiers

The Tier 1–4 structure and per-format tier selection live in `config/tiers.yaml`, not
in code. Ops can adjust the strategy (add a dimension, change which tiers a format
uses) by editing YAML, and every built order reflects the change — no code deploy.

## Credentials & safety

* No secrets in the repo. Every client reads env vars (`.env.example` lists them).
* Constructing an integration client without its credentials raises immediately.
* `push` defaults to **dry-run** (prints the payload it *would* send); `--live` is
  required to actually create.
* The audience resolver never fabricates a segment ID. Unmatched shows are reported
  so an operator can request/add them — a wrong ID could mis-target a live campaign.

## Confirming external API schemas

FreeWheel/Operative APIs are auth-gated, so exact endpoint paths and payload field
names are marked `# CONFIRM:` in the integration clients, and Salesforce/GAM field
mappings are marked `# MAP:`. These are the only places that need a live tenant to
finalize; the build/preview core is complete and tested.
