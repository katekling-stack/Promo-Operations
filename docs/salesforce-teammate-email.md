# Message to send your teammate (email or Slack)

Copy-paste and tweak. Two versions — a short Slack ping and a fuller email.

---

## Short version (Slack / quick email)

> Hey [name] — ahead of our chat on the Salesforce integration, here's the gist:
>
> The tool that builds our FreeWheel orders is done and running (15 regions, 153
> campaigns). The only thing left is letting a planner kick it off from a Salesforce
> Case instead of by hand. Salesforce is **just the intake form** — no logic lives
> there.
>
> Shortest path to live:
> **7 Case fields → 3 picklist values → a sandbox/integration user → one test Case.**
>
> I've attached the exact field list (import-ready CSV) and a one-page build sheet.
> Once the fields exist, a preflight command tells us green/red in one shot. Want to
> start with just USA to prove it, then open up the rest?

---

## Fuller version (email)

**Subject:** Salesforce → FreeWheel automation — what we need to build

Hi [name],

Thanks for making time to talk through this. Quick framing so we can move fast:

**What's already done:** the tool that builds FreeWheel Insertion Orders + all the
placements (tiering, naming, ad units, geo, exclusions, products) is built, tested, and
running against production for 15 regions / 153 campaigns. It can also duplicate a title
across markets in one step.

**What we need Salesforce to do:** act as the **intake form only**. A planner fills a
Case and flags it "Ready for Automation"; the tool reads it, builds the order as a draft
in FreeWheel, and posts the draft link back on the Case. No ad-ops logic in Salesforce —
it just captures ~7 fields cleanly and holds a status flag.

**The ask (attached):**
- `salesforce-case-fields.csv` — the exact fields to create (API names, types, picklist
  values), generated from our live config so it's complete and current.
- `SALESFORCE_ADMIN_ASKS.md` — a one-page build sheet (fields + 3 picklist values +
  access).
- `SALESFORCE_FIELD_MAPPING.md` (PDF) — the full write-up with the minimal-vs-full field
  breakdown and a few open questions for us to decide together.

**Shortest path to a working demo:** the 7 required fields, 3 Status/Reason picklist
values, and a sandbox + integration user (or Connected App). Once those exist, I run a
one-line preflight (`salesforce-check`) that reports exactly what's present/missing —
green means we can process a real Case end-to-end.

**Suggestion:** pilot with one region (USA) to prove the loop, then expand to all 15.

A couple of things I'd love your read on: whether targeting lists should live on an
attached sheet vs. more Case fields, how you'd prefer to keep the campaign picklist
updated, and whether a Status value is the right trigger (vs. a checkbox/record type).
All in the mapping doc.

Thanks!
[you]

---

**Attachments to include:** `salesforce-case-fields.csv`, `SALESFORCE_ADMIN_ASKS.md`,
`Salesforce-Field-Mapping.pdf` (and `Salesforce-Implementation-Plan.pdf` if you want the
full sequence).
