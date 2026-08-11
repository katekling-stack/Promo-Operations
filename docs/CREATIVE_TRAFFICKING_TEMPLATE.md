# Creative Trafficking template — near-term mockup

A governed, templatized alternative to ad hoc creative-delivery emails/sheets: one
consistent intake format for **any** case owner/creative team to submit creatives
against a Salesforce Case, instead of every team using slightly different fields.

Open [`templates/creative-trafficking/creative-trafficking-form.html`](../templates/creative-trafficking/creative-trafficking-form.html)
in any browser (no server, no login). Regenerate it after a config change with:

```bash
python scripts/build_creative_trafficking_form.py
```

## Where this came from

Modeled on the existing PTS ("Promo Trafficking Sheet") Excel workbook — six tabs,
one per product, each column tagged as filled by **Marketing** (the case
owner/creative team) or **Promo** (Ad Ops, after intake): **Video**, **Pause Ads**,
**Display**, **Audio**, **HPTO**, **Video Domination**. The field list and
ownership split per tab live in `TABS` in `scripts/build_creative_trafficking_form.py`
— that's the single source of truth; the form is generated from it.

Promo-owned fields (FreeWheel/GAM/Megaphone order links, exported creative name,
tracking pixel, etc.) render **read-only** in the intake form — they're filled in
after Promo Ops processes the line, not by the submitter — but stay in the JSON
schema (blank) so nothing downstream has to special-case a missing key.

## What's new vs. the original workbook

Every creative line gets a **Net New Creative** indicator:
`New` / `Reused – Prior Flight` / `Refresh of Existing`, plus an optional
**Prior Creative Reference** (prior Creative Name, Click-Through URL, or Case #)
that appears once the line isn't marked `New`. This is the ask that started this
template: when a case owner comes back for the next flight of an already-processed
title, Promo Ops can see at a glance which lines are genuinely new assets to
traffic vs. which can be re-pointed at what's already live.

**Campaign Name is free text, not a FreeWheel dropdown.** Submitting teams aren't
in FreeWheel and don't know its campaign naming — this field just mirrors
whatever the Salesforce Case calls the campaign.

**Brand is a separate dropdown**, and it *is* structured — sourced from the same
`brand_signature()` parser the plan form's cross-market mirroring uses
(`promo_ops.brand_sync`), collapsed to the ~18 region-independent brand families
(Paramount+, Pluto TV, Nickelodeon, CBS Sports, etc., each with a `- Kids` variant
where one exists) instead of the ~150 region-specific FreeWheel campaign names.
That's the identity a creative team actually recognizes, and it's what lets Promo
Ops map a Case back to the right FreeWheel brand even when the Case's free-text
Campaign Name doesn't match FreeWheel at all. Picking a Brand:
- shows a "typical formats for this brand" hint, derived from the union of
  products that brand family runs anywhere (`config/brands.yaml`) — informational
  only, it doesn't hide any of the six tabs, since which formats a given flight
  actually needs is still Promo's call;
- surfaces a Kids-safety note (COPPA / no personalized tracking) for Kids brands;
- stamps `brand` and `kids_audience` onto the downloaded JSON.

`FAMILY_LABEL` / `brands()` in `scripts/build_creative_trafficking_form.py` is
where to adjust the brand list or its labels.

## How this fits the Case (near-term)

This mirrors the pattern already built for **Targeting**: the Case carries core
scalar fields, and a structured file is attached and parsed off the Case
(`SalesforceClient._targeting_rows` in `src/promo_ops/integrations/salesforce.py`
downloads the attachment via `ContentDocumentLink` / `ContentVersion`, matched by a
title hint). The downloaded `*.creative.json` here is meant to become that same
kind of attachment — a `TRAFFICKING_FILE_HINT` and a small parser alongside
`_targeting_rows` would consume it the same way, once we're ready to wire it up.

## Longer-term option (not built yet)

Model each creative line as a child object (e.g. `Creative_Asset__c`) related to
the Case instead of a file attachment — one record per creative/placement. That's
what makes "required" actually enforceable (a validation rule/Flow blocking Case
submission until at least one Creative Asset record exists), and makes creatives
reportable/filterable by the Net New flag. Holding off on this until we get input
from the creative-automation team, per `SALESFORCE_IMPLEMENTATION_PLAN.md`'s staged
rollout approach.
