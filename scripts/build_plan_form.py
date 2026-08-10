"""Generate an interactive, self-contained HTML campaign-plan FORM.

A modern alternative to the Excel workbook: open `campaign-plan-form.html` in any
browser (no server, no login), fill it out with real dropdowns + smart show/hide, and
click "Download plan file" to get a JSON the tool consumes directly:

    promo-ops build   <downloaded>.plan.json
    promo-ops preview <downloaded>.plan.json
    promo-ops push    <downloaded>.plan.json --target freewheel --live

The option lists (regions, campaigns, brands, products, VD/takeovers) are baked in from
the live config, so the form can't drift. Run:  python scripts/build_plan_form.py
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config"
OUT = REPO / "templates" / "campaign-plan" / "campaign-plan-form.html"

# Where the form's "Download & post to Slack" button sends the Campaign Manager. This is a
# name-based deep link; if it doesn't land on the exact channel, replace it with the
# channel's "Copy link" URL from Slack (right-click the channel -> Copy link), then
# regenerate the form. (Interim intake — retires when the Salesforce integration lands.)
SLACK_SUBMIT_URL = "https://paramountglobal.enterprise.slack.com/archives/C0BNBKZDV6W"

# Where "Request a new audience segment" links (a Google Apps Script form). Shown next to
# the Audience Segments field so a CM can request a not-yet-created segment at the same time.
AUDIENCE_REQUEST_URL = "https://script.google.com/a/macros/paramount.com/s/AKfycbxknwofz4GTldgrDuXbg3G7Z_ijmz5TIvZPIl8rkHyfjhGMOT-CENRxSO5xFrsbiUOr/exec"

# Where "Create a Brand in FreeWheel" links (a Google Form). Shown in the Products card so a
# CM can request the advertiser's Brand be created — needed to map it to the IO + Placement
# level under Custom Exclusivity — if it doesn't exist yet.
BRAND_REQUEST_URL = "https://docs.google.com/forms/d/e/1FAIpQLScWpfaBYYQah5tJjbxm0iSkE46m1bRqRjW5eCXj5S0iEe6TbA/viewform"

REGION_ORDER = ["USA", "CA", "UK", "IE", "AU", "LATAM", "BR", "FR", "IT", "GSA",
                "FI", "DK", "NO", "SE", "ES"]
REGION_NAME = {"USA": "United States", "CA": "Canada", "UK": "United Kingdom",
               "IE": "Ireland", "AU": "Australia", "LATAM": "LATAM", "BR": "Brazil",
               "FR": "France", "IT": "Italy", "GSA": "Germany / Switzerland / Austria",
               "FI": "Finland", "DK": "Denmark", "NO": "Norway", "SE": "Sweden",
               "ES": "Spain"}

PRODUCT_LABEL = {
    "remnant_video": "Remnant Video", "pause_ads": "Pause Ads",
    "premium_preroll": "Premium Pre-Roll", "essential_bumper": "Essential / Basic Bumper",
    "cbs_preroll": "CBS Pre-Roll", "after_midroll_bumper": "After Mid-Roll Bumper",
    "cbs_1z_lockdown": "1Z Lockdown", "cbs_2z_lockdown": "2Z Lockdown",
    "pluto_breakout": "Include Pluto (UK P+)", "network_10": "Network 10 (10 Streaming)",
}
GENRES = ["Action", "Action & Adventure", "Adventure", "Animation", "Anime", "Comedy",
          "Crime", "Documentary", "Drama", "Family", "Fantasy", "Horror", "Kids",
          "Music", "Mystery", "News", "Reality", "Romance", "Sci-Fi", "Sports",
          "Thriller", "War", "Western"]
CATEGORIES = ["ClassicTV", "Comedy", "Crime", "Daytime TV", "Drama", "Entertainment",
              "Game Shows", "Gaming Anime", "History Factual", "Holiday",
              "Home Lifestyle Food Culture", "Horror", "Kids", "Movies", "Music",
              "News", "Paranormal", "Reality", "Sci-Fi", "Sports", "Westerns"]


def _yaml(name):
    return yaml.safe_load((CONFIG / name).read_text()) or {}


def _region_of(cname: str) -> str:
    for code in REGION_ORDER:
        if cname.endswith(f"- {code}") or cname.endswith(code):
            return code
    return "?"


def app_data() -> dict:
    from promo_ops.models import PRODUCT_FAMILIES
    brands = _yaml("brands.yaml").get("brands", {})
    campaigns = []
    for key, b in brands.items():
        cname = b.get("campaign_name")
        if not cname:
            continue
        available = (set(b.get("formats") or []) | set(b.get("optional_formats") or [])
                     | {"pause_ads"})
        prods = [fam for fam, members in PRODUCT_FAMILIES.items()
                 if set(members) & available and fam in PRODUCT_LABEL]
        # After Mid-Roll Bumper is Domestic (US) only — never offer it in other markets,
        # even if a brand config still lists the member format.
        if _region_of(cname) != "USA":
            prods = [f for f in prods if f != "after_midroll_bumper"]
        # A product is ON by default when any of its members is in the brand's required
        # `formats` set (vs. only in optional_formats). Drives the form's Yes/No preset so
        # the CM sees the real default and can flip it — no silent "included by default".
        default_on = set(b.get("formats") or [])
        prod_default = {fam: bool(set(PRODUCT_FAMILIES.get(fam, [fam])) & default_on) for fam in prods}
        from promo_ops import brand_sync
        sig = brand_sync.brand_signature(cname)
        campaigns.append({"name": cname, "region": _region_of(cname),
                          "brand": b.get("display_name", key), "kids": bool(b.get("kids")),
                          "products": prods, "product_defaults": prod_default,
                          # brand identity for cross-market mirroring (family|kids)
                          "sig": f"{sig[0]}|{int(sig[1])}" if sig else None})
    campaigns.sort(key=lambda c: (REGION_ORDER.index(c["region"]) if c["region"] in REGION_ORDER else 99, c["name"]))
    vd = [{"key": k, "label": v.get("label", k)}
          for k, v in _yaml("video_dominations.yaml").get("options", {}).items()]
    tk = [{"key": k, "label": v.get("label", k)}
          for k, v in _yaml("operative_takeovers.yaml").get("types", {}).items()]
    from promo_ops.batch import SHEET_COLUMNS
    return {
        # Where the "Download & post to Slack" button opens. Swap for the channel's exact
        # "Copy link" URL from Slack (right-click the channel -> Copy link) if this
        # name-based deep link doesn't land on the right channel.
        "slackSubmitUrl": SLACK_SUBMIT_URL,
        "regions": [{"code": c, "name": REGION_NAME.get(c, c)} for c in REGION_ORDER],
        "campaigns": campaigns, "productLabels": PRODUCT_LABEL,
        "videoDominations": vd, "takeovers": tk,
        # Canonical batch-Sheet column order (single source of truth in promo_ops.batch),
        # so the "Copy row for Sheet" button emits cells in the Sheet's column order.
        "sheetColumns": SHEET_COLUMNS,
        # Canonical targeting options for type-to-search (generated from FreeWheel).
        **_targeting_options(),
    }


def _targeting_options() -> dict:
    """Real FreeWheel option lists for the form's type-to-search pickers, from the
    same generator that feeds templates/targeting-options/."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_targeting_options", REPO / "scripts" / "build_targeting_options.py")
    bto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bto)
    pluto = bto._pluto()
    active = {r: m for r, m in bto.REGION_TO_PLUTO_MARKETS.items() if r in bto._pluto_regions()}
    cats = {r: sorted({c for m in ms for c in pluto.get(m, {}).get("categories", [])})
            for r, ms in active.items()}
    chans = {r: sorted({c for m in ms for c in pluto.get(m, {}).get("channels", [])})
             for r, ms in active.items()}
    return {
        "genres": [v for v, _ in bto.genres()],
        "categoriesByRegion": cats,
        "channelsByRegion": chans,
        "audienceSegments": [n for n, _ in bto.audience_segments()],
        "shows": [n for _, n in bto.shows()],
    }


def build(out: Path | None = None) -> Path:
    html = TEMPLATE.replace("/*APP_DATA*/", json.dumps(app_data(), ensure_ascii=False))
    html = html.replace("AUDIENCE_REQUEST_URL_PLACEHOLDER", AUDIENCE_REQUEST_URL)
    html = html.replace("BRAND_REQUEST_URL_PLACEHOLDER", BRAND_REQUEST_URL)
    out = out or OUT
    out.write_text(html, encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paramount Promo — Campaign Plan</title>
<style>
:root{--navy:#0B3D91;--blue:#1F6FEB;--bg:#eef2f9;--card:#fff;--ink:#1a2540;--muted:#6b7690;
 --line:#e2e8f4;--ok:#1a9d63;--no:#d0453b;--chip:#e8eefb;--focus:rgba(31,111,235,.25);}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#e9eef8,#eef2f9);color:var(--ink);
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:760px;margin:0 auto;padding:0 18px 200px}
header{position:sticky;top:0;z-index:20;background:var(--navy);color:#fff;
 padding:16px 18px;box-shadow:0 4px 18px rgba(11,61,145,.28)}
.hwrap{max-width:760px;margin:0 auto;display:flex;align-items:center;gap:14px}
header h1{font-size:18px;margin:0;font-weight:700;letter-spacing:.2px}
header p{margin:2px 0 0;font-size:12.5px;opacity:.85}
.spacer{flex:1}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;
 padding:20px 22px;margin:18px 0;box-shadow:0 6px 22px rgba(20,40,90,.06)}
.card h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--blue);
 margin:0 0 4px}
.card .sub{color:var(--muted);font-size:12.5px;margin:0 0 16px}
.field{margin:14px 0}
.field label{display:block;font-weight:600;font-size:13.5px;margin:0 0 6px}
.field label .req{color:var(--no);margin-left:3px}
.hint{color:var(--muted);font-size:12px;margin-top:5px}
.note{background:#eef4ff;border:1px solid #cfe0ff;border-left:3px solid var(--blue);
 color:#1a2540;border-radius:8px;padding:9px 12px;font-size:12.5px;margin:2px 0 12px}
.note code{background:#dbe6ff}
input[type=text],input[type=date],select,textarea{width:100%;padding:11px 13px;font-size:15px;
 border:1.5px solid var(--line);border-radius:11px;background:#fff;color:var(--ink);
 transition:border-color .15s, box-shadow .15s;appearance:none}
select{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%236b7690' stroke-width='2.5'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
 background-repeat:no-repeat;background-position:right 13px center;padding-right:38px;cursor:pointer}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--blue);box-shadow:0 0 0 4px var(--focus)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:560px){.row{grid-template-columns:1fr}}
.derived{display:inline-flex;align-items:center;gap:8px;background:var(--chip);color:var(--navy);
 border-radius:999px;padding:6px 13px;font-size:13px;font-weight:600;margin-top:2px}
.hidden{display:none!important}
/* chips input */
.chips{display:flex;flex-wrap:wrap;gap:7px;border:1.5px solid var(--line);border-radius:11px;
 padding:8px;min-height:46px;background:#fff;position:relative}
.chips.focus{border-color:var(--blue);box-shadow:0 0 0 4px var(--focus)}
.results{position:absolute;left:-1px;right:-1px;top:100%;margin-top:5px;z-index:30;background:#fff;
 border:1.5px solid var(--line);border-radius:11px;box-shadow:0 10px 28px rgba(20,40,90,.16);
 max-height:260px;overflow:auto}
.ritem{padding:9px 13px;font-size:13.5px;cursor:pointer}
.ritem:hover{background:var(--chip);color:var(--navy)}
.rnote{padding:9px 13px;font-size:12.5px;color:var(--muted)}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--chip);color:var(--navy);
 border-radius:999px;padding:5px 6px 5px 12px;font-size:13px;font-weight:600}
.chip b{font-weight:600}
.chip button{border:0;background:#c9d6f3;color:var(--navy);width:18px;height:18px;border-radius:50%;
 cursor:pointer;font-size:12px;line-height:1;display:grid;place-items:center}
.chips input{border:0;flex:1;min-width:120px;padding:6px;font-size:14px;box-shadow:none!important}
.chips input:focus{outline:none}
/* products tri-state */
.prod{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)}
.prod:last-child{border-bottom:0}
.prod .pl{flex:1;font-weight:600;font-size:14px}
.seg{display:inline-flex;border:1.5px solid var(--line);border-radius:10px;overflow:hidden}
.seg button{border:0;background:#fff;padding:7px 13px;font-size:12.5px;font-weight:600;color:var(--muted);cursor:pointer}
.seg button+button{border-left:1.5px solid var(--line)}
.seg button.on[data-v=""]{background:#eef2f9;color:var(--ink)}
.seg button.on[data-v="yes"]{background:var(--ok);color:#fff}
.seg button.on[data-v="no"]{background:var(--no);color:#fff}
/* footer bar */
.bar{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid var(--line);
 box-shadow:0 -6px 22px rgba(20,40,90,.08);padding:14px 18px;z-index:30}
.barw{max-width:760px;margin:0 auto;display:flex;align-items:center;flex-wrap:wrap;gap:10px 12px}
/* Status stays on ONE line (ellipsis) so the bar never grows tall enough to cover the
   last card's buttons; the buttons never wrap their own text. */
.status{flex:1 1 200px;min-width:120px;color:var(--muted);font-size:13px;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .btn{white-space:nowrap;flex:0 0 auto}
.btn{border:0;border-radius:11px;padding:12px 18px;font-size:14.5px;font-weight:700;cursor:pointer}
.btn.primary{background:var(--blue);color:#fff}
.btn.ghost{background:#eef2f9;color:var(--navy)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.status{color:var(--muted);font-size:12.5px;flex:1}
.toggle-adv{color:var(--blue);font-size:12.5px;font-weight:600;cursor:pointer;user-select:none}
.mtargets{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px}
.mtargets button{border:1.5px solid var(--line);background:#fff;color:var(--muted);
 border-radius:9px;padding:7px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
.mtargets button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.mtargets button:disabled{opacity:.35;cursor:not-allowed;text-decoration:line-through}
datalist{display:none}
</style></head>
<body>
<header><div class="hwrap">
  <div><h1>Campaign Plan</h1><p>Paramount Promo — Digital Ad Operations</p></div>
  <div class="spacer"></div>
</div></header>
<div class="wrap">

  <div class="card">
    <h2>Campaign</h2><p class="sub">Pick the region, then the campaign — that sets the brand, advertiser and default products for you.</p>
    <div class="row">
      <div class="field"><label>Region <span class="req">*</span></label>
        <select id="region"></select></div>
      <div class="field" id="langWrap"><label>Language</label>
        <select id="language"><option value="">—</option><option>English</option><option>French</option></select>
        <div class="hint">Canada only — routes to the FR vs EN advertiser.</div></div>
    </div>
    <div class="field"><label>Campaign <span class="req">*</span></label>
      <select id="campaign"></select>
      <div id="brandChip"></div>
      <div style="margin-top:11px">
        <a href="BRAND_REQUEST_URL_PLACEHOLDER" target="_blank" rel="noopener"
           style="display:inline-flex;align-items:center;gap:8px;background:#eef4ff;color:var(--blue);
                  border:1.5px solid var(--blue);border-radius:10px;padding:10px 16px;font-weight:700;
                  font-size:14px;text-decoration:none">🏷️ Create a Brand in FreeWheel ↗</a>
        <div class="hint" style="margin-top:6px">Brand not set up yet? Request it here — it must exist in FreeWheel to be mapped to the IO &amp; Placements (Custom Exclusivity).</div>
      </div></div>
    <div class="field"><label>Salesforce Case #</label>
      <input type="text" id="sf_case" placeholder="e.g. 00123456">
      <div class="hint">The case this campaign is for — carried through so the created FreeWheel draft maps back to it. Fill this to add the row to the batch Sheet.</div></div>
    <div class="field"><label>Primary Trafficker</label>
      <input type="text" id="primary_trafficker" placeholder="your name (the CM submitting)">
      <div class="hint">Stamped onto the IO's <b>Primary Trafficker</b> field — the draft is owned by whoever submits it.</div></div>
  </div>

  <div class="card">
    <h2>Creative & naming</h2><p class="sub">What's being promoted.</p>
    <div class="field"><label>Promoted title <span class="req">*</span></label>
      <input type="text" id="title" placeholder="e.g. Frisco King"></div>
    <div class="row">
      <div class="field"><label>Season or messaging</label>
        <input type="text" id="season" placeholder="e.g. Season 1 / Now Streaming / Launch">
        <div class="hint">The middle of every placement name — use it for the season, launch beat, or campaign messaging.</div></div>
      <div class="field"><label>Content type</label>
        <select id="content_type"><option value="show">Show</option><option value="movie">Movie</option></select></div>
    </div>
    <div class="row">
      <div class="field"><label>Show / Movie ID</label><input type="text" id="content_id" placeholder="the ShowID or MovieID">
        <div class="hint">Pick <b>Content type</b> above (Show vs Movie) to set the tag.</div></div>
      <div class="field"><label>Recommended Show ID</label><input type="text" id="rec_show_id"></div>
    </div>
    <div class="note hidden" id="pplusIdNudge">This is a <b>Paramount+</b> campaign — the <b>Show / Movie ID</b> above is stamped as <code>[ShowID:…]</code> / <code>[MovieID:…]</code> onto <b>every placement</b> in the order (all tiers), not just the Pre-Roll/Bumper. Left blank, it's stamped empty for the CM to fill in FreeWheel.</div>
    <div class="field" id="kidsWrap"><label>Kids audience</label>
      <div class="seg" id="kidsSeg">
        <button type="button" data-k="older">Older</button>
        <button type="button" data-k="younger">Younger</button>
        <button type="button" data-k="both">Both</button></div>
      <div class="hint">Kids brands only — which age group(s) to build.</div></div>
  </div>

  <div class="card">
    <h2>Flighting</h2>
    <div class="row">
      <div class="field"><label>Flight start</label><input type="date" id="flight_start"></div>
      <div class="field"><label>Flight end</label><input type="date" id="flight_end"></div>
    </div>
    <div class="row">
      <div class="field"><label>Video durations (seconds)</label>
        <div class="chips" data-chips="durations" data-numeric="1"><input type="text" placeholder="30, 15…  ↵"></div>
        <div class="hint">Type a number and press Enter. Common: 30, 15, 60.</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Products</h2><p class="sub">Each toggle is preset to this brand's standard set — every product that gets built is shown as <b>Yes</b>. Switch any to <b>No</b> to leave it out. Only the products this campaign can run appear.</p>
    <div id="products"></div>
  </div>

  <div class="card" id="addonsCard">
    <h2>Add-ons</h2><p class="sub">Optional Video Domination + takeover.</p>
    <div class="row">
      <div class="field"><label>Video Domination</label><select id="video_domination"></select></div>
      <div class="field"><label>Takeover</label><select id="takeover"></select></div>
    </div>
    <div class="field"><label>Scene Lift</label>
      <select id="scene_lift">
        <option value="">No — normal promo</option>
        <option value="ai">AI Scene Lift (Tier 3 only)</option>
        <option value="standard">60s / Standard Scene Lift (Tiers 1–3)</option>
      </select>
      <div class="hint" id="sceneLiftHint">Pluto TV UK / CA / USA only. Placements are added into the existing <b>Scene Lifts – {Region}</b> IO under the Pluto campaign; the promoted title + its audience are still excluded.</div></div>
    <div class="field hidden" id="vdTargetWrap"><label>Video Domination targeting (Pluto categories)</label>
      <div class="chips" data-chips="vd_targeting" data-suggest="categories"><input type="text" placeholder="Comedy, Crime…  ↵"></div></div>
    <div class="field hidden" id="ratingWrap"><label>Rating restrictions (AU Network 10)</label>
      <div class="chips" data-chips="rating_restrictions"><input type="text" placeholder="VG value  ↵"></div></div>
  </div>

  <div class="card">
    <h2>Targeting</h2><p class="sub">Type to search — pick from the real FreeWheel list (no free text). Categories &amp; channels are for the selected Region. Audience Segments (Tier 1) auto-resolve from the Showlist; leave blank.</p>
    <div class="note hidden" id="plutoNudge">This is a <b>Pluto</b> campaign — add the specific <b>Pluto channels / categories</b> below to target that inventory directly. Left blank, the lines run across the whole Pluto platform (broadest reach).</div>
    <div class="field"><label>Showlist</label><div class="chips" data-chips="showlist" data-source="shows"><input type="text" placeholder="type to search a series…"></div></div>
    <div class="field"><label>Genres</label><div class="chips" data-chips="genres" data-source="genres"><input type="text" placeholder="type to search a genre…"></div></div>
    <div class="field"><label>Pluto categories</label><div class="chips" data-chips="pluto_categories" data-source="categories"><input type="text" placeholder="type to search a category…"></div>
      <div class="hint">Category / channel options are for the selected Region.</div></div>
    <div class="field"><label>Pluto channels</label><div class="chips" data-chips="pluto_channels" data-source="channels"><input type="text" placeholder="type to search a channel…"></div></div>
    <div class="field"><label>Audience Segments (Tier 1)</label>
      <div class="chips" data-chips="audience_segments" data-source="audience"><input type="text" placeholder="usually blank — auto-resolved from the showlist"></div>
      <div class="hint">Tier 1 is standard across all markets. Usually left blank (auto-resolved from the showlist) — add specific DDA segments only if needed.</div>
      <div style="margin-top:11px">
        <a href="AUDIENCE_REQUEST_URL_PLACEHOLDER" target="_blank" rel="noopener"
           style="display:inline-flex;align-items:center;gap:8px;background:#eef4ff;color:var(--blue);
                  border:1.5px solid var(--blue);border-radius:10px;padding:10px 16px;font-weight:700;
                  font-size:14px;text-decoration:none">🎯 Request a new audience segment ↗</a>
        <div class="hint" style="margin-top:6px">Not in the list yet? Submit it now — it'll be applied once created.</div>
      </div></div>
  </div>

  <div class="card">
    <h2>Exclude from all placements</h2>
    <p class="sub">Keep the promo from running inside a title or channel. The promoted title is excluded automatically — add any extra series or Pluto channels here and they're excluded on <b>every</b> placement in the order.</p>
    <div class="field"><label>Series to exclude</label><div class="chips" data-chips="exclude_series" data-source="shows"><input type="text" placeholder="type to search a series to exclude…"></div></div>
    <div class="field"><label>Pluto channels to exclude</label><div class="chips" data-chips="exclude_channels" data-source="channels"><input type="text" placeholder="type to search a channel to exclude…"></div></div>
    <div class="field"><label>Movie videos to exclude</label>
      <div class="chips" data-chips="exclude_videos" data-numeric="1"><input type="text" placeholder="FreeWheel Video ID  ↵"></div>
      <div class="hint">For <b>movies</b> (single video assets, not series). Paste the FreeWheel <b>Video ID</b> — excluded on every placement. Type the ID and press Enter.</div></div>
    <div class="field"><label>Audience segments to exclude</label>
      <div class="chips" data-chips="exclude_audience_segments" data-source="audience"><input type="text" placeholder="type to search a segment to exclude…"></div>
      <div class="hint">Keep the promo OUT of an existing DDA audience segment — excluded on <b>every</b> placement, in every relationship. Type-to-search the real segment.</div></div>
  </div>

  <div class="card hidden" id="mirrorCard">
    <h2>Duplicate to another market</h2>
    <p class="sub">Building the same title in other countries? Pick the target markets — each gets the same creative &amp; targeting, re-pointed at that country's equivalent brand, with naming and placements re-derived. Fill this plan out first, then download a plan file per market.</p>
    <div class="mtargets" id="mirrorTargets"></div>
    <div class="hint" id="mirrorNote"></div>
    <button class="btn ghost" id="mirrorBtn" type="button" disabled>Download mirrored plan(s)</button>
  </div>
</div>

<div class="bar"><div class="barw">
  <span class="status" id="status">Fill Region, Campaign and Promoted title to continue.</span>
  <button class="btn ghost" id="copyBtn">Copy JSON</button>
  <button class="btn ghost" id="rowBtn" disabled title="Copy this campaign as one row, then paste it into the next empty line of the batch Sheet">Copy row for Sheet</button>
  <button class="btn ghost" id="dlBtn" disabled>Download plan file</button>
  <button class="btn primary" id="slackBtn" disabled title="Download the plan file and open the #promo-order-automations-submissions Slack channel to post it">Download &amp; post to Slack</button>
</div></div>

<script>
const APP = /*APP_DATA*/;
const $ = s => document.querySelector(s);
const state = {kids:new Set(), lists:{}};

// region + campaign
$("#region").innerHTML = '<option value="">Select region…</option>' +
  APP.regions.map(r=>`<option value="${r.code}">${r.name} (${r.code})</option>`).join("");
$("#video_domination").innerHTML = '<option value="">None</option>' +
  APP.videoDominations.map(o=>`<option value="${o.key}">${o.label}</option>`).join("");
$("#takeover").innerHTML = '<option value="">None</option>' +
  APP.takeovers.map(o=>`<option value="${o.key}">${o.label}</option>`).join("");

function currentCampaign(){ return APP.campaigns.find(c=>c.name===$("#campaign").value); }

$("#region").addEventListener("change", ()=>{
  const rc = $("#region").value;
  const cs = APP.campaigns.filter(c=>c.region===rc);
  $("#campaign").innerHTML = '<option value="">Select campaign…</option>' +
    cs.map(c=>`<option value="${c.name}">${c.name}</option>`).join("");
  $("#langWrap").classList.toggle("hidden", rc!=="CA");
  onCampaign();
});
$("#campaign").addEventListener("change", onCampaign);

function onCampaign(){
  const c = currentCampaign();
  $("#brandChip").innerHTML = c ? `<span class="derived">Brand: ${c.brand}</span>` : "";
  $("#kidsWrap").classList.toggle("hidden", !(c && c.kids));
  // products
  const prods = c ? c.products : [];
  const defs = (c && c.product_defaults) || {};
  $("#products").innerHTML = prods.length ? prods.map(p=>prodRow(p, defs[p])).join("")
     : '<p class="hint">Pick a campaign to see its products.</p>';
  bindProducts();
  const isAU = c && c.region==="AU";
  $("#ratingWrap").classList.toggle("hidden", !(c && c.products.includes("network_10")));
  $("#plutoNudge").classList.toggle("hidden", !(c && c.sig && c.sig.startsWith("pluto")));
  $("#pplusIdNudge").classList.toggle("hidden", !(c && c.sig && c.sig.startsWith("paramount_plus")));
  renderMirrorTargets();
  validate();
}

// --- Duplicate to another market -----------------------------------------
const mirrorTargets = new Set();
function renderMirrorTargets(){
  const c = currentCampaign();
  $("#mirrorCard").classList.toggle("hidden", !c);
  mirrorTargets.clear();
  if(!c){ return; }
  const box = $("#mirrorTargets");
  box.innerHTML = APP.regions.filter(r=>r.code!==c.region).map(r=>{
    const has = c.sig && APP.campaigns.some(x=>x.region===r.code && x.sig===c.sig);
    return `<button type="button" data-r="${r.code}" ${has?"":"disabled title='no equivalent brand here'"}>${r.code}</button>`;
  }).join("");
  box.querySelectorAll("button:not([disabled])").forEach(b=>b.addEventListener("click",()=>{
    const r=b.dataset.r;
    if(mirrorTargets.has(r)){ mirrorTargets.delete(r); b.classList.remove("on"); }
    else { mirrorTargets.add(r); b.classList.add("on"); }
    updateMirrorBtn();
  }));
  $("#mirrorNote").textContent = c.sig
    ? "Greyed-out markets have no equivalent brand for this campaign."
    : "This campaign can't be mirrored automatically.";
  updateMirrorBtn();
}
function updateMirrorBtn(){ $("#mirrorBtn").disabled = !(validate() && mirrorTargets.size); }
function equivalentCampaign(region, sig){
  const m = APP.campaigns.find(x=>x.region===region && x.sig===sig);
  return m ? m.name : null;
}
$("#mirrorBtn").addEventListener("click",()=>{
  if(!validate() || !mirrorTargets.size) return;
  const c = currentCampaign(); const base = buildPlan();
  [...mirrorTargets].forEach((region,i)=>{
    const equ = equivalentCampaign(region, c.sig); if(!equ) return;
    const plan = JSON.parse(JSON.stringify(base));
    plan.region = region; plan.campaign = {name:equ};
    const name = (plan.promoted_title+"-"+region).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")+".plan.json";
    setTimeout(()=>{
      const a=document.createElement("a");
      a.href=URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)],{type:"application/json"}));
      a.download=name; a.click();
    }, i*250);   // stagger so the browser allows the batch of downloads
  });
});
function prodRow(fam, deflt){
  const def = deflt ? "yes" : "no";   // preset to the brand's real default
  return `<div class="prod" data-fam="${fam}" data-default="${def}"><div class="pl">${APP.productLabels[fam]||fam}</div>
    <div class="seg">
      <button type="button" data-v="yes" class="${def==='yes'?'on':''}">Yes</button>
      <button type="button" data-v="no" class="${def==='no'?'on':''}">No</button></div></div>`;
}
function bindProducts(){
  document.querySelectorAll(".prod .seg").forEach(seg=>{
    seg.querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{
      seg.querySelectorAll("button").forEach(x=>x.classList.remove("on"));
      b.classList.add("on");
    }));
  });
}
// kids tri-state (multi)
$("#kidsSeg").querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{
  const k=b.dataset.k;
  if(k==="both"){ state.kids=new Set(["older","younger"]); }
  else { state.kids.has(k)?state.kids.delete(k):state.kids.add(k); }
  $("#kidsSeg").querySelectorAll("button").forEach(x=>{
    const on = x.dataset.k==="both" ? (state.kids.has("older")&&state.kids.has("younger"))
      : state.kids.has(x.dataset.k);
    x.classList.toggle("on", on);
  });
}));
// VD targeting show/hide
$("#video_domination").addEventListener("change",()=>{
  $("#vdTargetWrap").classList.toggle("hidden", $("#video_domination").value!=="pluto");
});

// Region-aware source lists for the type-to-search pickers.
function sourceList(name){
  if(name==="shows") return APP.shows;
  if(name==="genres") return APP.genres;
  if(name==="audience") return APP.audienceSegments;
  const rc=$("#region").value;
  if(name==="categories") return (APP.categoriesByRegion||{})[rc]||[];
  if(name==="channels") return (APP.channelsByRegion||{})[rc]||[];
  return null;
}

// chip fields: type-to-search over a real FreeWheel list (strict — only real values),
// or a plain chip input (numeric/free) when no data-source is set.
document.querySelectorAll(".chips").forEach(box=>{
  const key=box.dataset.chips; state.lists[key]=[];
  const src=box.dataset.source;
  const input=box.querySelector("input");
  const menu=document.createElement("div"); menu.className="results hidden"; box.appendChild(menu);
  const render=()=>{
    box.querySelectorAll(".chip").forEach(c=>c.remove());
    state.lists[key].forEach((v,i)=>{
      const el=document.createElement("span"); el.className="chip";
      el.innerHTML=`<b></b>`; el.querySelector("b").textContent=v;
      const x=document.createElement("button"); x.type="button"; x.textContent="×";
      x.onclick=()=>{ state.lists[key].splice(i,1); render(); };
      el.appendChild(x); box.insertBefore(el,input);
    }); validate();
  };
  const add=v=>{ v=(v||"").trim(); if(!v) return;
    if(box.dataset.numeric && !/^\d+$/.test(v)) return;
    if(src){ const list=sourceList(src)||[];               // strict: must be a real value
      const hit=list.find(x=>x.toLowerCase()===v.toLowerCase()); if(!hit) return; v=hit; }
    if(!state.lists[key].includes(v)){ state.lists[key].push(v); render(); }
    input.value=""; closeMenu(); };
  const closeMenu=()=>{ menu.classList.add("hidden"); menu.innerHTML=""; };
  const showMenu=()=>{
    if(!src){ closeMenu(); return; }
    const q=input.value.trim().toLowerCase();
    if(q.length<2){ closeMenu(); return; }
    const list=sourceList(src)||[];
    if(!list.length){ menu.innerHTML='<div class="rnote">Pick a Region first</div>'; menu.classList.remove("hidden"); return; }
    const raw=[]; for(let i=0;i<list.length && raw.length<250;i++){ if(list[i].toLowerCase().includes(q)) raw.push(list[i]); }
    // Rank: whole-word / start-of-name matches above mid-word substrings ("NCIS"
    // beats "Francisco"), then shorter names first.
    const rank=s=>{ s=s.toLowerCase(); return s.startsWith(q)?0 : (s.includes(" "+q)||s.includes("-"+q)||s.includes(":"+q))?1 : 2; };
    raw.sort((a,b)=>rank(a)-rank(b) || a.length-b.length);
    const hits=raw.slice(0,40);
    if(!hits.length){ menu.innerHTML='<div class="rnote">No match</div>'; menu.classList.remove("hidden"); return; }
    menu.innerHTML=hits.map(h=>`<div class="ritem"></div>`).join("");
    [...menu.children].forEach((el,i)=>{ el.textContent=hits[i]; el.onmousedown=e=>{e.preventDefault(); add(hits[i]);}; });
    menu.classList.remove("hidden");
  };
  input.addEventListener("input",showMenu);
  input.addEventListener("keydown",e=>{
    if(e.key==="Enter"){ e.preventDefault();
      const first=menu.querySelector(".ritem"); add(first?first.textContent:input.value); }
    else if(e.key==="Escape"){ closeMenu(); }
    else if(e.key==="Backspace"&&!input.value&&state.lists[key].length){ state.lists[key].pop(); render(); }
  });
  input.addEventListener("blur",()=>{ if(input.value.trim()) add(input.value); setTimeout(closeMenu,150); box.classList.remove("focus"); });
  box.addEventListener("click",e=>{ if(e.target===box||e.target===input) input.focus(); });
  input.addEventListener("focus",()=>{ box.classList.add("focus"); showMenu(); });
});
// Region change -> the region-scoped pickers (categories/channels) reset their options.
$("#region").addEventListener("change",()=>{
  ["pluto_categories","pluto_channels","exclude_channels"].forEach(k=>{
    if(state.lists[k]&&state.lists[k].length){ state.lists[k]=[];
      const box=document.querySelector(`[data-chips="${k}"]`);
      if(box) box.querySelectorAll(".chip").forEach(c=>c.remove()); }
  });
});
["title"].forEach(id=>$("#"+id).addEventListener("input",validate));

function validate(){
  const core = $("#region").value && $("#campaign").value && $("#title").value.trim();
  const hasDur = ((state.lists.durations||[]).length)>0;
  const ok = core && hasDur;
  $("#dlBtn").disabled = !ok; $("#rowBtn").disabled = !ok; $("#slackBtn").disabled = !ok;
  // Keep the mirror ("Download mirrored plan(s)") button in sync on EVERY field change,
  // not just on market-chip clicks — enabled once the plan is valid AND a market is ticked.
  const mb=$("#mirrorBtn");
  if(mb) mb.disabled = !(ok && typeof mirrorTargets!=="undefined" && mirrorTargets.size);
  $("#status").textContent = ok
    ? "Ready — click Download & post to Slack (or Copy row for Sheet for a batch)."
    : (core && !hasDur
        ? "Add at least one Video duration (type e.g. 30 and press Enter) to continue."
        : "Fill Region, Campaign, Promoted title and Video durations to continue.");
  return ok;
}

function buildPlan(){
  const c = currentCampaign();
  // Emit a product override only when the CM changed it from the brand default, so an
  // untouched form behaves exactly as before (default set), and an explicit flip is sent.
  const po={}; document.querySelectorAll(".prod").forEach(p=>{
    const v=p.querySelector(".seg button.on").dataset.v;
    if(v!==p.dataset.default) po[p.dataset.fam]=(v==="yes"); });
  const L=state.lists; const plan={
    promoted_title:$("#title").value.trim(), region:$("#region").value,
    campaign:{name:$("#campaign").value},
  };
  if($("#sf_case").value) plan.salesforce_case=$("#sf_case").value.trim();
  if($("#language").value) plan.language=$("#language").value;
  if($("#season").value) plan.season_or_messaging=$("#season").value;
  if($("#primary_trafficker").value) plan.primary_trafficker=$("#primary_trafficker").value.trim();
  plan.content_type=$("#content_type").value;
  if($("#content_id").value) plan.content_id=$("#content_id").value;
  if($("#rec_show_id").value) plan.recommended_show_id=$("#rec_show_id").value;
  if(L.durations.length) plan.durations=L.durations.map(Number);
  const fl={}; if($("#flight_start").value)fl.start=$("#flight_start").value;
  if($("#flight_end").value)fl.end=$("#flight_end").value;
  if(Object.keys(fl).length) plan.flight=fl;
  if(Object.keys(po).length) plan.product_overrides=po;
  if(c&&c.kids&&state.kids.size) plan.kids_audience=[...state.kids];
  if($("#scene_lift").value) plan.scene_lift=$("#scene_lift").value;
  if($("#video_domination").value) plan.video_domination=$("#video_domination").value;
  if(L.vd_targeting.length) plan.video_domination_targeting=L.vd_targeting;
  if($("#takeover").value) plan.takeover=$("#takeover").value;
  if(L.rating_restrictions.length) plan.rating_restrictions=L.rating_restrictions;
  if(L.genres.length) plan.genres=L.genres;
  if(L.showlist.length) plan.showlist=L.showlist;
  if(L.audience_segments.length) plan.audience_segments=L.audience_segments;
  const pl={}; if(L.pluto_categories.length)pl.categories=L.pluto_categories;
  if(L.pluto_channels.length)pl.channels=L.pluto_channels; if(Object.keys(pl).length)plan.pluto=pl;
  if(L.exclude_series.length) plan.exclude_series=L.exclude_series;
  if(L.exclude_channels.length) plan.exclude_channels=L.exclude_channels;
  if(L.exclude_videos.length) plan.exclude_videos=L.exclude_videos;
  if(L.exclude_audience_segments.length) plan.exclude_audience_segments=L.exclude_audience_segments;
  return plan;
}
function fname(){ const p=buildPlan();
  return (p.promoted_title+"-"+p.region).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")+".plan.json"; }
function downloadPlan(){
  const blob=new Blob([JSON.stringify(buildPlan(),null,2)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=fname(); a.click();
}
$("#dlBtn").addEventListener("click",()=>{ if(!validate())return; downloadPlan(); });
// Download the plan file, then open the submissions Slack channel so the CM can drag the
// just-downloaded file into the message. URL is APP.slackSubmitUrl (set in build_plan_form.py).
$("#slackBtn").addEventListener("click",()=>{
  if(!validate())return;
  downloadPlan();
  const b=$("#slackBtn"); b.textContent="Downloaded ✓ — attach it in Slack";
  setTimeout(()=>window.open(APP.slackSubmitUrl,"_blank"), 500);
  setTimeout(()=>b.textContent="Download & post to Slack", 2600);
});
$("#copyBtn").addEventListener("click",async()=>{
  await navigator.clipboard.writeText(JSON.stringify(buildPlan(),null,2));
  $("#copyBtn").textContent="Copied ✓"; setTimeout(()=>$("#copyBtn").textContent="Copy JSON",1400);
});

// --- Copy one row for the batch Google Sheet -------------------------------- //
// Maps the plan into the canonical Sheet column order (APP.sheetColumns). List cells are
// ";"-joined; product toggles become "Y"/""; the row is tab-separated so pasting drops it
// across the Sheet's columns in one line.
function cellFor(col, plan){
  const list=v=>Array.isArray(v)?v.join("; "):"";
  const pf=plan.product_overrides||{}; const fl=plan.flight||{}; const pl=plan.pluto||{};
  // Product toggle -> "Y" (explicit on) / "N" (explicit off) / "" (brand default, untouched).
  const tog=k=>(k in pf)?(pf[k]?"Y":"N"):"";
  switch(col){
    case "Salesforce Case": return plan.salesforce_case||"";
    case "Region": return plan.region||"";
    case "Campaign Name": return (plan.campaign||{}).name||"";
    case "Promoted Title": return plan.promoted_title||"";
    case "Content Type": return plan.content_type||"";
    case "Content ID": return plan.content_id||"";
    case "Recommended Show ID": return plan.recommended_show_id||"";
    case "Video Durations": return list(plan.durations);
    case "Flight Start": return fl.start||"";
    case "Flight End": return fl.end||"";
    case "Language": return plan.language||"";
    case "Season or Messaging": return plan.season_or_messaging||"";
    case "Primary Trafficker": return plan.primary_trafficker||"";
    case "Genres": return list(plan.genres);
    case "Showlist": return list(plan.showlist);
    case "Pluto Categories": return list(pl.categories);
    case "Pluto Channels": return list(pl.channels);
    case "Audience Segments": return list(plan.audience_segments);
    case "Exclude Series": return list(plan.exclude_series);
    case "Exclude Channels": return list(plan.exclude_channels);
    case "Exclude Videos": return list(plan.exclude_videos);
    case "Exclude Audience Segments": return list(plan.exclude_audience_segments);
    case "Kids Audience": return list(plan.kids_audience);
    case "Video Domination": return plan.video_domination||"";
    case "Video Domination Targeting": return list(plan.video_domination_targeting);
    case "Takeover": return plan.takeover||"";
    case "Scene Lift": return plan.scene_lift||"";
    case "Rating Restrictions": return list(plan.rating_restrictions);
    // "Include X" product toggles -> Y / "" (only when explicitly set on/off).
    case "Include Remnant Video": return tog("remnant_video");
    case "Include Pause Ads": return tog("pause_ads");
    case "Include Premium Pre-Roll": return tog("premium_preroll");
    case "Include Essential Bumper": return tog("essential_bumper");
    case "Include CBS Pre-Roll": return tog("cbs_preroll");
    case "Include After Mid-Roll Bumper": return tog("after_midroll_bumper");
    case "Include 1Z Lockdown": return tog("cbs_1z_lockdown");
    case "Include 2Z Lockdown": return tog("cbs_2z_lockdown");
    case "Include Pluto": return tog("pluto_breakout");
    case "Include Network 10": return tog("network_10");
    default: return "";
  }
}
function sheetRow(){ const p=buildPlan();
  return (APP.sheetColumns||[]).map(c=>String(cellFor(c,p)).replace(/\t/g," ")).join("\t"); }
$("#rowBtn").addEventListener("click",async()=>{
  if(!validate())return;
  await navigator.clipboard.writeText(sheetRow());
  const b=$("#rowBtn"); b.textContent="Row copied ✓ — paste into the Sheet";
  setTimeout(()=>b.textContent="Copy row for Sheet",1800);
});
validate();
</script>
</body></html>
"""


if __name__ == "__main__":
    print(f"Wrote {build()}")
