# FreeWheel create-placement / IO — exact structures

Source: **FreeWheel Publisher API docs** (public, readme.io) —
`https://api-docs.freewheel.tv/publisher/reference/create-a-placement`. The raw
OpenAPI spec per API is downloadable at
`https://api-docs.freewheel.tv/publisher/openapi/<apiSetting-id>` (Placement API V3
= `65dc08064433d6003d934347`). Server: `https://api.freewheel.tv`. V3 bodies are XML;
the Streaming Hub gateway accepts JSON objects and converts.

## Create Placement — `POST /services/v3/placement/create`

Confirmed request-body structure (the parts that matter for promo):

```
name, description, placement_type ("PROMO"), external_id, instruction
schedule:   { start_time, end_time, time_zone }
budget:     { budget_model, impression, impression_cap, currency, ongoing, ... }
delivery:   { priority: "GUARANTEED"|"PREEMPTIBLE",   # TYPE, not a number (validated live)
              pacing:   "SMOOTH_AS"|"FAST_AS"|...,     # required (validated live)
              frequency_cap: [ {value, type, period, advanced_fc_identity_level} ] }
ad_product: { ad_unit_node: [ {ad_unit_id:int64, price, budget_exempt, impression_cap, status} ],
              ad_unit_package_id: [int64], link_method, ... }
content_targeting.network_items.include.sets: [ { series:[int64], video:[int64],
              video_group:[int64], site:[int64], site_section:[int64] } ]
content_targeting.standard_attributes / ron / inventory_packages
audience_targeting.include: { audience_item:[int64], sets:[...], relation_between_sets:[AND|OR] }
geography_targeting.include: { country:[int64], state:[int64], dma:[int64], city:[int64],
              postal_code:[int64], region:[int64] }        # IDs, NOT names
platform_targeting, daypart_targeting, custom_targeting, ...
```

### Corrections vs. the first (empty-shell) attempt
- **geo**: must be `geography_targeting.include.country = [<country_id:int64>]` — I sent
  `region: ["USA"]` (string) → silently dropped.
- **priority**: TYPE `PREEMPTIBLE`/`GUARANTEED` (+ `pacing`), not the numeric 1–10.
- **ad units**: `ad_product.ad_unit_node[].ad_unit_id` — were missing entirely.
- **frequency caps**: set at the **IO level** (per the Ad Units doc), not per placement.
- **audience_targeting** / **content_targeting.series** structures were already correct;
  they failed on ID values (wrong series namespace) / the whole block dropping.

## Reference-ID resolution (the remaining work)

These are int64 IDs, and the list endpoints have **no name filter**, so each is a
sync-and-match (like audience items), sourced live or from the docs:

| Need | Source | Note |
|---|---|---|
| Country ID (US=165) | Standard Attributes `content_territories` | **SOLVED**: IDs match the UI Add-New-Country panel exactly. `sync_countries()` → `data/geo`. Team selects by name; tool resolves name→ID. See docs/REGIONS.md. |
| Ad unit IDs | `list-standard-and-custom-ad-units` (Ad Unit API v4) / `list-ad-unit-nodes` (V3) | no name filter → sync-and-match like countries |
| Pluto channels/categories | Site API v4 `list-site-groups` | **SOLVED**: Pluto = Site Groups named `SG: PlutoTV Channels/Promo Category: …`. Write to `sets[].site_group`. `sync_site_groups()` → `data/site_groups`. Keyword select-all. |
| Series IDs | Video Series (UI) vs standard-attribute series | confirm which namespace `content_targeting.series` accepts via one verified create |
| Audience item IDs | `sync-audience-items` | working (GL-DDA-1P-SHOW_) |

**Note on geo lookups**: the Streaming Hub has no dedicated geography/country
reference endpoint (checked all 49 tool categories) and placement reads don't
return targeting, so the country table is sourced from the `content_territories`
standard-attribute type — confirmed to be the same namespace the geo UI uses.

Every other API's schema is downloadable the same way (advertiser, campaign, IO, geo,
ad units) — so the write path is now fully specifiable, not guesswork.
