# Reference IO extractions (live FreeWheel reads)

> **Targeting lives in TWO places.** A placement can carry targeting under
> placement-level `content_targeting` OR under named `relationship_targeting.set[]`
> ("Relationships" in the UI). `show-a-placement` returns the latter only via
> `show=relationship_targeting` (no boolean flag). ALWAYS read both — reading only
> `content_targeting` makes relationship-targeted placements look empty. P+ Kids uses
> content_targeting; The Agency UK and Pluto En Español use relationship sets.
> `scripts/extract_reference_io.py` now reads both.


Captured with `scripts/extract_reference_io.py` (ACTIVE placements only). IDs here feed
the `config/brands.yaml` + `config/regions.yaml` entries. Ad-unit / site-group / video-
group IDs still need name resolution (sync tables) before finalizing.

## Recurring IDs (the building blocks)

**Ad units**
- `72000`, `72001` — base remnant units (in nearly every remnant placement)
- `71999` — added on short durations (10/15/20s)
- `69304` — appears on some UK / Kids remnant lines
- `61120` + `67610` — Premium Pre-Roll (guaranteed)
- `61123` — Bumper (Essential/Basic Plan) (guaranteed)

**Site groups**
- `932583` — Paramount+
- `929392` — Pluto TV
- `932400` — P+ Kids content SG
- `1109067`, `1120870` — Pluto Kids SGs (UK)
- `1107704,1107749,1107757,1107762,1107822,1107829,1107859,1107865,1200881,1204409,1214150,1224837,1235383` — UK Pluto channel list (Tier 2)

**Kids Video Groups — the Older/Younger split (CONFIRMED)**
- `86471529` — base, always included.
- `73408862` — **Older Kids**.
- `73408864` — **Younger Kids**.
- Default Kids campaigns target Older `[73408862, 86471529]`; add `73408864` for Younger
  (a campaign covering both uses all three). The global **Older/Younger Kids** plan
  option selects which age VG(s) are layered in.

**Regions**: USA = country `165`; UK = country `56`.

## Promo advertisers (from the Custom Adv Global Mapping) — region + audience

The promo advertiser = `VCBS - {Region} - {Adult|Kids} (Promo)`. Campaigns nested under
each are the brands. (`1219585` "…Adult (Promo) - Tests Only" is excluded.)

| Region | Adult advertiser | Kids advertiser |
|---|---|---|
| USA (English) | 1000520 | 1000521 |
| USA (Spanish) | 1000522 | 1000523 |
| United Kingdom | 1207836 | 1209288 |
| Canada (English) | 1207832 | 1209274 |
| Canada (French) | 1209272 | 1209273 |
| Australia | 1222262 | 1296461 |
| LATAM | 1207826 | 1207827 |
| Brazil | 1207828 | 1207830 |
| Ireland | 1371480 | 1371481 |
| GSA | 1207845 | 1209283 |
| Spain/Italy/France/Finland/Norway/Sweden/Denmark | (see mapping) | (see mapping) |

**Enumeration rules (per your guidance):** under a promo advertiser, keep only campaigns
that are ACTIVE, have **at least one active IO/placement**, and do **not** contain
"Bumper" or "test" in the name. `list-campaigns` has no advertiser filter and its rows
omit advertiser_id, so `scripts/extract_reference_io.py --advertiser <id> [--name <prefix>]`
name-searches then confirms each via `show-a-campaign` + an active-placement check.

## Domestic (USA)

### Paramount+ Kids — campaign 54440942, IO 93584432 (Valiente: A Tracker Story, movie)
- Bumper - Essential Plan (guaranteed, ALL_IMPRESSION): AU `61123`; CT = `SG 932583` AND (`VG [73408862,73408864,86471529]` + `SG 932400`)
- Pre-Roll - Premium Plan (guaranteed): AU `61120,67610`; same CT
- Remnant "Now Streaming - 30" (IMPRESSION_TARGET): AU `72000,72001`; no CT

### Pluto TV - En Español — campaign 54439023, IO 95298406 (Crímenes imperfectos)
- Remnant "Stream Ahora - 15": AU `72000,72001,71999`; no CT
- Remnant "Stream Ahora - 30": AU `72000,72001`; no CT
- Plain remnant, no relationship targeting.

### Pluto TV - En Español - Kids — campaign 62081253, IO 80290202 (El Reino Infantil)
- Remnant "Stream Ahora - 15": AU `71999,72000,72001`; no CT
- Remnant "Stream Ahora - 30": AU `72000,72001`; no CT

## UK (country 56)

### Paramount+ UK — campaign 73711557, IO 81277963 (The Agency, ShowID 943970057)
Re-read WITH relationship targeting — it's the **standard tiered model**, split P+/Pluto:
- **P+ lines** (main SG `[932583 P+, 932591 CBS Local, 932592 VCBS]`, NO Pluto, NO
  Tier 1): Tier 2 "Showlist" (main AND video+series), Tier 3 "Genre" (main AND genre
  VGs), Tier 4 (main RON). AU `[69304 INTL pre-roll, 71999 house pre-roll, 72000, 72001]`
  (house pre-roll drops at 30s; INTL stays).
- **Pluto lines** ("(Pluto)" infix, main SG `929392`): Tier 2 "Channels" (Pluto channel
  SGs), Tier 3 "Genre" (929392 AND genre VGs) + "Categories" (Pluto category SGs), Tier
  4 (929392 RON). AU `[71999,72000,72001]`.
- **Pause Ads** (AU `63413`): tiers 2/3/4 with main `[929392,932583,932592]` AND
  platform SGs `[929447 CTV, 929449 Desktop]` — same pattern as domestic pause.
- **Guaranteed**: Pre-Roll Premium `[61120,67610]` + Bumper **Basic Plan** `[61123]` —
  each Genre (932583 AND genre VGs) + Recommended Show (932583). Identical to domestic
  P+ guaranteed except the "Basic Plan" label.
- Genre VGs in the IO are the OLD region-specific set — use the **standard** genre
  resolver (per Kate).
- Note: the **P+/Pluto split** (separate line sets by inventory) is the current UK
  pattern (also seen in P+ Kids UK); domestic P+ combines them into one remnant.

### Pluto TV UK — campaign 72286125, IO 87074612 (MacGyver, "Stream Now")
Re-read WITH relationship targeting — it's a **Pluto-only 3-tier remnant** (no Tier 1):
- **Tier 2 "Channels"** (content_targeting): UK Pluto channel `SG [1107704,1107749,
  1107757,1107762,1107822,1107829,1107859,1107865,1200881,1204409,1214150,1224837,
  1235383]`
- **Tier 3** (relationship sets):
  - "Genres": `VG [74003220,74003231,74003269,74003454,75343512,75343611,99965267]` AND
    `SG 929392`
  - "Categories": `SG [1162830,1163098,1189781,1192163]`
- **Tier 4 "RON"** (content_targeting): `SG 929392` (Pluto)
- All lines: ad units `71999,72000,72001`; geo 56; IMPRESSION_TARGET.
- **Data dependency to build:** the Tier-3 genre Video Groups are **UK-specific**
  (74003220…) — the genre resolver's VG table is domestic, so UK genre VGs need syncing
  / a UK genre→VG mapping before this brand can resolve genres from a plan.

### Paramount+ Kids UK — campaign 75617429, IO 86215521 (Kamp Koral, ShowID 61457250)
- P+ lines "Streaming Now - 15/30 - Kids": CT = `SG 932583` AND (`VG [73408862,86471529]` + `SG 932400`); AU `69304,72000,72001(,71999)`
- Pluto lines "… (Pluto) - Kids": CT = (`VG [73408862,86471529]` + `SG 932400`) AND `SG [1109067,1120870]`; AU `72000,72001(,71999)`
- Bumper - Basic Plan / Pre-Roll - Premium Plan (guaranteed): kids CT as above

## Australia (country 10) — no Pluto

AU has **no Pluto** and **no Samsung** excludes. Standard genres/VGs everywhere.

### NOTE — Tier-1 audience segments use the DWH "Summit" convention
Every AU campaign resolves Tier 1 against the **`AU - DWH - <src> - ID - Summit - ...`**
audience segments — **not** the global `GL-DDA-1P-` DDA segments used everywhere else.
Region-scoped in the resolver: AU → Summit, all other regions → GL-DDA-1P (neither
leaks across). Deactivated segments (name contains "deactivated") are never targeted.

### Paramount+ AU — campaign `73850057` (`Paramount + - AU`)
- Tiered remnant on main `[932583 P+, 932591 CBS Local, 932592 VCBS]` (no Pluto).
  AU `[69304 INTL pre-roll, 71999 house pre-roll, 72000, 72001]`; house pre-roll drops
  at :30. Premium Pre-Roll + Basic Plan (UK-style "Basic", not "Essential") bumper.
- **Include Network 10** (opt-in): adds `(10 Streaming)` **tiered** remnant lines on
  main `[932591, 932592, 1238405 Ten Play]`, AU `[70313 Net10 Live pre-roll, house]`,
  `(10 Streaming)` after the tier. Sometimes ships **VG rating restrictions** — supplied
  per-case (`Rating_Restrictions__c` / "Rating Restrictions"), excluded on the 10
  Streaming sets only.

### Nick / Nick Jr AU (Kids) — campaigns `80947033` / `80947027`
- Flat Kids remnant (no tier stack): CT = (`VG kids` + `SG 932400 COPPA`) AND main SG.
  Standard line main = `932583 P+`, AU `[71999,72000,72001]` (drops pre-roll at :30).
  Kids remnant runs at **priority 1 (override −1) + cap 1 per 15 min** (not tier 4).
- **Include Network 10** (opt-in): adds `(10 Streaming)` Kids remnant on main
  `1238405 Ten Play`, AU `[70313, house]`, + a **10 Streaming After Mid-Roll Bumper**
  (guaranteed, HIGHEST, AU `70049 Net10_Brand_Bumper_Mid_Roll`).
- Naming: `{title} - {msg} - Kids - {dur}[ (10 Streaming)] - AU` (audience before dur).

### NOTE — (10 Streaming) Video Series come **underscored**
The Network 10 / 10 Streaming catalog names Video Series with underscores
(`masterchef_australia` = `1179587696`) alongside the standard spaced entries
(`MasterChef Australia` = `134200301`). Series matching folds `_` → space, so a single
showlist keyword resolves **both** spellings — this applies to the **Tier-2 showlist
include** *and* to self-exclusion, so every underscore + spaced variant is targeted /
excluded together.

## Open design questions

1. **Older vs Younger Kids** (global): which VG maps to which? (`73408864` present domestic, absent UK.)
2. **Naming variants** per brand/region: "Now Streaming" / "Stream Now" / "Streaming Now"
   / "Stream Ahora"; "Essential Plan" (US) vs "Basic Plan" (UK). Confirm the rule.
3. **Simple-remnant brands** (Pluto En Español): no targeting at all — model as a plain
   remnant format (no tier stack)?
4. Ad-unit / SG / VG **names** to confirm the IDs above.
