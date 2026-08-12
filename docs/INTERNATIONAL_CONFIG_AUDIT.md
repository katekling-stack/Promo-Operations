# International Config — Validation Status (pre-8/18 rollout)

Result of validating the USA-cloned brand families against real setups (live FreeWheel
lookups + per-family rules). **All families are now validated or fixed.**

## ✅ Validated / fixed

| Family | Status |
|---|---|
| **Paramount+** (all regions) | ✅ Already per-region correct (P+ + Pluto + Premium/Basic Plans as available per region; AU/IE = P+ only where no Pluto) |
| **Pluto TV** (all regions) | ✅ Already per-region correct (Pluto-only platform, House ad units) |
| **Pictures** | ✅ Already per-region variants |
| **Kids** — Nick / Nick Jr / Consumer Products (Kids-net **and** Adult-net variants) | ✅ Verified: Set 1 (Nick `73408862` + Nick Jr `73408864` + Kids COPPA VG `86471529` + Kids COPPA SG `932400`) **AND** Set 2 = SG Platform PlutoTV `929392`; Older → exclude Nick Jr, Younger → exclude Nick. Advertiser separation via campaign name (Adult vs Kids net). |
| **P+ Kids** | ✅ Pluto + P+ + Premium/Basic Plans per region (kept as-is per direction) |
| **MTVE** (international) | ✅ **Fixed** — now mirrors Pluto internationally: MTVE content VG `73408899` on Pluto `929392`, House ad units (dropped Viacom pre-roll + VCBS/CBS-Local SGs). MTVE-USA unchanged. Rec-show removed (P+/Pluto only); After-Mid-Roll domestic-only; CBS-Entertainment excludes USA-only. |

## 🗑️ Removed
- **CBS News** international (AU/ES/GSA/LATAM/UK) — not real promo campaigns.

## Region nuances (intentional, not bugs)
- **AU & IE** have no Pluto TV (`has_pluto=False`), so kids/promos there target **P+** platform, not Pluto.

## Ad-unit + priority updates (2026-08-12)
- **House Pre-Roll duration gating (all brands):** House Pre-Roll runs on :20/:15/:10-and-below
  and drops at :30+ (Mid+Post only) — tiered, standard, and kids. See `docs/AD_UNITS.md`.
- **P+ INTL pre-roll extended:** `Pplus_INTL_Promo_Pre_Roll` added to **FR, GSA, IT** on short
  creatives (kept at :30+), matching UK/IE/LATAM/AU/BR.
- **No-pre-roll brands corrected:** Pluto TV - USA and CBS News - USA / - Spanish - USA now
  carry the House Pre-Roll on short creatives (were Mid+Post only).
- **Pluto Tier 4 by duration:** :15 and :30+ → priority 8; :5/:6/:10/:20 → 10. Non-Pluto flat 10.

## Notes
- Live reads confirmed the kids VG/SG IDs; the `.env` used was deleted. **Rotate the shared FreeWheel password** since it passed through chat.
