# Promo Operations Automation — The Case for the Roadmap

*Why engineering should prioritize hosting + the Suggested Targeting tool.*
*Prepared by: Kate Kling, Digital Promo Ad Operations.*

---

## The one-line ask

We've **already built** the automation that turns a campaign plan into fully-built,
rule-complete FreeWheel orders. We need engineering to put the **last mile on the roadmap** —
**host it as a shared service** and **enable the Suggested Targeting tool** — so the whole team
gets the productivity and accuracy gains, not just whoever runs it locally.

---

## The problem today

Promo campaigns are trafficked **by hand**. For every campaign a coordinator manually builds
**dozens of placements** across tiers, durations, formats, regions, and platforms — each with
precise targeting, ad units, geo, flight timing, and exclusion rules. To do it they rely on
**institutional knowledge, common sense, and a scatter of reference docs, spreadsheets, and
past IOs.** That approach is:

- **Slow** — significant hands-on setup per order, repeated for every campaign.
- **Error-prone** — dozens of manual settings per order is dozens of chances to mis-key a site
  group, miss an exclusion, or apply the wrong rating VG. Mistakes surface *after* a campaign
  is live.
- **Inconsistent** — output depends on who built it and what they remembered that day.
- **Hard to scale / onboard** — the rules live in people's heads, not in a system.

Targeting specifically is built on **judgment plus manual lookups** — there's no single,
data-grounded source for "what should this campaign actually run against."

---

## What we've already built (de-risks the ask)

This isn't a green-field project — the hard part is **done and validated**:

- **Live against FreeWheel production**, feature-complete for building.
- **15 regions / ~79 brands**, each reverse-engineered from its live IOs.
- Encodes the tiered-targeting strategy, ad units, geo, flight timing, content-rating
  targeting, dayparting, and every exclusion rule **once**, deterministically.
- **389 automated tests** guard the behavior.
- A **self-service intake form** and a **Suggested Targeting** helper already exist; they just
  need to be hosted for the team.

The remaining work is **operational, not inventive**: stand it up on a shared host and turn on
the helper. Small, well-scoped, low-risk.

---

## The impact (why it's worth a roadmap slot)

### 1. ~75% lower error rate — from pre-built, rule-complete output
Orders are generated from **encoded rules and pre-set targeting** instead of dozens of manual
entries. The settings that people mis-key today — site groups, ad units, exclusions, rating
VGs, flight dates — are applied consistently every time and **validated before push** (the tool
blocks malformed orders rather than letting them reach FreeWheel). Fewer errors means fewer
**live-campaign incidents, make-goods, and re-trafficking cycles** — the expensive kind of
mistake.

### 2. ~60% faster to generate and build an order
What is significant manual setup today becomes a **reviewed draft in seconds**. Coordinators
shift from *building* placements to *reviewing* them — the same output, a fraction of the time,
freeing capacity for higher-value work and letting the team absorb more volume without adding
headcount.

### 3. Accuracy & consistency, by construction
Every order follows the **same rule set**, mirrored from how the live reference IOs are actually
configured. Output no longer varies by who built it. It's also **auditable** — the build is
deterministic and reviewable before anything goes live (the tool never books on its own; a
human activates every draft).

### 4. Smarter targeting — real data instead of guesswork
Today targeting is assembled from **common sense and scattered resources**. The **Suggested
Targeting tool** replaces that with a **data-grounded recommendation**: given a title, it
proposes comp shows, Pluto channels, genres, and categories — matched to our **real FreeWheel
inventory** and to **what similar past campaigns in that region actually ran**, ranked by
agreement across sources. It's especially valuable for **new titles with no history** and for
**onboarding** — it encodes the team's best practice so every coordinator builds like the most
experienced one.

---

## Illustrative annual value

*The two headline figures are ops estimates; the rest is simple arithmetic on top. Replace the
bracketed baselines with our real numbers to finalize.*

| Lever | Assumption (edit) | Result |
|---|---|---|
| Orders built / year | **[N]** orders | — |
| Time per order, manual | **[T] min** | — |
| **Build time −60%** | → **[0.4 × T] min** per order | **~[0.6 × T × N ÷ 60] hours saved / yr** |
| **Error rate −75%** | from **[E]%** → **[0.25 × E]%** | fewer make-goods, re-traffics, live incidents |
| Onboarding | ramp a new coordinator faster | targeting best-practice encoded, not taught ad hoc |

> Example only: at 1,000 orders/yr and 45 min each, a 60% cut saves **~450 hours/year** — before
> counting the error-rate savings, which avoid the costliest failures (live mis-targeting).

---

## Why now

- The build is **finished and production-validated** — the ROI is sitting behind a small
  hosting task.
- Today the tool runs **laptop-by-laptop**; only whoever set it up benefits. Hosting unlocks
  the gains **for the whole 5-person team at once.**
- The Suggested Targeting tool can start in a **zero-external-dependency mode** (grounded only
  in our own historical data) — immediate value, no approval blockers.

## The specific roadmap items

1. **Host the tool + Suggested Targeting helper** as a shared internal service (1 small VM,
   behind VPN). *See `docs/ENGINEERING_HANDOFF.md`.*
2. **Enable Suggested Targeting** — historicals-only first; optional AI layer later behind one
   server-side key.
3. **Own the daily data-refresh job** (already scripted) so dropdowns/suggestions stay current.

**Bottom line:** the heavy lifting is done and tested. A small, well-scoped hosting effort
converts it into a **~60% faster, ~75% more accurate** order-building workflow for the entire
team — with data-grounded targeting replacing manual guesswork.
