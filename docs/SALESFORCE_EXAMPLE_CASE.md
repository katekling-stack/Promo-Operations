# Example Case — "Frisco King - USA"

A concrete instance of the proposal, so the rep can see exactly what a planner fills
and what the automation derives. This is the real kickoff campaign (Frisco King, P+
Domestic) mapped onto the proposed Case fields.

> The same Case shape drives all 15 regions / ~80 brands — an international or Kids
> campaign just fills a different Campaign Name (and, where relevant, Language, Kids
> Audience, or the Include-* product toggles). The full field list is in
> `salesforce-case-fields.csv`.

## What the planner fills (native Case fields)

| Section | Field | API Name | Value |
|---|---|---|---|
| Campaign | Promoted Title | `Promoted_Title__c` | Frisco King |
| Campaign | Region | `Region__c` | USA |
| Campaign | Campaign Name | `Campaign_Name__c` | Paramount + - USA |
| Creative | Season or Messaging | `Season_or_Messaging__c` | Season 1 |
| Creative | Content Type | `Content_Type__c` | show |
| Creative | Content ID | `Content_ID__c` | *(blank — CM adds ShowID)* |
| Creative | Recommended Show ID | `Recommended_Show_ID__c` | *(blank — CM adds in UI)* |
| Flighting | Flight Start | `Flight_Start__c` | 2026-10-01 |
| Flighting | Flight End | `Flight_End__c` | 2026-12-31 |
| Flighting | Flight Code | `Flight_Code__c` | L1 |
| Flighting | Video Durations | `Video_Durations__c` | 30;15 |
| Products | Video Domination | `Video_Domination__c` | *(blank)* |
| Products | Takeover | `Takeover__c` | *(blank)* |

Plus **Status = "Ready for Automation"** when the planner is done.

## What the automation derives (Override fields — left blank on the Case)

The planner leaves these blank; the automation fills them from the Campaign. Shown here
so you can see the full resolved picture:

| Field | API Name | Derived value | Derived from |
|---|---|---|---|
| Brand | `Brand__c` | paramount_plus_domestic | Campaign Name |
| Advertiser | `Advertiser__c` | VCBS English - USA - Adult (Promo) | Brand |
| Advertiser ID | `Advertiser_ID__c` | 1000520 | Brand |
| Campaign ID | `Campaign_ID__c` | 86543608 | Campaign Name |
| Insertion Order Name | `Insertion_Order_Name__c` | Frisco King - USA | `{Title} - {Region}` |
| Recommended Show | `Recommended_Show__c` | Frisco King | Promoted Title |
| Exclude Show | `Exclude_Show__c` | Frisco King | Promoted Title |
| Formats | `Formats__c` | remnant_video; pause_ads; premium_preroll; essential_bumper | Brand's format set |

## The attached Targeting sheet

One file attached to the Case (title contains "Targeting"), one list per column:

| Networks | Genres | Showlist (22) | Pluto Categories | Pluto Channels (34) |
|---|---|---|---|---|
| Paramount Network | Drama | Tulsa King | True Crime | Paramount+ Picks |
| | Comedy | Landman | Drama | Paramount Movie Channel |
| | Crime | Mayor of Kingstown | History & Science | Westerns |
| | Western | Dutton Ranch | Movies - Action | Rawhide |
| | War | Marshals | Entertainment - General | PBR |
| | Sports | Mobland | Reality - Adventure | Gunsmoke |
| | Action & Adventure | The Madison | Sports | … (34 total) |
| | News | Tracker | | |
| | | … (22 total) | | |

*(Tier-1 Audience Segments column left blank — DDA segments auto-resolve from the
Showlist; sunset AAM segments are never used.)*

## What the automation produces

A **draft** FreeWheel Insertion Order "Frisco King - USA" under Campaign 86543608, with
placements for each format × tier × duration (remnant video Tiers 1–4, pause ads,
guaranteed Premium Pre-Roll + Essential Bumper). A Case comment posts the draft IO link
and any CM to-dos (e.g. "add the recommended_show value"), and **Reason** is set to
"Submitted to FreeWheel." The draft is reviewed and activated by a person in FreeWheel.
