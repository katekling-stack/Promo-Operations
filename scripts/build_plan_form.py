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
        campaigns.append({"name": cname, "region": _region_of(cname),
                          "brand": b.get("display_name", key), "kids": bool(b.get("kids")),
                          "products": prods})
    campaigns.sort(key=lambda c: (REGION_ORDER.index(c["region"]) if c["region"] in REGION_ORDER else 99, c["name"]))
    vd = [{"key": k, "label": v.get("label", k)}
          for k, v in _yaml("video_dominations.yaml").get("options", {}).items()]
    tk = [{"key": k, "label": v.get("label", k)}
          for k, v in _yaml("operative_takeovers.yaml").get("types", {}).items()]
    return {
        "regions": [{"code": c, "name": REGION_NAME.get(c, c)} for c in REGION_ORDER],
        "campaigns": campaigns, "productLabels": PRODUCT_LABEL,
        "videoDominations": vd, "takeovers": tk, "genres": GENRES, "categories": CATEGORIES,
    }


def build(out: Path | None = None) -> Path:
    html = TEMPLATE.replace("/*APP_DATA*/", json.dumps(app_data(), ensure_ascii=False))
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
.wrap{max-width:760px;margin:0 auto;padding:0 18px 120px}
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
 padding:8px;min-height:46px;background:#fff}
.chips.focus{border-color:var(--blue);box-shadow:0 0 0 4px var(--focus)}
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
.barw{max-width:760px;margin:0 auto;display:flex;align-items:center;gap:12px}
.btn{border:0;border-radius:11px;padding:12px 18px;font-size:14.5px;font-weight:700;cursor:pointer}
.btn.primary{background:var(--blue);color:#fff}
.btn.ghost{background:#eef2f9;color:var(--navy)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.status{color:var(--muted);font-size:12.5px;flex:1}
.toggle-adv{color:var(--blue);font-size:12.5px;font-weight:600;cursor:pointer;user-select:none}
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
      <div id="brandChip"></div></div>
  </div>

  <div class="card">
    <h2>Creative & naming</h2><p class="sub">What's being promoted.</p>
    <div class="field"><label>Promoted title <span class="req">*</span></label>
      <input type="text" id="title" placeholder="e.g. Frisco King"></div>
    <div class="row">
      <div class="field"><label>Season or messaging</label>
        <input type="text" id="season" placeholder="e.g. Season 1 / Now Streaming"></div>
      <div class="field"><label>Content type</label>
        <select id="content_type"><option value="show">Show</option><option value="movie">Movie</option></select></div>
    </div>
    <div class="row">
      <div class="field"><label>Content ID (ShowID / MovieID)</label><input type="text" id="content_id"></div>
      <div class="field"><label>Recommended Show ID</label><input type="text" id="rec_show_id"></div>
    </div>
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
      <div class="field"><label>Flight code</label><input type="text" id="flight_code" placeholder="e.g. L1"></div>
      <div class="field"><label>Video durations (seconds)</label>
        <div class="chips" data-chips="durations" data-numeric="1"><input type="text" placeholder="30, 15…  ↵"></div>
        <div class="hint">Type a number and press Enter. Common: 30, 15, 60.</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Products</h2><p class="sub">Leave on <b>Default</b> to keep the brand's standard set. Only the products this campaign can run are shown.</p>
    <div id="products"></div>
  </div>

  <div class="card" id="addonsCard">
    <h2>Add-ons</h2><p class="sub">Optional Video Domination + takeover.</p>
    <div class="row">
      <div class="field"><label>Video Domination</label><select id="video_domination"></select></div>
      <div class="field"><label>Takeover</label><select id="takeover"></select></div>
    </div>
    <div class="field hidden" id="vdTargetWrap"><label>Video Domination targeting (Pluto categories)</label>
      <div class="chips" data-chips="vd_targeting" data-suggest="categories"><input type="text" placeholder="Comedy, Crime…  ↵"></div></div>
    <div class="field hidden" id="ratingWrap"><label>Rating restrictions (AU Network 10)</label>
      <div class="chips" data-chips="rating_restrictions"><input type="text" placeholder="VG value  ↵"></div></div>
  </div>

  <div class="card">
    <h2>Targeting</h2><p class="sub">List everything to target — type a value and press Enter to add it. Audience Segments (Tier 1) auto-resolve from the Showlist; leave blank.</p>
    <div class="field"><label>Showlist</label><div class="chips" data-chips="showlist"><input type="text" placeholder="e.g. NCIS  ↵"></div></div>
    <div class="field"><label>Genres</label><div class="chips" data-chips="genres" data-suggest="genres"><input type="text" placeholder="e.g. Drama  ↵"></div></div>
    <div class="field"><label>Networks</label><div class="chips" data-chips="networks"><input type="text" placeholder="e.g. Paramount Network  ↵"></div></div>
    <div class="field"><label>Pluto categories</label><div class="chips" data-chips="pluto_categories" data-suggest="categories"><input type="text" placeholder="use your region's names  ↵"></div>
      <div class="hint">Category / channel names differ by region — use your region's real names.</div></div>
    <div class="field"><label>Pluto channels</label><div class="chips" data-chips="pluto_channels"><input type="text" placeholder="e.g. Westerns  ↵"></div></div>
    <div class="field"><span class="toggle-adv" id="advToggle">▸ Tier-1 audience segments (advanced)</span>
      <div class="chips hidden" data-chips="audience_segments" style="margin-top:8px"><input type="text" placeholder="usually blank — auto-resolved  ↵"></div></div>
  </div>
</div>

<div class="bar"><div class="barw">
  <span class="status" id="status">Fill Region, Campaign and Promoted title to continue.</span>
  <button class="btn ghost" id="copyBtn">Copy JSON</button>
  <button class="btn primary" id="dlBtn" disabled>Download plan file</button>
</div></div>

<datalist id="dl-genres"></datalist>
<datalist id="dl-categories"></datalist>

<script>
const APP = /*APP_DATA*/;
const $ = s => document.querySelector(s);
const state = {kids:new Set(), lists:{}};

// datalists
for(const [id,arr] of [["dl-genres",APP.genres],["dl-categories",APP.categories]]){
  $("#"+id).innerHTML = arr.map(v=>`<option value="${v}">`).join("");
}
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
  $("#products").innerHTML = prods.length ? prods.map(p=>prodRow(p)).join("")
     : '<p class="hint">Pick a campaign to see its products.</p>';
  bindProducts();
  const isAU = c && c.region==="AU";
  $("#ratingWrap").classList.toggle("hidden", !(c && c.products.includes("network_10")));
  validate();
}
function prodRow(fam){
  return `<div class="prod" data-fam="${fam}"><div class="pl">${APP.productLabels[fam]||fam}</div>
    <div class="seg">
      <button type="button" data-v="" class="on">Default</button>
      <button type="button" data-v="yes">Yes</button>
      <button type="button" data-v="no">No</button></div></div>`;
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
// advanced toggle
$("#advToggle").addEventListener("click",()=>{
  const box=document.querySelector('[data-chips="audience_segments"]');
  box.classList.toggle("hidden");
  $("#advToggle").textContent = (box.classList.contains("hidden")?"▸":"▾")+" Tier-1 audience segments (advanced)";
});

// chips inputs
document.querySelectorAll(".chips").forEach(box=>{
  const key=box.dataset.chips; state.lists[key]=[];
  const input=box.querySelector("input");
  if(box.dataset.suggest) input.setAttribute("list","dl-"+box.dataset.suggest);
  const add=v=>{ v=(v||"").trim(); if(!v) return;
    if(box.dataset.numeric && !/^\d+$/.test(v)) return;
    if(!state.lists[key].includes(v)){ state.lists[key].push(v); render(); } input.value=""; };
  const render=()=>{
    box.querySelectorAll(".chip").forEach(c=>c.remove());
    state.lists[key].forEach((v,i)=>{
      const el=document.createElement("span"); el.className="chip";
      el.innerHTML=`<b>${v}</b>`; const x=document.createElement("button"); x.textContent="×";
      x.onclick=()=>{ state.lists[key].splice(i,1); render(); };
      el.appendChild(x); box.insertBefore(el,input);
    }); validate();
  };
  input.addEventListener("keydown",e=>{
    if(e.key==="Enter"||e.key===","){ e.preventDefault(); add(input.value); }
    else if(e.key==="Backspace"&&!input.value&&state.lists[key].length){ state.lists[key].pop(); render(); }
  });
  input.addEventListener("blur",()=>add(input.value));
  box.addEventListener("click",()=>input.focus());
  input.addEventListener("focus",()=>box.classList.add("focus"));
  input.addEventListener("blur",()=>box.classList.remove("focus"));
});
["title"].forEach(id=>$("#"+id).addEventListener("input",validate));

function validate(){
  const ok = $("#region").value && $("#campaign").value && $("#title").value.trim();
  $("#dlBtn").disabled = !ok;
  $("#status").textContent = ok ? "Ready — download the plan file and hand it to Ad Ops."
    : "Fill Region, Campaign and Promoted title to continue.";
  return ok;
}

function buildPlan(){
  const c = currentCampaign();
  const po={}; document.querySelectorAll(".prod").forEach(p=>{
    const v=p.querySelector(".seg button.on").dataset.v;
    if(v==="yes") po[p.dataset.fam]=true; else if(v==="no") po[p.dataset.fam]=false; });
  const L=state.lists; const plan={
    promoted_title:$("#title").value.trim(), region:$("#region").value,
    campaign:{name:$("#campaign").value},
  };
  if($("#language").value) plan.language=$("#language").value;
  if($("#season").value) plan.season_or_messaging=$("#season").value;
  plan.content_type=$("#content_type").value;
  if($("#content_id").value) plan.content_id=$("#content_id").value;
  if($("#rec_show_id").value) plan.recommended_show_id=$("#rec_show_id").value;
  if(L.durations.length) plan.durations=L.durations.map(Number);
  const fl={}; if($("#flight_start").value)fl.start=$("#flight_start").value;
  if($("#flight_end").value)fl.end=$("#flight_end").value; if($("#flight_code").value)fl.code=$("#flight_code").value;
  if(Object.keys(fl).length) plan.flight=fl;
  if(Object.keys(po).length) plan.product_overrides=po;
  if(c&&c.kids&&state.kids.size) plan.kids_audience=[...state.kids];
  if($("#video_domination").value) plan.video_domination=$("#video_domination").value;
  if(L.vd_targeting.length) plan.video_domination_targeting=L.vd_targeting;
  if($("#takeover").value) plan.takeover=$("#takeover").value;
  if(L.rating_restrictions.length) plan.rating_restrictions=L.rating_restrictions;
  if(L.networks.length) plan.networks=L.networks;
  if(L.genres.length) plan.genres=L.genres;
  if(L.showlist.length) plan.showlist=L.showlist;
  if(L.audience_segments.length) plan.audience_segments=L.audience_segments;
  const pl={}; if(L.pluto_categories.length)pl.categories=L.pluto_categories;
  if(L.pluto_channels.length)pl.channels=L.pluto_channels; if(Object.keys(pl).length)plan.pluto=pl;
  return plan;
}
function fname(){ const p=buildPlan();
  return (p.promoted_title+"-"+p.region).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")+".plan.json"; }
$("#dlBtn").addEventListener("click",()=>{
  if(!validate())return; const blob=new Blob([JSON.stringify(buildPlan(),null,2)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=fname(); a.click();
});
$("#copyBtn").addEventListener("click",async()=>{
  await navigator.clipboard.writeText(JSON.stringify(buildPlan(),null,2));
  $("#copyBtn").textContent="Copied ✓"; setTimeout(()=>$("#copyBtn").textContent="Copy JSON",1400);
});
validate();
</script>
</body></html>
"""


if __name__ == "__main__":
    print(f"Wrote {build()}")
