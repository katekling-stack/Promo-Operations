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
