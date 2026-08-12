# FreeWheel ad units — reference

Every standard + custom ad unit available on network 520311, exported live
from the Ad Unit API v4 (`sync_ad_units`). Use this to pick which units a
format should assign, then add the NAMES to `config/ad_units.yaml` — the tool
resolves names → FW IDs automatically.

Total: **197** units (184 ACTIVE). Full machine-readable
list: `data/ad_units/seed_ad_units.csv`.

## Currently mapped (domestic remnant + pause)

| Ad unit | FW ID | Used by |
|---|---|---|
| Paramount House Preroll | 71999 | remnant_video (P+/Local/VCBS/Pluto) |
| Paramount House Midroll | 72000 | remnant_video (P+/Local/VCBS/Pluto) |
| Paramount House Postroll | 72001 | remnant_video (P+/Local/VCBS/Pluto) |
| Viacom_Promo_Pre_Roll | 61113 | MTVE/BET/VH1 |
| Paramount House Preroll | 71999 | MTVE/BET/VH1 |
| Paramount House Midroll | 72000 | MTVE/BET/VH1 |
| Paramount House Postroll | 72001 | MTVE/BET/VH1 |
| Viacom_NickJR_Promo_Pre_Roll | 61121 | Nick (kids) |
| ViacomCBS_Kids_Promo_Mid_Roll | 61157 | Nick (kids) |
| ViacomCBS_Kids_Promo_Pre_Roll | 61156 | Nick (kids) |
| Paramount House Preroll | 71999 | Nick (kids) |
| Paramount House Midroll | 72000 | Nick (kids) |
| Paramount House Postroll | 72001 | Nick (kids) |
| Pause_Ad | 63413 | pause_ads |

## Duration-based rules (applied automatically by the engine)

These are enforced on every push — CMs don't set them on the form; they follow from the
selected durations. Verified against live IOs.

**House Pre-Roll is a short-creative unit.** It runs on **:20 / :15 / :10 and below** and is
**dropped at :30 and above** (which then run **House Mid-Roll + Post-Roll only**). Applies
across the board — **tiered, standard, and kids**. Controlled by
`default_drop_preroll_at_duration: 30` in `config/ad_units.yaml` (a template may pin its own).

| Creative length | House units on the line |
|---|---|
| :20, :15, :10 (and shorter) | Pre-Roll + Mid-Roll + Post-Roll |
| :30 and above | Mid-Roll + Post-Roll (no Pre-Roll) |

**Brand-specific pre-rolls are NOT duration-gated** — only the *House* Pre-Roll drops. These
ride on every duration per their brand config:
- `Viacom_Promo_Pre_Roll` — MTVE / BET (kept on all durations, incl. :30+).
- `Pplus_INTL_Promo_Pre_Roll` — **all P+ INTL markets: UK, IE, LATAM, AU, BR, and FR / GSA / IT**
  (kept on all durations; the House Pre-Roll beside it still drops at :30+).
- `CBS_Promo_Pre_Roll`, `Net10_Live_ Pre_Roll`, `Viacom_NickJR_Promo_Pre_Roll` — per their brands.

**Brands corrected to the House-Pre-Roll-on-short rule:** Pluto TV - USA and
CBS News - USA / - Spanish - USA previously ran Mid+Post only (no pre-roll on any length);
they now carry the House Pre-Roll on short creatives like every other House-unit brand.

## Priority rule — Pluto TV Tier 4 by duration

Pluto TV - {Region} campaigns run **Tier 4 hotter** for the main creative lengths:
**:15 and :30-and-above → priority 8** (override `-8`); shorter creatives
(**:5 / :6 / :10 / :20 → priority 10**, override `-10`). **Non-Pluto brands keep the flat
Tier 4 = 10.** Config: `pluto_tier4_priority` in `config/priorities.yaml`.

## Sponsored / bumper units (candidates for Premium Pre-Roll & Essential Bumper)

These GUARANTEED formats aren't mapped yet — tell me which of these they use
(or add to config) and I'll wire them in.

| Ad unit | FW ID | Status |
|---|---|---|
| CBS_Brand Bumper_Mid_Roll_First | 61119 | ACTIVE |
| CBS_Brand Bumper_Mid_Roll_Last | 61123 | ACTIVE |
| CBS_Brand Bumper_Pre_Roll | 61107 | ACTIVE |
| CTA_Midroll_Bumper_Back | 61890 | IN_ACTIVE |
| CTA_Midroll_Bumper_Front | 61888 | IN_ACTIVE |
| My5_Channel_Bumper_Mid_Roll | 74745 | ACTIVE |
| My5_Channel_Bumper_Post_Roll | 74746 | ACTIVE |
| My5_Channel_Bumper_Pre_Roll | 69988 | ACTIVE |
| My5_Channel_Sponsor_Mid_Roll | 69901 | ACTIVE |
| My5_Channel_Sponsor_Post_Roll | 74747 | ACTIVE |
| My5_Channel_Sponsor_Pre_Roll | 69900 | ACTIVE |
| My5_Sponsor_Mid_Roll | 69903 | ACTIVE |
| My5_Sponsor_Mid_Roll_First | 71402 | ACTIVE |
| My5_Sponsor_Mid_Roll_Last | 71403 | ACTIVE |
| My5_Sponsor_Post_Roll | 69904 | ACTIVE |
| My5_Sponsor_Pre_Roll | 69898 | ACTIVE |
| Net10_Brand_Bumper_Mid_Roll | 70049 | ACTIVE |
| Net10_Sponsored_ Pre_Roll | 70147 | ACTIVE |
| PPlus_PPlus on Amazon Bumper_Mid_Roll | 61122 | ACTIVE |
| PPlus_PPluss on Amazon Bumper_Pre_Roll | 61108 | ACTIVE |
| PPlus_Show Brand Bumper_PreRoll | 64877 | ACTIVE |
| PPlus_Sponsored_Mid_Roll | 68257 | ACTIVE |
| PPlus_Sponsored_Pre_Roll | 65125 | ACTIVE |
| Pplus_Sponsored_Pre_roll_Live | 77209 | ACTIVE |
| PPlus_Stay Tuned_Bumper_Pre_Roll | 63623 | ACTIVE |
| PPlus_Walmart_Brand Bumper_PreRoll | 67875 | ACTIVE |
| Viacom_Content_Bumper | 61104 | ACTIVE |
| ViacomCBS_BrandBumper_Pre_Roll | 61646 | IN_ACTIVE |
| ViacomCBS_Sponsor Billboard_Pre_Roll | 61103 | ACTIVE |
| ViacomCBS_Sponsored Billboard_Mid_Roll | 61109 | ACTIVE |

## All units (A–Z)

<details><summary>Expand full list of 197 ad units</summary>

| Ad unit | FW ID | Status |
|---|---|---|
| 150x30 | 65854 | ACTIVE |
| 160x600 | 61115 | ACTIVE |
| 234x60 | 63415 | ACTIVE |
| 300x250 | 61117 | ACTIVE |
| 320x50 | 68385 | ACTIVE |
| 728x90 | 61116 | ACTIVE |
| 970x66 | 68384 | ACTIVE |
| Any_Mid_Roll_Position_2 | 61798 | ACTIVE |
| BETPlus_Commercial Free_Promo | 67755 | ACTIVE |
| BETPlus_LinearSkippable_Promo_Pre_Roll | 67754 | ACTIVE |
| CBS_Brand Bumper_Mid_Roll_First | 61119 | ACTIVE |
| CBS_Brand Bumper_Mid_Roll_Last | 61123 | ACTIVE |
| CBS_Brand Bumper_Pre_Roll | 61107 | ACTIVE |
| CBS_Promo_Pre_Roll | 66704 | ACTIVE |
| CBSNews_Audio | 62469 | IN_ACTIVE |
| CTA_Midroll_Bumper_Back | 61890 | IN_ACTIVE |
| CTA_Midroll_Bumper_Front | 61888 | IN_ACTIVE |
| DNU_mid_roll | 74703 | IN_ACTIVE |
| DNU_post_roll | 74704 | IN_ACTIVE |
| DNU_pre_roll | 74702 | IN_ACTIVE |
| fixed_mid1_posA | 73680 | ACTIVE |
| fixed_mid1_posB | 73681 | ACTIVE |
| fixed_mid1_posC | 73682 | ACTIVE |
| fixed_mid1_posD | 73683 | ACTIVE |
| fixed_mid1_posE | 73684 | ACTIVE |
| fixed_mid1_posF | 73685 | ACTIVE |
| fixed_mid2_posA | 73767 | ACTIVE |
| fixed_mid2_posB | 73768 | ACTIVE |
| fixed_mid2_posC | 73769 | ACTIVE |
| fixed_mid2_posD | 73770 | ACTIVE |
| fixed_mid2_posE | 73771 | ACTIVE |
| fixed_mid2_posF | 73772 | ACTIVE |
| fixed_mid3_posA | 73773 | ACTIVE |
| fixed_mid3_posB | 73774 | ACTIVE |
| fixed_mid3_posC | 73775 | ACTIVE |
| fixed_mid3_posD | 73776 | ACTIVE |
| fixed_mid3_posE | 73777 | ACTIVE |
| fixed_mid3_posF | 73778 | ACTIVE |
| fixed_mid4_posA | 73779 | ACTIVE |
| fixed_mid4_posB | 73780 | ACTIVE |
| fixed_mid4_posC | 73781 | ACTIVE |
| fixed_mid4_posD | 73782 | ACTIVE |
| fixed_mid4_posE | 73783 | ACTIVE |
| fixed_mid4_posF | 73784 | ACTIVE |
| fixed_mid5_posA | 73785 | ACTIVE |
| fixed_mid5_posB | 73786 | ACTIVE |
| fixed_mid5_posC | 73787 | ACTIVE |
| fixed_mid5_posD | 73788 | ACTIVE |
| fixed_mid5_posE | 73789 | ACTIVE |
| fixed_mid5_posF | 73790 | ACTIVE |
| fixed_mid6_posA | 76643 | ACTIVE |
| fixed_mid6_posB | 76644 | ACTIVE |
| fixed_mid6_posC | 76645 | ACTIVE |
| fixed_mid7_posA | 76660 | ACTIVE |
| Halo_Mid_Roll_1 | 68252 | ACTIVE |
| Halo_Mid_Roll_2 | 68253 | ACTIVE |
| Halo_Mid_Roll_3 | 68254 | ACTIVE |
| Halo_Mid_Roll_4 | 68255 | ACTIVE |
| hyldadoublebox | 74569 | ACTIVE |
| hyldalbar | 74570 | ACTIVE |
| hyldamidroll | 74527 | ACTIVE |
| Live Feed Disclaimer | 61748 | ACTIVE |
| Local_mid_roll | 74700 | ACTIVE |
| Local_post_roll | 74699 | ACTIVE |
| Local_pre_roll | 74701 | ACTIVE |
| Mid_Roll | 61101 | ACTIVE |
| Mid_Roll_Break 10_First | 61144 | ACTIVE |
| Mid_Roll_Break 10_Last | 61145 | ACTIVE |
| Mid_Roll_Break 11_First | 61146 | ACTIVE |
| Mid_Roll_Break 11_Last | 61147 | ACTIVE |
| Mid_Roll_Break 12_First | 61148 | ACTIVE |
| Mid_Roll_Break 12_Last | 61149 | ACTIVE |
| Mid_Roll_Break 13_First | 61150 | ACTIVE |
| Mid_Roll_Break 13_Last | 61151 | ACTIVE |
| Mid_Roll_Break 14_First | 61152 | ACTIVE |
| Mid_Roll_Break 14_Last | 61153 | ACTIVE |
| Mid_Roll_Break 15_First | 61154 | ACTIVE |
| Mid_Roll_Break 15_Last | 61155 | ACTIVE |
| Mid_Roll_Break 1_First | 61126 | ACTIVE |
| Mid_Roll_Break 1_Last | 61127 | ACTIVE |
| Mid_Roll_Break 1_Second | 62335 | ACTIVE |
| Mid_Roll_Break 2_First | 61128 | ACTIVE |
| Mid_Roll_Break 2_Last | 61129 | ACTIVE |
| Mid_Roll_Break 3_First | 61130 | ACTIVE |
| Mid_Roll_Break 3_Last | 61131 | ACTIVE |
| Mid_Roll_Break 4_First | 61132 | ACTIVE |
| Mid_Roll_Break 4_Last | 61133 | ACTIVE |
| Mid_Roll_Break 5_First | 61134 | ACTIVE |
| Mid_Roll_Break 5_Last | 61135 | ACTIVE |
| Mid_Roll_Break 6_First | 61136 | ACTIVE |
| Mid_Roll_Break 6_Last | 61137 | ACTIVE |
| Mid_Roll_Break 7_First | 61138 | ACTIVE |
| Mid_Roll_Break 7_Last | 61139 | ACTIVE |
| Mid_Roll_Break 8_First | 61140 | ACTIVE |
| Mid_Roll_Break 8_Last | 61141 | ACTIVE |
| Mid_Roll_Break 9_First | 61142 | ACTIVE |
| Mid_Roll_Break 9_Last | 61143 | ACTIVE |
| Mid_Roll_Break _1_Any | 72373 | ACTIVE |
| Mid_Roll_Break_Any_First | 61609 | ACTIVE |
| Mid_Roll_Break_Any_Last | 61610 | ACTIVE |
| Mid_Roll_Middle | 63258 | ACTIVE |
| My5_Channel_Bumper_Mid_Roll | 74745 | ACTIVE |
| My5_Channel_Bumper_Post_Roll | 74746 | ACTIVE |
| My5_Channel_Bumper_Pre_Roll | 69988 | ACTIVE |
| My5_Channel_Sponsor_Mid_Roll | 69901 | ACTIVE |
| My5_Channel_Sponsor_Post_Roll | 74747 | ACTIVE |
| My5_Channel_Sponsor_Pre_Roll | 69900 | ACTIVE |
| My5_Promo_Mid_Roll | 69902 | ACTIVE |
| My5_Promo_Post_Roll | 69905 | ACTIVE |
| My5_Promo_Pre_Roll | 69899 | ACTIVE |
| My5_Sponsor_Mid_Roll | 69903 | ACTIVE |
| My5_Sponsor_Mid_Roll_First | 71402 | ACTIVE |
| My5_Sponsor_Mid_Roll_Last | 71403 | ACTIVE |
| My5_Sponsor_Post_Roll | 69904 | ACTIVE |
| My5_Sponsor_Pre_Roll | 69898 | ACTIVE |
| Net10_Brand_Bumper_Mid_Roll | 70049 | ACTIVE |
| Net10_Live_ Pre_Roll | 70313 | ACTIVE |
| Net10_Sponsored_ Pre_Roll | 70147 | ACTIVE |
| Paramount House Midroll ✅ mapped | 72000 | ACTIVE |
| Paramount House Postroll ✅ mapped | 72001 | ACTIVE |
| Paramount House Preroll ✅ mapped | 71999 | ACTIVE |
| Pause_Ad ✅ mapped | 63413 | ACTIVE |
| PGATour Scene Setter | 61737 | ACTIVE |
| Pluto_House_Mid_Roll | 61111 | ACTIVE |
| Pluto_House_Mid_Roll_Clickable | 65541 | ACTIVE |
| Pluto_House_Post_Roll | 61112 | IN_ACTIVE |
| Pluto_House_Pre_Roll | 61110 | IN_ACTIVE |
| Pluto_intl_mid_roll | 67393 | ACTIVE |
| Pluto_Mid-Roll_Billboard_A | 61796 | ACTIVE |
| Pluto_Mid-Roll_Billboard_B | 61797 | ACTIVE |
| Pluto_Mid-Roll_Billboard_C | 69318 | ACTIVE |
| Pluto_Nordic_Midroll_First | 74623 | ACTIVE |
| Pluto_Pre-Roll_Billboard | 67510 | ACTIVE |
| Pluto_Pre_Roll | 68691 | ACTIVE |
| Pluto_Pre_Roll_Billboard_A | 68696 | ACTIVE |
| Pluto_Pre_Roll_Billboard_B | 68697 | ACTIVE |
| Post_Roll | 61102 | ACTIVE |
| PPlus_Commercial Free_Mid-Roll_Promo | 64765 | ACTIVE |
| PPlus_Commercial Free_Promo | 61120 | ACTIVE |
| PPlus_Commercial Free_Promo_TestAdUnit_No-UX_Cap | 62753 | ACTIVE |
| Pplus_INTL_Promo_Pre_Roll | 69304 | ACTIVE |
| PPlus_LinearSkippable | 62391 | ACTIVE |
| PPlus_LinearSkippable_Midroll | 65907 | ACTIVE |
| PPlus_LinearSkippable_Promo_Pre_Roll_1s | 67610 | ACTIVE |
| PPlus_Movie Promo_Pre_Roll | 64766 | ACTIVE |
| PPlus_Next On_Mid_Roll | 64096 | ACTIVE |
| PPlus_Next_on | 61636 | IN_ACTIVE |
| PPlus_PPlus on Amazon Bumper_Mid_Roll | 61122 | ACTIVE |
| PPlus_PPluss on Amazon Bumper_Pre_Roll | 61108 | ACTIVE |
| PPlus_PPluss_12-curtain-raiser | 61613 | ACTIVE |
| PPlus_Previously on_Pre_Roll | 64231 | ACTIVE |
| PPlus_Samsung_Pre_Roll_Test | 64504 | ACTIVE |
| PPlus_Show Brand Bumper_PreRoll | 64877 | ACTIVE |
| Pplus_Show_Disclaimer_Pre_Roll | 65318 | ACTIVE |
| Pplus_showtime_promos | 63840 | ACTIVE |
| PPlus_Sponsored_Mid_Roll | 68257 | ACTIVE |
| PPlus_Sponsored_Pre_Roll | 65125 | ACTIVE |
| Pplus_Sponsored_Pre_roll_Live | 77209 | ACTIVE |
| PPlus_Stay Tuned_Bumper_Pre_Roll | 63623 | ACTIVE |
| Pplus_TV_Rating | 61889 | ACTIVE |
| Pplus_Walmart Plus_Pre_Roll | 65250 | ACTIVE |
| PPlus_Walmart_Brand Bumper_PreRoll | 67875 | ACTIVE |
| Pre_Roll | 61100 | ACTIVE |
| Pre_Roll_Break_First | 71718 | ACTIVE |
| Pre_Roll_Break_Last | 71719 | ACTIVE |
| Promo_Mid_Roll | 71728 | IN_ACTIVE |
| Promo_Pre_Roll | 71727 | IN_ACTIVE |
| Promo_Skippable_Pre_Roll | 65889 | ACTIVE |
| Promo_Skippable_Pre_Roll_1skipoffset | 67033 | ACTIVE |
| SFU Placeholder | 74571 | ACTIVE |
| Standard Display | 60651 | ACTIVE |
| Standard Mids | 60648 | ACTIVE |
| Standard Overlay | 60650 | ACTIVE |
| Standard Pause | 60652 | ACTIVE |
| Standard Post | 60649 | ACTIVE |
| Standard Pre | 60647 | ACTIVE |
| Super Bowl 58 | 66688 | ACTIVE |
| Super Bowl 58 Interactive Companion | 67185 | ACTIVE |
| Trial_Sub_Mid_Roll_1 | 68307 | ACTIVE |
| Trial_Sub_Mid_Roll_3 | 68308 | ACTIVE |
| TrueX_Mid_Roll | 61106 | ACTIVE |
| TrueX_Pre_Roll | 61105 | ACTIVE |
| UFC BrightLine Companion | 75655 | ACTIVE |
| UFC MIdroll | 74112 | IN_ACTIVE |
| US_Preroll_Live | 73308 | ACTIVE |
| Viacom_Content_Bumper | 61104 | ACTIVE |
| Viacom_LinearSkippable | 63672 | ACTIVE |
| Viacom_Movie Promo_Pre_Roll | 72136 | ACTIVE |
| Viacom_NickJR_Promo_Pre_Roll ✅ mapped | 61121 | ACTIVE |
| Viacom_Promo_Mid_Roll | 61118 | ACTIVE |
| Viacom_Promo_Pre_Roll ✅ mapped | 61113 | ACTIVE |
| ViacomCBS_BrandBumper_Pre_Roll | 61646 | IN_ACTIVE |
| ViacomCBS_Kids_Promo_Mid_Roll ✅ mapped | 61157 | ACTIVE |
| ViacomCBS_Kids_Promo_Pre_Roll ✅ mapped | 61156 | ACTIVE |
| ViacomCBS_Sponsor Billboard_Pre_Roll | 61103 | ACTIVE |
| ViacomCBS_Sponsored Billboard_Mid_Roll | 61109 | ACTIVE |
| Video Overlay | 61114 | ACTIVE |

</details>
