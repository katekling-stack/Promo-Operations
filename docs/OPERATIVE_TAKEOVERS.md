# Operative Takeovers → GAM (runbook)

Covers HPTO, First Impression (FITO), Arena Takeover, 3-Peat, and Internal
Marketing. Products + booking rules are encoded in `config/operative_takeovers.yaml`;
this is the manual runbook the automation will mirror.

## Book in Operative (Sales module)
1. **Sales** tab → left filters → **Order** → search the order type (HPTO, Arena
   Takeover, FITO, 3-Peat, or Internal Marketing e.g. MLS/NBA/MLB) → Enter.
2. Open a **similar** existing order (matching products + sites).
3. **Copy Sales Order** → new order name + date(s) + start date.
   - Naming: `Show Name - HPTO/FITO/Arena Takeover Date(s)`
   - Paramount+: prefix `P+ ` → `P+ HPTO - Show Name - P+ HPTO/FITO/Arena Takeover Date(s)`
     (helps VideoAmp reporting).
4. Products: select under **Add Group**, or copy an existing order that has them
   (full list in the config `types`).
5. New product (not copied): Media Plan → **Bulk Operations** → Select All Line
   Items → Custom Fields → **+ IO Package Name = "Internal Takeover"** → Review &
   Confirm → Save.
6. Update dates + quantities:
   - **HPTO / Sponsorship**: quantity = **1**, unit cost = **0**, all *Unit Price
     Before Discounts* = **$0**.
   - Confirm all booked products match the Network Working Report. Save.
7. **Get Approvals**: Submit for Internal Approval **twice**, then manually Approve
   (Status dropdown → Approved) → Save.
   - Any later edit requires re-approval before you can Acknowledge & Push.

## Push to GAM (Ad Operations module)
8. Find the order → **Assign to yourself** → open it.
9. **Bulk Operations** → set push quantity:
   - **Sponsorship** (HPTO/FITO/Arena): Select All → Bulk Edit → Standard Fields →
     **Push Quantity = 100**.
   - **Standard** (MLS/NBA/MLB, 3-Peat): Select All → Bulk Edit → Standard Fields →
     **increase push quantity by 3%** → Production System Fields → **Same Advertiser
     Exception = Yes**.
10. **Push to Ad Server** → Push All → Advertiser = **"CBS Interactive"** → Push to
    Ad Server.

## Automation notes
The above is UI-driven in Operative. Automating it means, via the Operative API
(capabilities to CONFIRM): copy order → set dates/quantities/unit cost → set IO
Package Name → submit + approve → set push quantities → push to GAM. That is the
Operative → GAM execution layer (shared with the 3 Operative Video Dominations).

## Live push status

Operative bookings are a **UI workflow** (copy order → approve → Push All to GAM), not
an API the automation drives — so the tool produces a **booking worksheet** the CM
executes, rather than pushing live. GAM has an API: `GoogleAdManagerClient` +
`promo-ops gam-check` (connectivity preflight) are ready to wire **if/when GAM API
access + a service account are granted**; until then the worksheet is the path.

## Booking worksheet (`promo-ops booking-sheet <plan>`)

Prints a step-by-step, checkbox worksheet for a campaign's Video Domination + takeover:
which Operative order to copy, the generated order name, the exact product lines, the
per-line quantities/push rules, the approval steps, and the GAM push advertiser
("CBS Interactive"). `render_booking_worksheet()` mirrors the runbook steps above, so a
CM can execute it top to bottom.

## Building add-ons from a plan (`promo-ops addons`)

`promo-ops addons <plan>` emits the Video Domination + Takeover specs for a campaign
(from the plan's `video_domination` / `takeover` fields), built by
`src/promo_ops/addons.py`:

- **Pluto VD** (`video_domination: pluto`) → a ready FreeWheel create-placement body
  (guaranteed HIGHEST, House Pre/Mid units, 1/day+1/stream+1/asset caps, a "Categories"
  set of the plan's Pluto category SGs — region-aware). Push it with
  `promo-ops addons <plan> --live` (creates a NOT_BOOKED IO + the VD placement under
  the plan's campaign). Verified against the live "… - Pluto Video Domination - …" IO.
- **Operative VDs** (`standard` / `aus_10_streaming` / `uk_my5`) and **Takeovers**
  (`hpto` / `first_impression` / `arena_takeover` / `three_peat`) → a **booking spec**:
  which Operative order to copy, the new order name (per the naming patterns), the exact
  product lines, the push quantities/rules, and the GAM push advertiser. Execute it in
  Operative per the runbook below (no API drives that step).

