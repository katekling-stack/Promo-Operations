# Adding a Brand / Region — the playbook

How we add a new brand or region. Every brand so far was reverse-engineered from a real
reference IO, so that's the input: **one reference Insertion Order** that represents how
the team already traffics that brand/region. From it we fill a `config/brands.yaml`
entry and any region/site-group specifics.

## What I need from you to start one

For each new brand (or a brand in a new region), the reference IO URL, plus:

1. **Reference IO URL** (e.g. `…/campaigns/<id>/?insertion_order_id=<io>`) — the model
   we mirror.
2. **Parent campaign name + id** the IOs nest under (e.g. "CBS Sports - CA").
3. **Advertiser** name + id.
4. **Region** — if it's a new region (CA/AU/UK/LATAM/BR), the countries it targets
   (names as the team searches them, e.g. "Canada").
5. Anything brand-specific you already know: which **ad units** (the sponsored/bumper
   set), any **site groups** that are always included/excluded, brand **Video Groups**
   for genre, and any platform differences (e.g. no P+, or Pluto-only).

If you paste the reference IO URL, I can pull most of 2–5 straight from FreeWheel.

## What I extract from the reference IO

Using the FreeWheel read tools (`show-a-placement` with expand flags), per the Dutton
Ranch method:

- **Ad units** on the sponsored/bumper placements → `config/ad_units.yaml` group +
  `format_ad_unit_group` mapping.
- **Geography** (countries) → region entry in `config/regions.yaml`.
- **Main site groups** always AND-ed in (platform/biz-div) → brand `main_site_groups`.
- **Include/exclude** site groups + video groups → brand `include_video_groups`,
  `extra_exclude_site_groups`, `extra_exclude_video_groups`.
- **Formats** run for the brand → brand `formats`.
- Priorities, freq caps, pacing, override precedence → confirmed against the tier config.

## Where it lands in config

A brand is one entry under `brands:` in `config/brands.yaml`:

```yaml
<brand_key>:
  display_name: "…"
  advertiser_name_contains: ["VCBS", "…"]
  template_campaign_id: "<id>"        # parent campaign (also drives brand-from-campaign)
  template_io_id: "<id>"              # the reference IO we mirror
  campaign_name: "… - <REGION>"       # exact parent campaign name (dropdown value)
  formats: [remnant_video, pause_ads, …]
  ad_unit_groups: { <format>: <group> }
  main_site_groups: [ … ]             # platform SGs AND-ed into every tier
  include_video_groups: [ … ]         # brand content VGs for genre
  extra_exclude_site_groups: [ … ]
  extra_exclude_video_groups: [ … ]
```

A new **region** is one entry under `regions:` in `config/regions.yaml` (country names +
resolved ids). Country ids resolve via the synced country table (`data/geo`).

## How we verify a new brand

1. Add the config entry (+ region if new).
2. Write a throwaway plan (or a test Case) for a show on that brand.
3. `promo-ops preview <plan.yaml>` — eyeball tiers, ad units, geo, excludes.
4. `promo-ops push <plan.yaml> --target freewheel --live` into the **test network**
   (520310), then read the draft back and diff against the reference IO.
5. Add a `tests/test_brands.py` case asserting the brand's placements/ad-units.
6. Delete the test draft.

## Status of brands today

All current brands are **USA**:

| Brand key | Campaign | Notes |
|---|---|---|
| paramount_plus_domestic | Paramount + - USA | kickoff (Frisco King) |
| cbs_sports | CBS Sports - USA | |
| cbs_news | CBS News - USA | excludes Pluto News SGs |
| cbs_network | CBS Network - USA | + preroll/bumper/1z/2z lockdowns |
| mtve | MTVE - USA | main SGs: PlutoTV/VCBS/CBS Local (no P+) |
| bet | BET Media Group - USA | main SG 1072587; brand VG |
| pluto_tv | Pluto TV - USA | excludes Samsung SGs |
| pluto_tv_xco | Pluto TV (Cross-Company) - USA | |

**Next up:** non-USA regions (CA/AU/UK/LATAM/BR) and any additional brands (e.g. Nick),
each driven by a reference IO.
