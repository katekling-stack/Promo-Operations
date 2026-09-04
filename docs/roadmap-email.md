# Roadmap request email — draft

*Copy/paste and adjust the bracketed bits. Keep it short; attach the one-pager + calculator.*

---

**Subject:** Roadmap ask: host our promo order-building tool (built + tested) — ~60% faster, ~75% fewer errors

Hi [Name],

I'd like to get one item onto the engineering roadmap. The short version: **the hard part is already built and running against FreeWheel production — we just need it hosted so the whole promo team can use it.**

**What it is.** A tool that turns a campaign plan into fully-built FreeWheel orders — the tiered targeting, ad units, geo, flight timing, and every exclusion rule applied automatically, across 15 regions and ~79 brands. It creates review-ready drafts a coordinator activates; it never books on its own. It's covered by ~389 automated tests.

**Why it matters.** Today we traffic campaigns by hand — dozens of settings per order, built from institutional knowledge and scattered reference docs. The tool makes that a reviewed draft in seconds and validates orders *before* they hit FreeWheel. Our estimates:

- **~60% less time** to generate and build an order
- **~75% lower error rate** — fewer live mis-targeting incidents, make-goods, and re-trafficking
- **Data-grounded targeting** — the Suggested Targeting feature proposes comp shows, channels, and genres from our *real* inventory and what similar past campaigns actually ran, instead of manual guesswork (a big help for new titles and onboarding)

*(There's a quick ROI calculator attached — drop in our real order volume and it sizes the hours/$ saved.)*

**The ask is small and well-scoped.** It's an operational lift, not a new build:
1. Host the tool + Suggested Targeting helper as a shared internal service (one small VM, behind VPN)
2. Enable Suggested Targeting — historicals-only to start (no external dependencies), optional AI layer later behind one server-side key
3. Own the daily data-refresh job (already scripted)

I've attached a one-pager and a fuller handoff doc with the technical details, sizing, and security posture. Could we find a slot to scope this? Happy to walk through it whenever works.

Thanks,
[Your name]

---

*Attach: `roadmap-onepager.pdf`, `roi-calculator.html`, `ENGINEERING_HANDOFF.md`.*
