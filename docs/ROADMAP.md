# Roadmap — what's live vs. pending

This is a **starting point**. The deterministic core is done and tested; the
external-system integrations are scaffolded and need a live tenant to finalize.

## ✅ Live now (no credentials needed)

- Support-plan model + YAML loader.
- Tiered targeting engine driven by `config/tiers.yaml` (Slide 5 of the strategy deck).
- Tier 1 region gating (USA/AU/CA/LATAM/BR).
- Audience-segment resolver with the P+ groupings + Pluto seed data.
- Order + Placement builder from brand/region/placement templates.
- `promo-ops build` / `preview` — full Frisco King - USA order in dry-run.
- Test suite (9 tests).

## 🟡 Scaffolded — needs credentials / confirmation

| Item | What's needed |
|---|---|
| **FreeWheel push** | Auth is username/password (API user `AdOps.api@<network_id>`; test net = 520310). Confirm token endpoint + Order/Placement/targeting paths against the reference (marked `# CONFIRM:` in `integrations/freewheel.py`). Then `promo-ops push --target freewheel --live`. **Blocker:** the Claude-on-web session's network policy denies outbound to `*.freewheel.tv` / `shmcp.freewheel.com`, so the API can't be reached or schema-confirmed from here. Unblock by either (a) allowlisting FreeWheel domains in the environment's network policy, (b) running the client from a network with FreeWheel access, or (c) exporting the reference docs so the schema can be finalized offline. |
| **VCBS advertiser discovery** | Run `find_advertisers()` against the live API to confirm the advertisers-list endpoint and resolve real advertiser IDs. |
| **Template cloning** | Confirm how FreeWheel exposes "clone from campaign/IO" so brand `template_campaign_id` becomes a real clone. |
| **Salesforce Case → plan** | Map the real Case field API names in `integrations/salesforce.py` `CASE_FIELD_MAP`. Then `promo-ops from-case <CASE_ID>`. |
| **GAM push** | Create/confirm custom-targeting key IDs in the GAM network and map them in `integrations/gam.py` (marked `# MAP:`). Confirm advertiser (company) IDs. |
| **Operative** | Confirm Operative One order/line endpoints for the Operative-originated push. |
| **Audience segment sync** | Run `promo-ops sync-segments` with a Drive service account to pull all tabs of the Audience Segments sheet; extend `TAB_COLUMN_MAP` in `integrations/gsheets.py` for each tab layout (esp. the USA video tab that holds the Frisco King showlist segments). |

## 🔜 Next decisions for the team

1. **Google Sheet template layout** — finalize the columns for the interim
   plan-input sheet (`read_plan_template` in `gsheets.py`), since we're starting
   there before Salesforce-driven input.
2. **Brand coverage** — build out `config/brands.yaml` templates for each brand
   beyond Paramount Network (P+, Pluto, CBS) using their real VCBS advertisers and
   reference campaigns.
3. **Format coverage** — confirm tier mapping for Display / Podcast / HPTO and any
   guaranteed formats (Video Domination, Pre-Roll Lockdown).
4. **Additional regions** — extend `config/regions.yaml` and audience-segment tabs
   for CA, LATAM, BR, and the "TBD" markets.
