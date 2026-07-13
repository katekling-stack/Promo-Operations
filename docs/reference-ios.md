# Reference IO extractions (live FreeWheel reads)

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

**Kids Video Groups — the Older/Younger split**
- Domestic P+ Kids: `[73408862, 73408864, 86471529]`
- UK P+ Kids:      `[73408862, 86471529]`
- → `73408864` is the differentiator. The global **Older vs Younger Kids** option most
  likely toggles this VG. **CONFIRM:** which VG(s) = Older vs Younger.

**Regions**: USA = country `165`; UK = country `56`.

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
- Remnant tiers 2 & 3 "Season 2 - 30": AU `69304,72000,72001`; no CT
- Pre-Roll - Premium Plan (guaranteed): AU `61120,67610`; no CT
- Bumper - **Basic Plan** (guaranteed): AU `61123`; no CT   ← UK uses "Basic" not "Essential"

### Pluto TV UK — campaign 72286125, IO 87074612 (MacGyver, "Stream Now")
- Tier 2 (15s): CT = big UK Pluto channel `SG [1107704…1235383]`
- Tier 4 (10/15/20s): CT = `SG 929392` (Pluto)
- Tier 3: no CT
- All: AU `71999,72000,72001`

### Paramount+ Kids UK — campaign 75617429, IO 86215521 (Kamp Koral, ShowID 61457250)
- P+ lines "Streaming Now - 15/30 - Kids": CT = `SG 932583` AND (`VG [73408862,86471529]` + `SG 932400`); AU `69304,72000,72001(,71999)`
- Pluto lines "… (Pluto) - Kids": CT = (`VG [73408862,86471529]` + `SG 932400`) AND `SG [1109067,1120870]`; AU `72000,72001(,71999)`
- Bumper - Basic Plan / Pre-Roll - Premium Plan (guaranteed): kids CT as above

## Open design questions

1. **Older vs Younger Kids** (global): which VG maps to which? (`73408864` present domestic, absent UK.)
2. **Naming variants** per brand/region: "Now Streaming" / "Stream Now" / "Streaming Now"
   / "Stream Ahora"; "Essential Plan" (US) vs "Basic Plan" (UK). Confirm the rule.
3. **Simple-remnant brands** (Pluto En Español): no targeting at all — model as a plain
   remnant format (no tier stack)?
4. Ad-unit / SG / VG **names** to confirm the IDs above.
