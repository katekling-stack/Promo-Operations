"""Build a standalone, searchable **Targeting Catalog** page for the team — a browse-all
reference of every targeting option the plan form offers, generated from the SAME synced
FreeWheel snapshots that back the form's pickers (so the catalog == what's actually
selectable). Complements the ✨ Suggest button: Suggest recommends options for one title;
this lets the team browse the whole vocabulary when they don't know all their options.

Sections: Genres · Sub-genres · Franchises · Brand VGs · Dayparts · Pluto Channels (by
region) · Pluto Categories (by region) · DDA Audience Segments · Shows/Series. Instant
search, per-section counts, region filter for the region-specific sets, and click-to-copy
so a value drops straight into the form's chip fields.

Run: python scripts/build_targeting_catalog.py   (refresh after sync-* to stay current)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_targeting_options as opts   # reuse the exact form-picker aggregation  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "templates" / "targeting-options" / "targeting-catalog.html"
SHOW_CAP = 15000   # ~230k series is a search-as-you-type universe, not a browse list


def catalog_data() -> dict:
    buckets: dict[str, list] = {"Genre": [], "Sub-genre": [], "Franchise": [],
                                "Brand": [], "Daypart": []}
    for value, typ in opts.genres():
        if typ == "Genre" and value.startswith("Sub: "):
            buckets["Sub-genre"].append(value)
        elif typ == "Genre":
            buckets["Genre"].append(value)
        elif typ in buckets:
            buckets[typ].append(value)

    pluto = opts._pluto()
    pluto_regions = opts._pluto_regions()
    active = {r: m for r, m in opts.REGION_TO_PLUTO_MARKETS.items() if r in pluto_regions}
    channels_by_region, categories_by_region = {}, {}
    for region, markets in active.items():
        channels_by_region[region] = sorted({v for m in markets
                                             for v in pluto.get(m, {}).get("channels", [])})
        categories_by_region[region] = sorted({v for m in markets
                                               for v in pluto.get(m, {}).get("categories", [])})

    audience = [{"name": n, "structure": s} for n, s in opts.audience_segments()]
    sh = opts.shows()   # (series_id, name)
    shows = [{"id": sid, "name": name} for sid, name in sh[:SHOW_CAP]]

    return {
        "genres": buckets["Genre"], "subgenres": buckets["Sub-genre"],
        "franchises": buckets["Franchise"], "brands": buckets["Brand"],
        "dayparts": buckets["Daypart"],
        "channels_by_region": channels_by_region,
        "categories_by_region": categories_by_region,
        "audience": audience,
        "shows": shows, "shows_total": len(sh), "shows_capped": len(sh) > SHOW_CAP,
    }


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Targeting Catalog — Promo Ops</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--line:#e4e7eb;--ink:#1c2430;--muted:#6b7580;--blue:#2f6fed;--chip:#eef2f8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{background:var(--card);border-bottom:1px solid var(--line);padding:16px 22px;position:sticky;top:0;z-index:5}
h1{margin:0;font-size:19px}
.sub{color:var(--muted);font-size:13px;margin:4px 0 0}
.wrap{display:flex;gap:18px;padding:18px 22px;align-items:flex-start}
.side{width:220px;flex:0 0 220px;position:sticky;top:92px}
.tab{display:flex;justify-content:space-between;gap:8px;padding:9px 12px;border-radius:9px;cursor:pointer;color:var(--ink)}
.tab:hover{background:#eef1f5}
.tab.on{background:var(--blue);color:#fff}
.tab .n{opacity:.75;font-variant-numeric:tabular-nums;font-size:12.5px}
.main{flex:1;min-width:0}
.controls{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
input,select{font:inherit;padding:9px 11px;border:1.5px solid var(--line);border-radius:10px;background:#fff}
#q{flex:1;min-width:220px}
.count{color:var(--muted);font-size:12.5px}
.grid{display:flex;flex-wrap:wrap;gap:8px}
.item{display:inline-flex;align-items:center;gap:8px;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer;max-width:100%}
.item:hover{border-color:var(--blue);background:#e7eefc}
.item .t{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .sub2{color:var(--muted);font-size:11.5px}
.item.copied{background:#e6f4ea;border-color:#3aa76d}
.hint{color:var(--muted);font-size:12.5px;margin:8px 0}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1c2430;color:#fff;padding:9px 16px;border-radius:10px;opacity:0;transition:opacity .15s;pointer-events:none}
.toast.show{opacity:1}
</style></head><body>
<header>
  <h1>🎯 Targeting Catalog</h1>
  <p class="sub">Everything you can target in the plan form, generated from the live FreeWheel-synced data. Type to search; click any value to copy it, then paste into the form's chip fields.</p>
</header>
<div class="wrap">
  <div class="side" id="tabs"></div>
  <div class="main">
    <div class="controls">
      <input id="q" placeholder="Search this section…" autocomplete="off">
      <select id="region" class="hidden" style="display:none"></select>
      <span class="count" id="count"></span>
    </div>
    <div class="hint" id="sectionHint"></div>
    <div class="grid" id="grid"></div>
  </div>
</div>
<div class="toast" id="toast">Copied</div>
<script>
const DATA = __DATA__;
const $=s=>document.querySelector(s);
const REGIONS = Object.keys(DATA.channels_by_region).sort();
// Section registry: how each tab pulls + renders its items.
const SECTIONS = [
  {key:"genres", label:"Genres", items:()=>DATA.genres.map(v=>({t:v}))},
  {key:"subgenres", label:"Sub-genres", items:()=>DATA.subgenres.map(v=>({t:v}))},
  {key:"franchises", label:"Franchises", items:()=>DATA.franchises.map(v=>({t:v}))},
  {key:"brands", label:"Brand VGs", items:()=>DATA.brands.map(v=>({t:v}))},
  {key:"dayparts", label:"Dayparts", items:()=>DATA.dayparts.map(v=>({t:v}))},
  {key:"channels", label:"Pluto Channels", region:true,
     items:r=>(DATA.channels_by_region[r]||[]).map(v=>({t:v}))},
  {key:"categories", label:"Pluto Categories", region:true,
     items:r=>(DATA.categories_by_region[r]||[]).map(v=>({t:v}))},
  {key:"audience", label:"DDA Audience Segments",
     items:()=>DATA.audience.map(a=>({t:a.name, sub:a.structure}))},
  {key:"shows", label:"Shows / Series",
     items:()=>DATA.shows.map(s=>({t:s.name, sub:"id "+s.id}))},
];
let active = SECTIONS[0];

function count(sec){
  if(sec.region) return REGIONS.reduce((n,r)=>n+sec.items(r).length,0);
  return sec.items().length;
}
function renderTabs(){
  $("#tabs").innerHTML = SECTIONS.map(s=>{
    let n = s.key==="shows" && DATA.shows_capped ? DATA.shows_total.toLocaleString()+"+" : count(s).toLocaleString();
    return `<div class="tab ${s===active?'on':''}" data-k="${s.key}"><span>${s.label}</span><span class="n">${n}</span></div>`;
  }).join("");
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{ active=SECTIONS.find(s=>s.key===t.dataset.k); $("#q").value=""; render(); });
}
function esc(s){ return s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function copy(txt, el){
  navigator.clipboard && navigator.clipboard.writeText(txt);
  el.classList.add("copied"); setTimeout(()=>el.classList.remove("copied"),600);
  const t=$("#toast"); t.textContent="Copied  "+txt.slice(0,60); t.classList.add("show");
  clearTimeout(window._tt); window._tt=setTimeout(()=>t.classList.remove("show"),900);
}
function render(){
  renderTabs();
  const rSel=$("#region");
  if(active.region){ rSel.style.display="";
    if(rSel.dataset.built!=="1"){ rSel.innerHTML=REGIONS.map(r=>`<option>${r}</option>`).join(""); rSel.dataset.built="1"; }
  } else rSel.style.display="none";
  const q=($("#q").value||"").trim().toLowerCase();
  let items = active.region ? active.items(rSel.value||REGIONS[0]) : active.items();
  const total = items.length;
  if(q) items = items.filter(i=>i.t.toLowerCase().includes(q) || (i.sub&&i.sub.toLowerCase().includes(q)));
  $("#count").textContent = (q? items.length+" of "+total : total.toLocaleString()) + " item(s)";
  let hint="";
  if(active.key==="shows" && DATA.shows_capped) hint=`Showing the first ${DATA.shows.length.toLocaleString()} of ${DATA.shows_total.toLocaleString()} series — search to find any specific title (the form's Showlist is search-as-you-type over the full set).`;
  else if(active.key==="shows" && DATA.shows_total===0) hint="No series synced yet — run promo-ops sync-series to populate this section.";
  else if(active.region) hint="Region-specific — switch region to see that market's list.";
  $("#sectionHint").textContent=hint;
  const CAP=2000;
  const shown = items.slice(0,CAP);
  $("#grid").innerHTML = shown.map(i=>
    `<span class="item" data-v="${esc(i.t)}"><span class="t">${esc(i.t)}</span>${i.sub?`<span class="sub2">${esc(i.sub)}</span>`:""}</span>`).join("")
    || '<span class="hint">No matches.</span>';
  if(items.length>CAP) $("#grid").insertAdjacentHTML("beforeend", `<span class="hint">+${(items.length-CAP).toLocaleString()} more — narrow your search.</span>`);
  document.querySelectorAll(".item").forEach(el=>el.onclick=()=>copy(el.dataset.v, el));
}
$("#q").addEventListener("input", render);
$("#region").addEventListener("change", render);
render();
</script></body></html>
"""


def build() -> str:
    data = catalog_data()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    return (f"{OUT.relative_to(REPO)}  "
            f"(genres {len(data['genres'])}, sub {len(data['subgenres'])}, "
            f"franchises {len(data['franchises'])}, brands {len(data['brands'])}, "
            f"dayparts {len(data['dayparts'])}, audience {len(data['audience'])}, "
            f"shows {data['shows_total']})")


if __name__ == "__main__":
    print("Wrote " + build())
