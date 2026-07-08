# FreeWheel — confirmed against the live API

Validated read-only against the **Streaming Hub** (`shmcp.freewheel.com`) on the
**production** network (520311) using the `AdOps.api@520311` account. No writes were
made.

## Write validation (test network 520310)

End-to-end write path validated read/create/delete, no residue:
- create Insertion Order (`sh_1_1_create-an-insertion-order`, body = JSON object) →
  created `NOT_BOOKED` (draft). ✓
- create Placement (`sh_1_0_create-a-placement`, body = JSON object, `placement_type`
  `PROMO`). ✓
- delete Insertion Order (`sh_1_1_delete-an-insertion-order`) → **cascades** to its
  placements (both 404 after). ✓ Use IO-delete for cleanup; the direct placement
  DELETE errors "json is not supported" via the gateway.

Test network has no VCBS/promo data (load-test env), so the real Frisco King create
(with the actual advertiser 1000520 / campaign 86543608 / series / segments) is a
production (520311) action, created as a draft for review.

## Access model

`shmcp.freewheel.com` is FreeWheel's **Streaming Hub MCP server** (309 tools). It is
reached over MCP JSON-RPC at `POST /mcp` with an OAuth 2.1 (PKCE) bearer token.

Login flow (fully scriptable — no browser, no custom connector needed):
1. `POST /oauth/register` (public client, PKCE) → `client_id`
2. `GET /oauth/authorize?...&code_challenge=...` → redirects to a login page whose
   URL carries `csrf_token`
3. `POST /oauth/login` with `username`, `password`, `environment`
   (`production`|`staging`), `csrf_token` → 302 to `redirect_uri?code=...`
4. `POST /oauth/token` (code + `code_verifier`) → JWT `access_token`
5. `POST /mcp` with `Authorization: Bearer <jwt>`; call `initialize`, then
   `tools/call` → `invoke_tool` with `{tool_name, parameters}`

Responses are V3 (XML rendered as JSON with `@`-prefixed attributes) wrapped as
`{"ok":true,"data":{...}}`. List payloads look like
`data.<plural>.<singular> = [ ... ]` with `@current_page` / `@total_entries`.

Tool names are **not uniformly** `sh_1_1_*` — several are `sh_1_0_*` (e.g. placements).
Resolve names via the `search_tools` meta-tool rather than hard-coding; the client
does this.

## Confirmed object hierarchy & IDs (USA adult promo)

```
Advertiser  VCBS English - USA - Adult (Promo)      id 1000520
  Campaign  Paramount + - USA                        id 86543608   ← matches kickoff URL
    IO      Dutton Ranch - USA (reference/template)   id 92725144  brand_id 346378
      Placements (per TIER):
        Dutton Ranch - Summer Sale - 15 (Tier 1) - USA
        Dutton Ranch - Summer Sale - 15 (Tier 2) - USA
        ... (30 placements across beat × duration × tier)
```

Note: there are **two** active campaigns named "Paramount + - USA" (54026435 and
86543608). **86543608** is the correct one — it matches the kickoff reference URL.

Full VCBS advertiser set exists per market (Sweden, Finland, Norway, Canada EN,
Brazil, GSA, France, Italy, LATAM, UK, + Kids variants, + Spanish-USA 1000522) —
the basis for multi-region templating.

## Key structural finding: placements are per-Tier

In the live data, **each tier is its own placement**, named:

```
{title} - {beat} - {duration} (Tier N) - {region}
```

e.g. `Dutton Ranch - Summer Sale - 15 (Tier 1) - USA`. `placement_type = PROMO`.
This differs from the tool's current model (one placement per format with tiers
nested). See ROADMAP — the builder's placement granularity is the open design item.

## Confirmed field schemas

**Insertion Order** (`get-a-insertion-order` / create under
`POST /services/v3/campaign/{campaign_id}/insertion_order`):
`campaign_id, name, description, client_po, brand_id, external_id,
primary_sales_person, primary_trafficker, stage (BOOKED), schedule{start_time,
end_time, time_zone}, currency (USD), budget`.

**Placement** (`show-a-placement` returns only name/type/status; the full targeting
lives in the **create body** `POST /services/v3/placement/create`). Confirmed body
sections and how our tier dimensions map onto them:

| Placement body field | Sub-shape | Fed by |
|---|---|---|
| `delivery.priority` | string/number | tier × duration priority (see scheme below) |
| `delivery.frequency_cap` | `[{value, type, period}]` | per-tier cap (T1-3 1/30min, T4 1/hr) |
| `schedule` | `{start_time, end_time, time_zone}` | flight |
| `audience_targeting.include.audience_item` | `[int64]` | **Tier 1** audience segment IDs (from the Audience Segments doc) |
| `custom_targeting.{set,match}` | key/value | Tier 1 recommended_show (Periscope key value) |
| `content_targeting.{network_items, standard_attributes, ron, inventory_packages}` | | Tier 2 showlist / Pluto channels; Tier 3 network/genre/category; Tier 4 RON |
| `geography_targeting.{include, exclude}` | | Tier 3 geo (region) |
| `platform_targeting.{device, os, ...}` | | endpoints (Desktop/Mobile/CTV) |
| exclusions | content/audience exclude | promoted show (label) — every placement |

### Show / content resolution (confirmed live)

| Input | Resolves via | Notes |
|---|---|---|
| Genre / Network | `GET /services/v4/standard_attributes` (types `genres`, `brands`) | name → id; genres 8/8, Paramount Network → brand 680 |
| Tier 2 showlist | `GET /services/v4/standard_attributes/series?name=` | pick the `(ViacomCBS Production)` entry; exact-name match, else flag. 20/22 Frisco King shows auto-resolve; Marshals + NCIS: New York need a manual pick |
| Tier 1 audience segments | Audience Items, convention `GL-DDA-1P-SHOW_<Show>` | `GET /services/v4/audience_items` has no name filter → `sync-audience-items` pulls all (~6k) and matches locally; Tulsa King = 1437993 |
| Pluto channels / categories | naming convention (no lookup) | `SG: PlutoTV Channels/Promo Category: …` |
| Geo | `geography_targeting` (region codes) | |

`liststandardseries` name search works (unlike `list-series`, which has no filter and
229k rows). Resolvers cache to `data/series/`, `data/standard_attributes/`,
`data/audience_segments/`; refresh with `sync-attributes` / `sync-audience-items`.
All resolvers surface unmatched/ambiguous inputs — never guess.

## Priority + frequency-cap scheme (Tiered – Domestic, US)

Confirmed from the Promo Settings Reference "Tiered – Domestic" tab. Priority is a
number = tier base + duration offset:

| Tier | :30–:90 | :15 | :20/:10 | Freq cap |
|---|---|---|---|---|
| 1 | 1 | 2 | 3 | 1 per 30 min |
| 2 | 4 | 5 | 6 | 1 per 30 min |
| 3 | 7 | 8 | 9 | 1 per 30 min |
| 4 | 10 | 10 | 10 | 1 per hr |

Guaranteed (Premium Pre-Roll / Essential Bumper) = **SPONSORSHIP** priority
(Premium cap 1/day, Essential cap 1 per 2 hrs). Encoded in `config/priorities.yaml`.

## Verified endpoints / tool names

| Purpose | Tool name | Method / path |
|---|---|---|
| List advertisers (name filter) | `sh_1_1_list-advertisers` | GET /services/v3/advertisers |
| List campaigns (name filter) | `sh_1_1_list-campaigns` | GET /services/v3/campaigns |
| List IOs of a campaign | `sh_1_1_list-insertion-orders-of-a-campaign` | GET /services/v3/campaign/{id}/insertion_orders |
| Get IO | `sh_1_1_get-a-insertion-order` | GET /services/v3/insertion_order/{id} |
| Create IO | `sh_1_1_create-an-insertion-order` | POST /services/v3/campaign/{campaign_id}/insertion_order |
| List IO placements | `sh_1_1_list-insertion-order-placements` | GET /services/v3/insertion_order/{id}/placements |
| Show placement | `sh_1_0_show-a-placement` | GET /services/v3/placement/{id} |
| Create placement | `sh_1_0_create-a-placement` | POST /services/v3/placement/create |

`list-campaigns` / `list-advertisers` accept `name` (prefix match, **case
sensitive**), `page`, `per_page` (max 50).
