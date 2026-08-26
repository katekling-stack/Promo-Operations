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
                          "my5": bool(b.get("my5_brand")),
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
        # My5 (Channel 5) inventory options for the "5 - UK" campaigns' My5 Inventory field.
        "my5SiteGroups": _my5_site_group_names(),
        "videoDominations": vd, "takeovers": tk,
        # Canonical batch-Sheet column order (single source of truth in promo_ops.batch),
        # so the "Copy row for Sheet" button emits cells in the Sheet's column order.
        "sheetColumns": SHEET_COLUMNS,
        # Canonical targeting options for type-to-search (generated from FreeWheel).
        **_targeting_options(),
    }


def _my5_site_group_names() -> list:
    """CM-facing My5 Site Group names (Stream Type + My5 Channels) for the My5 Inventory
    picker, from the synced snapshot."""
    import csv as _csv
    path = REPO / "data" / "site_groups" / "synced_my5_site_groups.csv"
    if not path.exists():
        return []
    out = []
    for row in _csv.DictReader(path.open(encoding="utf-8")):
        nm = (row.get("name") or "").strip()
        if nm and (row.get("status", "ACTIVE") == "ACTIVE"):
            out.append(nm)
    return sorted(out)


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
    # Content-rating restrictions per region (top-level ratings only), keyed by region
    # VALUE (USA/GSA/…) so the region-aware picker can filter like categories/channels.
    from promo_ops.ratings import RatingRestrictionResolver
    from promo_ops.config import regions_config
    rr = RatingRestrictionResolver().load()
    ratings = {region: rr.ratings_for(cfg.get("code") or region)
               for region, cfg in regions_config().get("regions", {}).items()}
    # IO-level Brand list per region (synced from FreeWheel), for the Brand picker.
    from promo_ops.brands_resolver import BrandResolver
    br = BrandResolver().load()
    brands = {region: br.brands_for(region) for region in br.regions()}
    return {
        "genres": [v for v, _ in bto.genres()],
        "categoriesByRegion": cats,
        "channelsByRegion": chans,
        "ratingsByRegion": {r: v for r, v in ratings.items() if v},
        "brandsByRegion": {r: v for r, v in brands.items() if v},
        "audienceSegments": [n for n, _ in bto.audience_segments()],
        "shows": [n for _, n in bto.shows()],
        **_geo_options(),
    }


def _geo_options() -> dict:
    """Region-aware sub-country geo picker lists (states / Nielsen DMAs), from data/geo.

    States are scoped to each region's countries (a region maps to its countries' ISO
    codes); a region that spans multiple countries prefixes the country when a plain
    state name would be ambiguous. DMAs are a US-only Nielsen concept.
    """
    from promo_ops.geo import GeoResolver
    from promo_ops.config import regions_config
    g = GeoResolver().load()
    # Plain state NAMES (no country suffix) so the picked value resolves as-is — the engine
    # scopes resolution to the region's ISO set, so it maps "Bavaria" -> the DE state itself.
    states_by_region: dict[str, list[str]] = {}
    for region, cfg in regions_config().get("regions", {}).items():
        isos = GeoResolver.isos_for_countries(cfg.get("countries") or [])
        names = sorted({s["name"] for s in g.states_for(isos) if s["name"]})
        if names:
            states_by_region[region] = names
    # DMAs: US-only. Offer under any domestic (US) region.
    dmas = sorted({d["name"] for d in g.dmas() if d["name"]})
    dmas_by_region = {r: dmas for r, cfg in regions_config().get("regions", {}).items()
                      if "United States" in (cfg.get("countries") or [])}
    return {"statesByRegion": states_by_region, "dmasByRegion": dmas_by_region}


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
.seg button.on[data-k]{background:var(--blue);color:#fff}
.ghostbtn{margin-top:8px;background:#fff;border:1.5px solid var(--line);border-radius:9px;padding:7px 12px;font-size:12.5px;font-weight:600;color:var(--blue);cursor:pointer}
.dpRow{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:8px 0;padding:8px 10px;background:#f7f9fd;border:1px solid var(--line);border-radius:10px}
.dpRow select,.dpRow input[type=time]{padding:5px 7px;border:1.5px solid var(--line);border-radius:8px;font-size:12.5px;background:#fff;color:var(--ink)}
.dpsep{color:var(--muted);font-size:12px}
.dpDel{margin-left:auto;background:none;border:0;color:var(--no);cursor:pointer;font-size:14px;font-weight:700}
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

  <div class="card hidden" id="draftBanner" style="border-color:var(--blue);background:#eef4ff">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span style="font-weight:700;color:var(--blue)">💾 We saved your last draft on this browser</span>
      <span class="hint" id="draftMeta" style="margin:0"></span>
      <span style="flex:1"></span>
      <button class="btn primary" type="button" id="draftRestore">Restore draft</button>
      <button class="btn ghost" type="button" id="draftDiscard">Discard</button>
    </div>
  </div>

  <details class="card" id="briefCard">
    <summary style="cursor:pointer;font-weight:700;font-size:18px;list-style:revert">🧠 Paste a brief — auto-fill targeting <span style="font-weight:400;font-size:13px;color:#888">(beta — click to expand)</span></summary>
    <p class="sub" style="margin-top:10px">Pick <b>Region</b> + <b>Campaign</b> first, then paste your promo brief below. Use labels the tool understands — <code>Networks:</code>, <code>Genres:</code>, <code>Shows:</code>, <code>Pluto Categories:</code>, <code>Pluto Channels:</code>, <code>Audience:</code>, <code>Ratings:</code> (values comma- or line-separated). Exact matches are added to the fields automatically; close matches are <b>suggested</b> for you to confirm; anything unmatched is flagged.</p>
    <textarea id="briefText" rows="8" placeholder="Networks: BET, MTV, Comedy Central&#10;Genres: Comedy, Drama&#10;Shows: NCIS, Yellowstone&#10;Pluto Categories: News, Sports&#10;Pluto Channels: CBS News&#10;Audience: &#10;Ratings: TV-MA&#10;Video Domination: Pluto homepage takeover" style="width:100%;box-sizing:border-box;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;padding:12px;border:1.5px solid var(--line);border-radius:10px;resize:vertical"></textarea>
    <div style="display:flex;gap:10px;align-items:center;margin-top:10px">
      <button class="btn primary" type="button" id="briefParse">Parse &amp; fill</button>
      <button class="btn ghost" type="button" id="briefClear">Clear</button>
      <span class="hint" id="briefHint" style="margin:0"></span>
    </div>
    <div id="briefReport" style="margin-top:14px"></div>
  </details>

  <details class="card" id="suggestCard">
    <summary style="cursor:pointer;font-weight:700;font-size:18px;list-style:revert">✨ Suggest targeting <span style="font-weight:400;font-size:13px;color:#888">(brief + AI + historicals; click to expand)</span></summary>
    <p class="sub" style="margin-top:10px">No show/channel list yet? Give the <b>title</b> — optionally add a <b>description</b> and/or paste a <b>brief</b> — and the tool proposes comp shows, Pluto channels, genres and Pluto categories, all matched to real FreeWheel inventory. It layers every signal you give it (brief, AI, and what <i>similar past campaigns in this region actually ran</i>) and ranks by agreement, so values confirmed by more sources come first. The comp shows populate the Showlist (which feeds both Tier 2 and the Tier 1 DDA audience segments). Pick <b>Region</b> below first — suggestions are region-specific.</p>
    <div class="row">
      <div class="field"><label>Title</label><input type="text" id="suggestTitle" placeholder="e.g. Dexter: Resurrection S2"></div>
    </div>
    <div class="field"><label>Description / logline <span style="font-weight:400;color:#888">(optional)</span></label>
      <textarea id="suggestDesc" rows="3" placeholder="A dark, suspenseful crime thriller about a vigilante serial killer in NYC…" style="width:100%;box-sizing:border-box;font-size:13px;padding:10px;border:1.5px solid var(--line);border-radius:10px;resize:vertical"></textarea></div>
    <div class="field"><label>Paste a brief <span style="font-weight:400;color:#888">(optional — if you have one, it's the strongest signal)</span></label>
      <textarea id="suggestBrief" rows="4" placeholder="Paste the campaign brief text here (comp titles, genres, audiences…). Leave blank to suggest from title + historicals." style="width:100%;box-sizing:border-box;font-size:13px;padding:10px;border:1.5px solid var(--line);border-radius:10px;resize:vertical"></textarea></div>
    <div style="display:flex;gap:10px;align-items:center;margin-top:8px">
      <button class="btn primary" type="button" id="suggestBtn">✨ Suggest targeting</button>
      <span class="hint" id="suggestHint" style="margin:0"></span>
    </div>
    <div id="suggestReport" style="margin-top:14px"></div>
  </details>

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
      <div class="field" style="margin-top:11px"><label>Brand (IO-level, for Custom Exclusivity)</label>
        <div class="chips" data-chips="brand_pick" data-source="brands" data-single="1" data-allow-new="1"><input type="text" placeholder="type to search — or type a new name to create it…"></div>
        <div class="hint">Pick <b>one</b> existing Brand (region-filtered) — or <b>type a new name</b> (e.g. <code>{Title} (Promo) ({CC})</code>, or <code>… - Kids (Promo) (CC)</code>) and it'll be <b>created on the live push</b> under the advertiser (kids get Industry <b>Rating: G</b>). New adult titles may also need a Global Brand created via the button below.</div></div>
      <div style="margin-top:11px">
        <a href="BRAND_REQUEST_URL_PLACEHOLDER" target="_blank" rel="noopener"
           style="display:inline-flex;align-items:center;gap:8px;background:#eef4ff;color:var(--blue);
                  border:1.5px solid var(--blue);border-radius:10px;padding:10px 16px;font-weight:700;
                  font-size:14px;text-decoration:none">🏷️ Submit a Brand for Global Brand Mapping ↗</a>
        <div class="hint" style="margin-top:6px">Global Brand Mapping not set up yet? Request it here and Kelly Malloy will submit and build in FreeWheel once ready.</div>
      </div></div>
    <div class="field"><label>Salesforce Case #</label>
      <input type="text" id="sf_case" placeholder="e.g. 00123456">
      <div class="hint">The case this campaign is for — carried through so the created FreeWheel draft maps back to it. Fill this to add the row to the batch Sheet.</div></div>
    <div class="field"><label>Primary Trafficker</label>
      <input type="text" id="primary_trafficker" placeholder="your name (the CM submitting)">
      <div class="hint">Stamped onto the IO's <b>Primary Trafficker</b> field — the draft is owned by whoever submits it.</div></div>
    <div class="field"><label>Add to existing IO <span style="color:var(--muted);font-weight:400">(optional)</span></label>
      <input type="text" id="existing_io_id" placeholder="existing FreeWheel IO ID (e.g. for Season 2 → Season 1's IO)">
      <div class="hint">Leave blank to create a <b>new</b> IO. To add these placements into an <b>existing</b> IO (e.g. new season lines into the IO that's already live), paste that IO's FreeWheel ID — no new IO is created.</div></div>
  </div>

  <div class="card">
    <h2>Creative & naming</h2><p class="sub">What's being promoted.</p>
    <div class="field"><label>Promoted title <span class="req">*</span></label>
      <input type="text" id="title" placeholder="e.g. Frisco King"></div>
    <div class="row">
      <div class="field"><label>Season or messaging</label>
        <input type="text" id="season" placeholder="e.g. Season 1 / Now Streaming / Launch">
        <div class="hint">The middle of every placement name — use it for the season, launch beat, or campaign messaging.</div></div>
      <div class="field hidden" id="ctypeWrap"><label>Content type</label>
        <select id="content_type"><option value="show">Show</option><option value="movie">Movie</option><option value="na">N/A</option></select>
        <div class="hint">Select when you need to note a Show or Movie ID for Paramount+ campaigns. Leave as <b>N/A</b> for campaigns that don't need a Show/Movie ID.</div></div>
    </div>
    <div class="row hidden" id="pplusIdRow">
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
      <div class="field"><label>Flight start</label>
        <div style="display:flex;gap:6px">
          <input type="date" id="flight_start" style="flex:1">
          <input type="time" id="flight_start_time" step="3600" title="optional start time (region's time zone)" style="width:120px"></div>
        <div class="hint">Time optional — leave blank to start at the region's default hour.</div></div>
      <div class="field"><label>Flight end</label>
        <div style="display:flex;gap:6px">
          <input type="date" id="flight_end" style="flex:1">
          <input type="time" id="flight_end_time" step="3600" title="optional end time (region's time zone)" style="width:120px"></div>
        <div class="hint">Time optional — leave blank to end at 11:59 PM.</div></div>
    </div>
    <div class="row">
      <div class="field"><label>Video durations (seconds)</label>
        <div class="chips" data-chips="durations" data-numeric="1"><input type="text" placeholder="30, 15…  ↵"></div>
        <div class="hint">Type a number and press Enter. Common: 30, 15, 60.</div></div>
    </div>
    <div class="field"><label>Daypart (time restrictions)</label>
      <div class="hint">Default <b>24/7</b> — leave empty to run all day. Add windows to restrict to specific times (in the market's time zone). Applies to every placement.</div>
      <div id="daypartRows"></div>
      <button type="button" id="addDaypart" class="ghostbtn">+ Add time window</button></div>
  </div>

  <div class="card">
    <h2>Products</h2><p class="sub">Each toggle is preset to this brand's standard set — every product that gets built is shown as <b>Yes</b>. Switch any to <b>No</b> to leave it out. Only the products this campaign can run appear.</p>
    <div id="prodQuick" class="hint hidden" style="margin-bottom:8px">Quick select: <span id="prodPauseWrap"><a href="#" id="prodPauseOnly" class="toggle-adv">Pause Ads only</a> · </span><a href="#" id="prodReset" class="toggle-adv">Reset to defaults</a></div>
    <div id="products"></div>
  </div>

  <div class="card" id="addonsCard">
    <h2>Add-ons</h2><p class="sub">Optional Video Domination + takeover.</p>
    <div class="row">
      <div class="field"><label>Video Domination</label><select id="video_domination"></select>
        <div class="hint"><b>Pluto</b> VD is built &amp; pushed to FreeWheel automatically (list the Pluto categories below). <b>Standard / 10 Streaming / My5</b> VDs run in <b>Operative</b> (no API) — they are <b>not</b> automated; you push them manually.</div></div>
      <div class="field"><label>Takeover</label><select id="takeover"></select>
        <div class="hint">All takeovers (<b>HPTO</b> / FITO / Arena / 3-Peat) run in <b>Operative</b> — they are <b>not</b> automated; you push them manually per the Case instructions.</div></div>
    </div>
    <div class="note hidden" id="manualPushReminder" style="border-left:4px solid #d97706;background:#fff7ed">
      ⚠️ <b>Manual push required.</b> This add-on runs in <b>Operative</b>, not FreeWheel. Follow the push instructions in the Case (copy the referenced Operative order → rename → set flight dates → get the 2× approvals → <b>Push All to GAM</b>). The automation does <b>not</b> book or push this for you.</div>
    <div class="field"><label>Scene Lift</label>
      <select id="scene_lift">
        <option value="">No — normal promo</option>
        <option value="ai">AI Scene Lift (Tier 3 only)</option>
        <option value="standard">60s / Standard Scene Lift (Tiers 1–3)</option>
      </select>
      <div class="hint" id="sceneLiftHint">Pluto TV UK / CA / USA only. Placements are added into the existing <b>Scene Lifts – {Region}</b> IO under the Pluto campaign; the promoted title + its audience are still excluded.</div></div>
    <div class="field"><label style="display:flex;align-items:center;gap:9px;cursor:pointer">
        <input type="checkbox" id="standard" style="width:18px;height:18px">
        <span><b>Standard (non-tiered)</b> — don't tier this</span></label>
      <div class="hint">Builds <b>one platform-wide placement per duration</b> (video) + a pause placement at the Standard priorities, instead of the tier stack. Still excludes the promoted title + audience.</div></div>
    <div class="field hidden" id="vdTargetWrap"><label>Video Domination targeting (Pluto categories)</label>
      <div class="chips" data-chips="vd_targeting" data-suggest="categories"><input type="text" placeholder="Comedy, Crime…  ↵"></div></div>
  </div>

  <div class="card">
    <h2>Targeting</h2><p class="sub">Type to search — pick from the real FreeWheel list (no free text). Categories &amp; channels are for the selected Region. Audience Segments (Tier 1) auto-resolve from the Showlist; leave blank.</p>
    <div class="note hidden" id="plutoNudge">This is a <b>Pluto</b> campaign — add the specific <b>Pluto channels / categories</b> below to target that inventory directly. Left blank, the lines run across the whole Pluto platform (broadest reach).</div>
    <div class="field hidden" id="my5Wrap"><label>My5 inventory <span class="req">*</span></label>
      <div class="chips" data-chips="my5_site_groups" data-source="my5"><input type="text" placeholder="type to search My5 endpoints (Stream Type / Channels)…"></div>
      <div class="hint">Channel 5 only — pick the My5 endpoints to run on (e.g. <b>SG: Stream Type: VOD: My5</b>, <b>SG: My5 Channels: UK: MTV Owned</b>). AND-ed into every tier. Leave blank to use the default (Adults: VOD; Kids: VOD + Milkshake).</div></div>
    <div class="field"><label>Showlist</label><div class="chips" data-chips="showlist" data-source="shows"><input type="text" placeholder="type to search a series…"></div>
      <div id="ddaFlag" class="hidden" style="margin-top:8px;font-size:12.5px;background:#FAEEDA;border:1px solid #E6C67A;color:#854F0B;border-radius:8px;padding:9px 12px"></div></div>
    <div class="field"><label>Genres</label><div class="chips" data-chips="genres" data-source="genres"><input type="text" placeholder="type to search a genre…"></div></div>
    <div class="field"><label>Content ratings to include (run ONLY on these)</label>
      <div class="chips" data-chips="rating_inclusions" data-source="ratings"><input type="text" placeholder="type a rating to require (e.g. TV-14, PG)…"></div>
      <div class="hint">Restrict the promo to <b>only</b> the selected rating(s) — the rating VG is added as an <b>AND</b> on <b>every</b> placement/argument, so it runs only where content matches. Region-based options, same as the Region's rating list.</div></div>
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
    <details class="field" style="border-top:1px dashed var(--line);padding-top:14px;margin-top:4px">
      <summary style="cursor:pointer;font-weight:600;list-style:revert">Geo — narrow to states / DMAs / cities <span style="font-weight:400;color:#888">(optional — click to expand; rarely used)</span></summary>
      <div class="hint" style="margin-top:10px">Leave blank to run across the whole region. Anything added here is layered <b>on top</b> of the region's country targeting (added to <code>include</code>) on every placement.</div>
      <label style="margin-top:10px">States</label>
      <div class="chips" data-chips="geo_states" data-source="states"><input type="text" placeholder="type a state (e.g. California)…"></div>
      <label style="margin-top:10px">DMAs <span style="font-weight:400;color:#888">(US only)</span></label>
      <div class="chips" data-chips="geo_dmas" data-source="dmas"><input type="text" placeholder="type a Nielsen DMA (e.g. New York, NY)…"></div>
      <label style="margin-top:10px">Cities</label>
      <div class="chips" data-chips="geo_cities"><input type="text" placeholder="City, ST — e.g. New York, NY (press Enter)"></div>
      <div class="hint">City names are ambiguous, so include the state: <code>Chicago, IL</code>. Must belong to the region.</div>
      <div class="hint" style="margin-top:12px"><b>Exclude</b> instead — run everywhere <b>except</b> the geos below (can combine with the includes above).</div>
      <label style="margin-top:6px">Exclude states</label>
      <div class="chips" data-chips="geo_states_exclude" data-source="states"><input type="text" placeholder="type a state to exclude…"></div>
      <label style="margin-top:10px">Exclude DMAs <span style="font-weight:400;color:#888">(US only)</span></label>
      <div class="chips" data-chips="geo_dmas_exclude" data-source="dmas"><input type="text" placeholder="type a DMA to exclude…"></div>
      <label style="margin-top:10px">Exclude cities</label>
      <div class="chips" data-chips="geo_cities_exclude"><input type="text" placeholder="City, ST to exclude — e.g. Chicago, IL"></div>
    </details>
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
    <div class="field"><label>Content rating restrictions (exclude)</label>
      <div class="chips" data-chips="rating_restrictions" data-source="ratings"><input type="text" placeholder="type a rating to exclude (e.g. TV-MA, R)…"></div>
      <div class="hint">Exclude content of the selected rating(s) — resolves to this market's <code>VG: Content Rating: {region}: {rating}</code> Video Groups and excludes them on <b>every</b> placement. Options are the ratings that exist for the selected Region.</div></div>
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
  <input type="file" id="loadFile" accept=".json,application/json" class="hidden">
  <button class="btn ghost" id="loadBtn" type="button" title="Upload a plan file you downloaded earlier to keep editing it">Load a saved plan</button>
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
  $("#my5Wrap").classList.toggle("hidden", !(c && c.my5));
  // products
  const prods = c ? c.products : [];
  const defs = (c && c.product_defaults) || {};
  $("#products").innerHTML = prods.length ? prods.map(p=>prodRow(p, defs[p])).join("")
     : '<p class="hint">Pick a campaign to see its products.</p>';
  bindProducts();
  $("#prodQuick").classList.toggle("hidden", !prods.length);
  $("#prodPauseWrap").classList.toggle("hidden", !prods.includes("pause_ads"));
  $("#plutoNudge").classList.toggle("hidden", !(c && c.sig && c.sig.startsWith("pluto")));
  // Content Type + Show/Movie ID + Recommended Show ID show for P+ (all) AND Pluto TV
  // (non-kids) — both use the Recommended Show / Show-Movie ID (it rides on Tier 1). Hidden for
  // CBS/MTVE/etc. The P+-specific "stamped on every placement" note stays P+ only.
  const isPplus = !!(c && c.sig && c.sig.startsWith("paramount_plus"));
  const isPlutoNonKids = !!(c && c.sig && c.sig.startsWith("pluto") && !c.kids);
  const showIds = isPplus || isPlutoNonKids;
  $("#ctypeWrap").classList.toggle("hidden", !showIds);
  $("#pplusIdRow").classList.toggle("hidden", !showIds);
  $("#pplusIdNudge").classList.toggle("hidden", !isPplus);
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
// Re-point a brand's trailing "(MARKET)" suffix to the target market, e.g.
// "Caught In The Act: Unfaithful (Promo) (UK)" -> "… (Promo) (IE)". The market token is
// the region key (USA/UK/IE/GSA/…), same as the synced brand naming. Leaves a brand with
// no recognisable suffix untouched.
function reregionBrand(brand, toRegion){
  if(!brand) return brand;
  const known = new Set((APP.regions||[]).map(r=>r.code));
  return brand.replace(/\(([A-Za-z]+)\)\s*$/, (m,tok)=> known.has(tok) ? `(${toRegion})` : m);
}
$("#mirrorBtn").addEventListener("click",()=>{
  if(!validate() || !mirrorTargets.size) return;
  const c = currentCampaign(); const base = buildPlan();
  [...mirrorTargets].forEach((region,i)=>{
    const equ = equivalentCampaign(region, c.sig); if(!equ) return;
    const plan = JSON.parse(JSON.stringify(base));
    plan.region = region; plan.campaign = {name:equ};
    // Market-specific fields must NOT ride along from the source plan:
    //  - io_brand's "(MARKET)" suffix is re-pointed to the target market (a UK brand
    //    name can't be created under the IE advertiser — brand names are network-unique).
    //  - existing_io_id (a FreeWheel IO id) belongs to the source market's IO; drop it so
    //    the mirrored plan creates its own new IO.
    if(plan.io_brand) plan.io_brand = reregionBrand(plan.io_brand, region);
    delete plan.existing_io_id;
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
function setProd(fam, val){   // val "yes"/"no" — flip a product row's toggle
  const seg = document.querySelector('.prod[data-fam="'+fam+'"] .seg');
  if(seg) seg.querySelectorAll("button").forEach(x=>x.classList.toggle("on", x.dataset.v===val));
}
// Quick-select: Pause Ads only (everything else No), or reset every product to its default.
$("#prodPauseOnly").addEventListener("click",e=>{ e.preventDefault();
  document.querySelectorAll(".prod").forEach(r=>setProd(r.dataset.fam, r.dataset.fam==="pause_ads"?"yes":"no"));
});
$("#prodReset").addEventListener("click",e=>{ e.preventDefault();
  document.querySelectorAll(".prod").forEach(r=>setProd(r.dataset.fam, r.dataset.default));
});
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
// VD targeting show/hide + manual-push reminder (non-Pluto VD or any takeover)
function syncManualPushReminder(){
  const vd=$("#video_domination").value, tk=$("#takeover").value;
  const manual=(vd&&vd!=="pluto")||!!tk;
  $("#manualPushReminder").classList.toggle("hidden",!manual);
}
$("#video_domination").addEventListener("change",()=>{
  $("#vdTargetWrap").classList.toggle("hidden", $("#video_domination").value!=="pluto");
  syncManualPushReminder();
});
$("#takeover").addEventListener("change",syncManualPushReminder);

// Daypart (time restrictions): repeatable day-range + time-range windows. Empty = 24/7.
const DP_DAYS=["MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY","SUNDAY"];
function dpDaySelect(sel){
  return '<select class="dpDay">'+DP_DAYS.map(d=>
    `<option value="${d}"${d===sel?' selected':''}>${d[0]+d.slice(1).toLowerCase()}</option>`).join('')+'</select>';
}
function dpHourSelect(cls,selVal,isEnd){
  // Whole hours only — FreeWheel dayparts reject anything off the hour (e.g. 8:30PM).
  // END has no midnight: the latest end is 11:00PM, which runs THROUGH the end of the day.
  // So the End dropdown starts at 1:00 AM (skip hour 0) and labels 11:00 PM accordingly.
  let opts=""; const start=isEnd?1:0;
  for(let h=start;h<24;h++){
    const v=String(h).padStart(2,"0")+":00";
    const ap=h>=12?"PM":"AM"; let h12=h%12; if(h12===0) h12=12;
    let label=h12+":00 "+ap;
    if(h===0) label="12:00 AM (midnight)"; if(h===12) label="12:00 PM (noon)";
    if(isEnd&&h===23) label="11:00 PM (through midnight)";
    opts+=`<option value="${v}"${v===selVal?' selected':''}>${label}</option>`;
  }
  return `<select class="${cls}">${opts}</select>`;
}
function addDaypartRow(){
  const row=document.createElement("div"); row.className="dpRow";
  row.innerHTML=dpDaySelect("MONDAY")+' <span class="dpsep">to</span> '+dpDaySelect("FRIDAY")+
    ' '+dpHourSelect("dpStart","18:00",false)+' <span class="dpsep">–</span> '+
    dpHourSelect("dpEnd","23:00",true)+' '+
    '<button type="button" class="dpDel" title="Remove window">✕</button>';
  row.querySelector(".dpDel").addEventListener("click",()=>row.remove());
  $("#daypartRows").appendChild(row);
}
$("#addDaypart").addEventListener("click",addDaypartRow);
function dpTo12h(t){
  if(!t) return "";
  let [h,m]=t.split(":").map(Number); const ap=h>=12?"PM":"AM";
  h=h%12; if(h===0) h=12;
  return String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+ap;
}
function collectDayparts(){
  const out=[];
  document.querySelectorAll("#daypartRows .dpRow").forEach(r=>{
    const days=r.querySelectorAll(".dpDay");
    const st=dpTo12h(r.querySelector(".dpStart").value), et=dpTo12h(r.querySelector(".dpEnd").value);
    if(st&&et) out.push({start_day:days[0].value,end_day:days[1].value,start_time:st,end_time:et});
  });
  return out;
}

// Region-aware source lists for the type-to-search pickers.
function sourceList(name){
  if(name==="shows") return APP.shows;
  if(name==="genres") return APP.genres;
  if(name==="my5") return APP.my5SiteGroups||[];
  if(name==="audience") return APP.audienceSegments;
  const rc=$("#region").value;
  if(name==="categories") return (APP.categoriesByRegion||{})[rc]||[];
  if(name==="channels") return (APP.channelsByRegion||{})[rc]||[];
  if(name==="ratings") return (APP.ratingsByRegion||{})[rc]||[];
  if(name==="brands") return (APP.brandsByRegion||{})[rc]||[];
  if(name==="states") return (APP.statesByRegion||{})[rc]||[];
  if(name==="dmas") return (APP.dmasByRegion||{})[rc]||[];
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
  box._render = render;   // exposed so loadPlan() can repopulate this field
  const add=(v,keepOpen)=>{ v=(v||"").trim(); if(!v) return;
    if(box.dataset.numeric && !/^\d+$/.test(v)) return;
    if(src){ const list=sourceList(src)||[];               // strict: must be a real value…
      const hit=list.find(x=>x.toLowerCase()===v.toLowerCase());
      if(hit){ v=hit; } else if(!box.dataset.allowNew){ return; } }  // …unless data-allow-new (create-on-push)
    if(!state.lists[key].includes(v)){
      if(box.dataset.single) state.lists[key]=[];         // single-select: replace
      state.lists[key].push(v); render(); }
    // Multi-select: after clicking a match keep the menu open (the just-added item drops
    // out of the list) so several values can be picked in a row without re-typing.
    if(keepOpen && !box.dataset.single){ input.focus(); showMenu(); } else { input.value=""; closeMenu(); } };
  const closeMenu=()=>{ menu.classList.add("hidden"); menu.innerHTML=""; };
  const showMenu=()=>{
    if(!src){ closeMenu(); return; }
    const q=input.value.trim().toLowerCase();
    const list=sourceList(src)||[];
    if(!list.length){ if(q.length){ menu.innerHTML='<div class="rnote">Pick a Region first</div>'; menu.classList.remove("hidden"); } else closeMenu(); return; }
    // Small enumerated lists (ratings, geo, …) search from the FIRST character so single-
    // char values like the BR "6" rating are findable; big lists need 2 chars to stay useful.
    if(q.length < (list.length<=60 ? 1 : 2)){ closeMenu(); return; }
    // Hide already-selected values so they can't be picked twice.
    const chosen=new Set(state.lists[key].map(x=>x.toLowerCase()));
    const raw=[]; for(let i=0;i<list.length && raw.length<250;i++){
      if(chosen.has(list[i].toLowerCase())) continue;
      if(list[i].toLowerCase().includes(q)) raw.push(list[i]); }
    // Rank: whole-word / start-of-name matches above mid-word substrings ("NCIS"
    // beats "Francisco"), then shorter names first.
    const rank=s=>{ s=s.toLowerCase(); return s.startsWith(q)?0 : (s.includes(" "+q)||s.includes("-"+q)||s.includes(":"+q))?1 : 2; };
    raw.sort((a,b)=>rank(a)-rank(b) || a.length-b.length);
    const hits=raw.slice(0,40);
    if(!hits.length){ menu.innerHTML='<div class="rnote">No match</div>'; menu.classList.remove("hidden"); return; }
    menu.innerHTML=hits.map(h=>`<div class="ritem"></div>`).join("");
    [...menu.children].forEach((el,i)=>{ el.textContent=hits[i]; el.onmousedown=e=>{e.preventDefault(); add(hits[i],true);}; });
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
  // Bulk paste: drop a copied list (one per line, or comma-separated) and auto-add every
  // EXACT match to this field's real FreeWheel options; anything unmatched is reported so
  // the CM can fix spelling or add it manually.
  const matchOne=it=>{ it=(it||"").trim(); if(!it) return {ok:false,v:it};
    if(box.dataset.numeric) return {ok:/^\d+$/.test(it), v:it};
    if(!src) return {ok:true, v:it};                       // free-text field: keep as typed
    const list=sourceList(src)||[]; const hit=list.find(x=>x.toLowerCase()===it.toLowerCase());
    return {ok:!!hit, v:hit||it}; };
  const bulkAdd=text=>{
    const rows=text.split(/[\n\r\t;]+/).map(s=>s.trim()).filter(Boolean);
    const items=[];                                        // expand comma-lists only when the
    rows.forEach(it=>{                                     // whole line isn't itself a value
      if(matchOne(it).ok || !it.includes(",")) items.push(it);
      else it.split(",").forEach(p=>{ if(p.trim()) items.push(p.trim()); }); });
    const added=[], missed=[];
    items.forEach(it=>{ const r=matchOne(it);
      if(r.ok){ if(!state.lists[key].includes(r.v)) state.lists[key].push(r.v); added.push(r.v); }
      else missed.push(it); });
    render(); input.value=""; closeMenu();
    if(added.length||missed.length) alert(added.length+" matched & added"+
      (missed.length ? "\n\n"+missed.length+" NOT found (check spelling or add manually):\n• "+missed.join("\n• ") : " ✅"));
  };
  input.addEventListener("paste",e=>{
    const text=(e.clipboardData||window.clipboardData).getData("text"); if(!text) return;
    if(/[\n\r\t;]/.test(text) || (text.includes(",") && !matchOne(text).ok)){
      e.preventDefault(); bulkAdd(text); }
  });
});
// Region change -> the region-scoped pickers (categories/channels) reset their options.
$("#region").addEventListener("change",()=>{
  ["pluto_categories","pluto_channels","exclude_channels"].forEach(k=>{
    if(state.lists[k]&&state.lists[k].length){ state.lists[k]=[];
      const box=document.querySelector(`[data-chips="${k}"]`);
      if(box) box.querySelectorAll(".chip").forEach(c=>c.remove()); }
  });
});
["title","existing_io_id"].forEach(id=>$("#"+id).addEventListener("input",validate));

// --- Flag showlist shows with no DDA segment yet (heads-up, not a submission) ------- //
// Which affinity shows will need a NEW DDA segment generated, so Tier 1 isn't silently
// empty. Uses the baked-in audience library + the picked region. You still request them
// through the audience form as usual — this just flags the gaps while you plan.
const DDA_CONVENTIONS = {   // region -> accepted DDA name prefixes (normalized tokens)
  USA:["gl dda 1p","us dda 1p"], CA:["gl dda 1p","us dda 1p"], BR:["gl dda 1p","us dda 1p"],
  LATAM:["gl dda 1p","us dda 1p"], AU:["au dwh","apac dda 1p"],
  UK:["gl dda 1p","eu uk dda 1p"], IE:["gl dda 1p","eu uk dda 1p"], FR:["gl dda 1p","eu uk dda 1p"],
  IT:["gl dda 1p","eu uk dda 1p"], GSA:["gl dda 1p","eu uk dda 1p"], ES:["gl dda 1p","eu uk dda 1p"],
  FI:["gl dda 1p","eu uk dda 1p"], DK:["gl dda 1p","eu uk dda 1p"], NO:["gl dda 1p","eu uk dda 1p"],
  SE:["gl dda 1p","eu uk dda 1p"]
};
function ddaToks(s){ return (s||"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim(); }
let _ddaNorm=null;
function ddaFlag(){
  const box=$("#ddaFlag"); if(!box) return;
  const shows=state.lists.showlist||[]; const region=$("#region").value;
  if(!shows.length){ box.classList.add("hidden"); return; }
  const convs=DDA_CONVENTIONS[region]||["gl dda 1p"];
  if(_ddaNorm===null) _ddaNorm=(APP.audienceSegments||[]).map(ddaToks);
  const missing=shows.filter(sh=>{ const kw=ddaToks(sh); if(!kw) return false;
    const has=_ddaNorm.some(n=> convs.some(c=>n.startsWith(c)) &&
      (n===kw || n.endsWith(" "+kw) || n.includes(" "+kw+" ")));
    return !has; });
  if(!missing.length){ box.classList.add("hidden"); return; }
  const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  const many=missing.length>1;
  box.innerHTML="⚠️ <b>"+missing.length+" show"+(many?"s":"")+(many?" don't":" doesn't")+
    " have a DDA segment yet</b> — request "+(many?"these":"this")+
    " through the audience form so Tier 1 can target "+(many?"them":"it")+":<br>• "+
    missing.map(esc).join("<br>• ");
  box.classList.remove("hidden");
}
function validate(){
  ddaFlag();
  const core = $("#region").value && $("#campaign").value && $("#title").value.trim();
  const hasDur = ((state.lists.durations||[]).length)>0;
  // "Add to existing IO" (optional) must be a numeric FreeWheel IO ID when filled — a name
  // there reaches FreeWheel as insertion_order_id and fails ("fail to convert … to Int").
  const ioRaw = ($("#existing_io_id").value||"").trim();
  const ioBad = ioRaw && !/^\d+$/.test(ioRaw);
  const ok = core && hasDur && !ioBad;
  $("#dlBtn").disabled = !ok; $("#rowBtn").disabled = !ok; $("#slackBtn").disabled = !ok;
  // Keep the mirror ("Download mirrored plan(s)") button in sync on EVERY field change,
  // not just on market-chip clicks — enabled once the plan is valid AND a market is ticked.
  const mb=$("#mirrorBtn");
  if(mb) mb.disabled = !(ok && typeof mirrorTargets!=="undefined" && mirrorTargets.size);
  $("#status").textContent = ok
    ? "Ready — click Download & post to Slack (or Copy row for Sheet for a batch)."
    : (ioBad
        ? "‘Add to existing IO’ must be a numeric FreeWheel IO ID (or blank for a new IO)."
        : (core && !hasDur
          ? "Add at least one Video duration (type e.g. 30 and press Enter) to continue."
          : "Fill Region, Campaign, Promoted title and Video durations to continue."));
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
  if($("#existing_io_id").value) plan.existing_io_id=$("#existing_io_id").value.trim();
  plan.content_type=$("#content_type").value;
  if($("#content_id").value) plan.content_id=$("#content_id").value;
  if($("#rec_show_id").value) plan.recommended_show_id=$("#rec_show_id").value;
  if(L.durations.length) plan.durations=L.durations.map(Number);
  const dp=collectDayparts(); if(dp.length) plan.dayparts=dp;
  // Flight dates, with an OPTIONAL specific time-of-day (region's time zone). A time makes it
  // "YYYY-MM-DDTHH:MM"; the builder honors that exact time instead of the default start/end-of-day.
  const fl={};
  if($("#flight_start").value){ const t=$("#flight_start_time").value; fl.start=$("#flight_start").value+(t?("T"+t):""); }
  if($("#flight_end").value){ const t=$("#flight_end_time").value; fl.end=$("#flight_end").value+(t?("T"+t):""); }
  if(Object.keys(fl).length) plan.flight=fl;
  if(Object.keys(po).length) plan.product_overrides=po;
  if(c&&c.kids&&state.kids.size) plan.kids_audience=[...state.kids];
  if($("#scene_lift").value) plan.scene_lift=$("#scene_lift").value;
  if($("#standard").checked) plan.standard=true;
  if($("#video_domination").value) plan.video_domination=$("#video_domination").value;
  if(L.vd_targeting.length) plan.video_domination_targeting=L.vd_targeting;
  if($("#takeover").value) plan.takeover=$("#takeover").value;
  if(L.rating_restrictions.length) plan.rating_restrictions=L.rating_restrictions;
  if(L.rating_inclusions.length) plan.rating_inclusions=L.rating_inclusions;
  if(L.brand_pick && L.brand_pick.length) plan.io_brand=L.brand_pick[0];   // IO Brand (single)
  if(L.geo_states.length) plan.geo_states=L.geo_states;
  if(L.geo_dmas.length) plan.geo_dmas=L.geo_dmas;
  if(L.geo_cities.length) plan.geo_cities=L.geo_cities;
  if(L.geo_states_exclude.length) plan.geo_states_exclude=L.geo_states_exclude;
  if(L.geo_dmas_exclude.length) plan.geo_dmas_exclude=L.geo_dmas_exclude;
  if(L.geo_cities_exclude.length) plan.geo_cities_exclude=L.geo_cities_exclude;
  if(L.genres.length) plan.genres=L.genres;
  if(L.showlist.length) plan.showlist=L.showlist;
  if(L.my5_site_groups&&L.my5_site_groups.length) plan.my5_site_groups=L.my5_site_groups;
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
    case "Existing IO ID": return plan.existing_io_id||"";
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
    case "Standard": return plan.standard?"Y":"";
    case "Rating Restrictions": return list(plan.rating_restrictions);
    case "Rating Includes": case "Rating Inclusions": return list(plan.rating_inclusions);
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

// --- Save progress / reload a plan ---------------------------------------- //
// Everything the CM types is auto-saved to THIS browser (localStorage) so a refresh or
// accidental close doesn't lose the form; and any plan file downloaded earlier can be
// uploaded to keep editing. loadPlan() is the inverse of buildPlan().
const DRAFT_KEY="promoPlanDraft";
function setV(id,v){ const e=$("#"+id); if(e&&v!=null) e.value=v; }
function setChips(key,arr){ state.lists[key]=(arr||[]).slice();
  const box=document.querySelector(`[data-chips="${key}"]`); if(box&&box._render) box._render(); }
function dpTo24h(t){ if(!t) return "";                       // "06:00PM" -> "18:00"
  const ap=t.slice(-2).toUpperCase(); let [h,m]=t.slice(0,-2).split(":").map(Number);
  if(ap==="PM"&&h!==12) h+=12; if(ap==="AM"&&h===12) h=0;
  return String(h).padStart(2,"0")+":"+String(m).padStart(2,"0"); }
function loadDayparts(dps){ $("#daypartRows").innerHTML="";
  (dps||[]).forEach(d=>{ addDaypartRow(); const r=$("#daypartRows").lastElementChild;
    const days=r.querySelectorAll(".dpDay");
    if(d.start_day) days[0].value=d.start_day; if(d.end_day) days[1].value=d.end_day;
    r.querySelector(".dpStart").value=dpTo24h(d.start_time);
    r.querySelector(".dpEnd").value=dpTo24h(d.end_time); }); }
function loadPlan(plan){
  if(!plan||typeof plan!=="object") return;
  // 1) region first (rebuilds the campaign dropdown + clears region-scoped chips)…
  if(plan.region){ $("#region").value=plan.region; $("#region").dispatchEvent(new Event("change")); }
  // 2) …then campaign (renders that campaign's products, kids, nudges)
  const cname=(plan.campaign||{}).name||"";
  if(cname){ $("#campaign").value=cname; $("#campaign").dispatchEvent(new Event("change")); }
  // 3) simple fields
  setV("title",plan.promoted_title); setV("sf_case",plan.salesforce_case);
  setV("language",plan.language); setV("season",plan.season_or_messaging);
  setV("primary_trafficker",plan.primary_trafficker); setV("existing_io_id",plan.existing_io_id);
  setV("content_type",plan.content_type||"show"); setV("content_id",plan.content_id);
  setV("rec_show_id",plan.recommended_show_id); setV("scene_lift",plan.scene_lift);
  setV("video_domination",plan.video_domination); setV("takeover",plan.takeover);
  // Flight start/end may carry an optional time ("YYYY-MM-DDTHH:MM") — split it back into the
  // date + time inputs.
  const _fs=String((plan.flight||{}).start||"").split("T"), _fe=String((plan.flight||{}).end||"").split("T");
  setV("flight_start",_fs[0]); setV("flight_start_time",_fs[1]||"");
  setV("flight_end",_fe[0]); setV("flight_end_time",_fe[1]||"");
  $("#video_domination").dispatchEvent(new Event("change"));
  $("#takeover").dispatchEvent(new Event("change"));
  $("#standard").checked=!!plan.standard;
  // 4) product overrides (segmented Yes/No)
  Object.entries(plan.product_overrides||{}).forEach(([fam,on])=>{
    const p=document.querySelector(`.prod[data-fam="${fam}"]`); if(!p) return;
    const want=on?"yes":"no";
    p.querySelectorAll(".seg button").forEach(x=>x.classList.toggle("on", x.dataset.v===want)); });
  // 5) kids audience
  state.kids=new Set(plan.kids_audience||[]);
  $("#kidsSeg").querySelectorAll("button").forEach(x=>{
    const on=x.dataset.k==="both" ? (state.kids.has("older")&&state.kids.has("younger")) : state.kids.has(x.dataset.k);
    x.classList.toggle("on", on); });
  // 6) chip lists
  setChips("durations",(plan.durations||[]).map(String));
  setChips("vd_targeting",plan.video_domination_targeting);
  setChips("rating_restrictions",plan.rating_restrictions);
  setChips("rating_inclusions",plan.rating_inclusions);
  setChips("genres",plan.genres); setChips("showlist",plan.showlist);
  setChips("my5_site_groups",plan.my5_site_groups);
  setChips("audience_segments",plan.audience_segments);
  setChips("pluto_categories",(plan.pluto||{}).categories);
  setChips("pluto_channels",(plan.pluto||{}).channels);
  setChips("exclude_series",plan.exclude_series);
  setChips("exclude_channels",plan.exclude_channels);
  setChips("exclude_videos",plan.exclude_videos);
  setChips("exclude_audience_segments",plan.exclude_audience_segments);
  // 7) dayparts
  loadDayparts(plan.dayparts);
  validate();
}
// Auto-save the whole form to this browser on any change (debounced).
let _saveT=null;
function saveDraft(){ try{ localStorage.setItem(DRAFT_KEY,
  JSON.stringify({t:Date.now(), plan:buildPlan()})); }catch(e){} }
document.addEventListener("input",()=>{ clearTimeout(_saveT); _saveT=setTimeout(saveDraft,600); });
document.addEventListener("change",()=>{ clearTimeout(_saveT); _saveT=setTimeout(saveDraft,600); });
// Upload a saved plan file to keep editing it.
$("#loadBtn").addEventListener("click",()=>$("#loadFile").click());
$("#loadFile").addEventListener("change",e=>{
  const f=e.target.files&&e.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>{ try{ loadPlan(JSON.parse(rd.result)); saveDraft();
      const b=$("#loadBtn"); b.textContent="Plan loaded ✓"; setTimeout(()=>b.textContent="Load a saved plan",1800); }
    catch(err){ alert("Couldn't read that file — is it a .plan.json downloaded from this form?\n\n"+err); } };
  rd.readAsText(f); $("#loadFile").value="";
});
// On open, offer to restore the last draft saved on this browser.
(function(){ let raw; try{ raw=localStorage.getItem(DRAFT_KEY); }catch(e){ return; }
  if(!raw) return; let d; try{ d=JSON.parse(raw); }catch(e){ return; }
  const p=(d&&d.plan)||{}; const has=p.region||((p.campaign||{}).name)||p.promoted_title;
  if(!has) return;
  const when=d.t?new Date(d.t):null;
  $("#draftMeta").textContent=(p.promoted_title? '"'+p.promoted_title+'" ':"")+
    ((p.campaign||{}).name? "· "+p.campaign.name+" ":"")+
    (when? "· saved "+when.toLocaleString():"");
  $("#draftBanner").classList.remove("hidden");
  $("#draftRestore").addEventListener("click",()=>{ loadPlan(p); $("#draftBanner").classList.add("hidden"); });
  $("#draftDiscard").addEventListener("click",()=>{ try{ localStorage.removeItem(DRAFT_KEY); }catch(e){}
    $("#draftBanner").classList.add("hidden"); });
})();

// --- Brief parser (beta): paste a promo brief, auto-fill the targeting fields -------- //
// Splits the brief on its labels (Networks/Genres/Shows/Pluto Categories/Channels/Audience/
// Ratings), routes each list to the matching field, and matches every term against that
// field's REAL FreeWheel options: exact -> added automatically; close -> suggested to
// confirm; unmatched -> flagged. Rides on sourceList()/state.lists so it inherits the same
// exact-value guarantees as the pickers. No FreeWheel calls — matches the baked-in lists.
const BRIEF_LABELS=[
  {keys:["networks","network","brands","brand"], field:"genres", only:"brand", title:"Networks / Brands"},
  {keys:["genres","genre"], field:"genres", noBrand:true, title:"Genres"},
  {keys:["shows","show","series"], field:"showlist", title:"Shows"},
  {keys:["pluto categories","categories","category"], field:"pluto_categories", title:"Pluto Categories"},
  {keys:["pluto channels","channels","channel"], field:"pluto_channels", title:"Pluto Channels"},
  {keys:["audience","audiences","audience segments","segments"], field:"audience_segments", title:"Audience Segments"},
  {keys:["ratings","rating","rating restrictions","exclude ratings"], field:"rating_restrictions", title:"Ratings to exclude"},
  {keys:["exclude shows","exclude series"], field:"exclude_series", title:"Shows to exclude"},
  {keys:["exclude channels"], field:"exclude_channels", title:"Channels to exclude"},
];
const BRIEF_SRC={genres:"genres", showlist:"shows", pluto_categories:"categories",
  pluto_channels:"channels", audience_segments:"audience", rating_restrictions:"ratings",
  exclude_series:"shows", exclude_channels:"channels"};
// Notes-only labels: informational, surfaced but never auto-filled (mirrors the sibling tool).
const BRIEF_NOTE_KEYS=["video domination","pause ads","flight","dates","kpi","kpis","objective","notes","budget"];
const briefEsc=s=>String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const _briefLc=new Map();                                  // source name -> Map(lowercase->canonical)
function briefSrcMap(src){ if(_briefLc.has(src)) return _briefLc.get(src);
  const mp=new Map(); (sourceList(src)||[]).forEach(x=>{ const k=x.toLowerCase(); if(!mp.has(k)) mp.set(k,x); });
  _briefLc.set(src,mp); return mp; }
function briefOptOK(def,x){ const s=x.toLowerCase();
  if(def.only==="brand") return s.startsWith("brand:");
  if(def.noBrand && s.startsWith("brand:")) return false;
  return true; }
function parseBrief(text){
  // Strip a leading "Pluto TV:" / "Pluto:" so its sub-labels (Categories:/Channels:) read
  // as first-class labels, then find every "<label>:" at a line start or after ";".
  let t="\n"+String(text).replace(/\r/g,"").replace(/pluto tv\s*:/gi,"").replace(/pluto\s*:/gi,"");
  const alias=[]; BRIEF_LABELS.forEach(l=>l.keys.forEach(k=>alias.push(k)));
  const kw=alias.concat(BRIEF_NOTE_KEYS).sort((a,b)=>b.length-a.length).join("|");
  const re=new RegExp("(?:^|\\n|;)[ \\t]*("+kw+")[ \\t]*:","gi");
  const hits=[]; let m;
  while((m=re.exec(t))!==null) hits.push({label:m[1].toLowerCase().trim(), at:re.lastIndex, start:m.index});
  const sections=[], notes=[];
  for(let i=0;i<hits.length;i++){
    const end = i+1<hits.length ? hits[i+1].start : t.length;
    const payload=t.slice(hits[i].at, end).trim();
    const def=BRIEF_LABELS.find(l=>l.keys.indexOf(hits[i].label)>=0);
    if(!def){ if(payload) notes.push({label:hits[i].label, payload}); continue; }
    const terms=payload.split(/[\n,;\t]+/).map(s=>s.trim()).filter(Boolean);
    if(terms.length) sections.push({def, terms});
  }
  return {sections, notes};
}
function briefMatch(def, term){
  const src=BRIEF_SRC[def.field], list=sourceList(src)||[], t=term.toLowerCase();
  const hit=briefSrcMap(src).get(t);
  if(hit && briefOptOK(def,hit)) return {status:"exact", value:hit};
  const cands=[];
  for(let i=0;i<list.length && cands.length<50;i++){ const x=list[i]; if(!briefOptOK(def,x)) continue;
    const s=x.toLowerCase();
    if(s.indexOf(t)>=0 || s.split(/[^a-z0-9]+/).indexOf(t)>=0) cands.push(x); }
  cands.sort((a,b)=>a.length-b.length);
  if(cands.length) return {status:"fuzzy", options:cands.slice(0,6)};
  return {status:"none"};
}
function briefAddToField(key, vals){ const cur=state.lists[key]||(state.lists[key]=[]);
  vals.forEach(v=>{ if(cur.indexOf(v)<0) cur.push(v); });
  const box=document.querySelector('[data-chips="'+key+'"]'); if(box&&box._render) box._render(); }
function renderBriefReport(groups, notes, R){
  R = R || $("#briefReport"); R.innerHTML="";
  if(!groups.length && !notes.length){
    R.innerHTML='<p class="hint">No recognizable labels found. Start lines with Networks:, Genres:, Shows:, Pluto Categories:, Pluto Channels:, Audience:, or Ratings:.</p>'; return; }
  groups.forEach(g=>{
    const box=document.createElement("div");
    box.style.cssText="margin:0 0 12px;padding:10px 12px;border:1px solid var(--line);border-radius:10px";
    const h=document.createElement("div"); h.style.cssText="font-weight:700;margin-bottom:6px"; h.textContent=g.def.title; box.appendChild(h);
    if(g.added.length){ const d=document.createElement("div"); d.style.cssText="font-size:13px;margin:2px 0";
      d.innerHTML='<span style="color:#137333">✅ Added '+g.added.length+':</span> '+briefEsc(g.added.join(", ")); box.appendChild(d); }
    g.review.forEach(rv=>{ const d=document.createElement("div"); d.style.cssText="font-size:13px;margin:4px 0";
      d.innerHTML='<span style="color:#b06000">🟡 “'+briefEsc(rv.term)+'” — did you mean:</span> ';
      rv.options.forEach(opt=>{ const b=document.createElement("button"); b.type="button"; b.className="btn ghost";
        b.style.cssText="padding:3px 9px;font-size:12px;margin:2px 4px 2px 0"; b.textContent=opt;
        b.onclick=()=>{ briefAddToField(g.def.field,[opt]); b.textContent="✓ "+opt; b.disabled=true; };
        d.appendChild(b); }); box.appendChild(d); });
    if(g.none.length){ const d=document.createElement("div"); d.style.cssText="font-size:13px;margin:2px 0;color:#a00";
      d.textContent="❌ Not found: "+g.none.join(", "); box.appendChild(d); }
    R.appendChild(box);
  });
  if(notes.length){ const d=document.createElement("div"); d.style.cssText="font-size:13px;margin-top:6px;color:#555";
    d.innerHTML="📝 <b>Notes (not auto-filled):</b> "+notes.map(n=>briefEsc(n.label)+": "+briefEsc(n.payload)).join(" · "); R.appendChild(d); }
}
function runBrief(){
  _briefLc.clear();                                        // region may have changed -> rebuild exact maps
  const text=$("#briefText").value||"";
  if(!text.trim()){ $("#briefHint").textContent="Paste a brief first."; $("#briefReport").innerHTML=""; return; }
  $("#briefHint").textContent = (!$("#region").value || !$("#campaign").value)
    ? "Tip: pick a Region + Campaign first — channels, categories and ratings are region-specific."
    : "";
  const {sections, notes}=parseBrief(text);
  const groups=[];
  sections.forEach(sec=>{
    const added=[], review=[], none=[];
    sec.terms.forEach(term=>{ const r=briefMatch(sec.def, term);
      if(r.status==="exact"){ if(added.indexOf(r.value)<0) added.push(r.value); }
      else if(r.status==="fuzzy") review.push({term, options:r.options});
      else none.push(term); });
    if(added.length) briefAddToField(sec.def.field, added);
    groups.push({def:sec.def, added, review, none});
  });
  renderBriefReport(groups, notes);
}
$("#briefParse").addEventListener("click", runBrief);
$("#briefClear").addEventListener("click",()=>{ $("#briefText").value=""; $("#briefReport").innerHTML=""; $("#briefHint").textContent=""; });

// --- ✨ Suggest targeting (AI, via the local helper server) --------------------------- //
// POSTs {title, description, region} to /suggest (same-origin when the form is opened through
// `python -m promo_ops.suggest_server`), then fills the fields with the grounded matches and
// shows the review/not-found report. Never holds a key in the browser — the helper does.
const SUGGEST_TITLES={genres:"Genres", showlist:"Shows (→ Tier 2 + Tier 1 audience segments)",
  pluto_categories:"Pluto Categories", pluto_channels:"Pluto Channels"};
function suggestOfflineMsg(){
  return "This button needs the helper. Run <code>PYTHONPATH=src python3 -m promo_ops.suggest_server</code> "
    + "and open the form at the URL it prints (e.g. <b>http://127.0.0.1:8770/</b>) — not the .html file directly. "
    + "It works with no API key (historicals-only); set ANTHROPIC_API_KEY to add the AI layer.";
}
async function runSuggest(){
  const title=($("#suggestTitle").value||($("#title")?$("#title").value:"")||"").trim();
  const desc=($("#suggestDesc").value||"").trim();
  const brief=($("#suggestBrief")?$("#suggestBrief").value:"").trim();
  const region=$("#region").value;
  const H=$("#suggestHint"), R=$("#suggestReport");
  if(!title){ H.textContent="Enter a title (a description or pasted brief helps, but isn't required)."; return; }
  if(!region){ H.textContent="Pick a Region below first — channels & categories are region-specific."; return; }
  if($("#title")&&!$("#title").value){ $("#title").value=title; validate(); }   // seed the plan title
  H.textContent=""; R.innerHTML='<span class="hint">✨ Thinking — layering brief, AI &amp; historicals, grounding to real inventory…</span>';
  let res;
  try{
    res=await fetch("/suggest",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title,description:desc,brief_text:brief,region})});
  }catch(e){ R.innerHTML='<span style="color:#a00">Couldn\'t reach the helper.</span><br>'+suggestOfflineMsg(); return; }
  if(!res.ok){ let j={}; try{ j=await res.json(); }catch(_){}
    R.innerHTML='<span style="color:#a00">'+briefEsc(j.error||("Error "+res.status))+'</span>'
      + (res.status===503 ? "<br>"+suggestOfflineMsg() : ""); return; }
  const data=await res.json();
  const groups=Object.keys(SUGGEST_TITLES).filter(f=>data.fields&&data.fields[f]).map(f=>{
    const fp=data.fields[f]; briefAddToField(f, fp.matched||[]);
    return {def:{field:f,title:SUGGEST_TITLES[f]}, added:fp.matched||[], review:fp.review||[], none:fp.missed||[]};
  });
  const notes=(data.notes||[]).map(n=>({label:"note",payload:n}));
  renderBriefReport(groups, notes, R);
}
$("#suggestBtn").addEventListener("click", runSuggest);

validate();
</script>
</body></html>
"""


if __name__ == "__main__":
    print(f"Wrote {build()}")
