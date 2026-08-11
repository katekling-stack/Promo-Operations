"""Generate an interactive, self-contained HTML CREATIVE TRAFFICKING form.

Mirrors the existing PTS ("Promo Trafficking Sheet") Excel workbook — one section
per product (Video / Pause Ads / Display / Audio / HPTO / Video Domination) — as a
governed, templatized intake form: open `creative-trafficking-form.html` in any
browser (no server, no login), add creative lines per product with the same
Marketing-owned vs. Promo-owned field split as the original workbook, and click
"Download plan file" to get a JSON.

New vs. the original workbook: every creative line gets a **Net New Creative**
indicator (New / Reused – Prior Flight / Refresh of Existing) plus an optional
Prior Creative Reference, so Promo Ops can see at a glance what actually needs to
be trafficked fresh vs. re-pointed at an existing asset for the next flight.

This is the near-term mockup (Case core fields stay as-is; this becomes a required
attachment on the Case, downloaded and parsed the same way the Targeting sheet is
today — see `SalesforceClient._targeting_rows` in `integrations/salesforce.py`).
The longer-term option — a `Creative_Asset__c` child object per line, enforced by a
validation rule/Flow — is a separate decision once the creative-automation team
weighs in.

The Campaign dropdown is baked in from the live `config/brands.yaml`, so it can't
drift from the real campaign list. Run:  python scripts/build_creative_trafficking_form.py
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config"
OUT = REPO / "templates" / "creative-trafficking" / "creative-trafficking-form.html"

REGION_ORDER = ["USA", "CA", "UK", "IE", "AU", "LATAM", "BR", "FR", "IT", "GSA",
                "FI", "DK", "NO", "SE", "ES"]


def _yaml(name):
    return yaml.safe_load((CONFIG / name).read_text()) or {}


def _region_of(cname: str) -> str:
    for code in REGION_ORDER:
        if cname.endswith(f"- {code}") or cname.endswith(code):
            return code
    return "?"


def campaigns() -> list[dict]:
    brands = _yaml("brands.yaml").get("brands", {})
    seen, out = set(), []
    for b in brands.values():
        cname = b.get("campaign_name")
        if not cname or cname in seen:
            continue
        seen.add(cname)
        out.append({"name": cname, "region": _region_of(cname)})
    out.sort(key=lambda c: (REGION_ORDER.index(c["region"]) if c["region"] in REGION_ORDER else 99, c["name"]))
    return out


# --------------------------------------------------------------------------- #
# One entry per PTS tab. `fields` order matches the original workbook column
# order; `owner` mirrors the workbook's "Marketing Team Input" / "Promo Team
# Input" split. Promo-owned fields render read-only in the intake form — Promo
# Ops fills those in after the creative lines come in — but stay in the JSON
# schema (blank) so nothing downstream has to special-case a missing key.
# --------------------------------------------------------------------------- #
TABS = [
    dict(key="video", label="Video", fields=[
        dict(key="messaging", label="Messaging / Beat / Phase", owner="marketing", type="text"),
        dict(key="flight_start", label="Flight Start", owner="marketing", type="date"),
        dict(key="flight_end", label="Flight End", owner="marketing", type="date"),
        dict(key="freewheel_order_link", label="FreeWheel Order Link", owner="promo", type="text"),
        dict(key="duration", label="Duration (seconds)", owner="marketing", type="text", placeholder="e.g. 30"),
        dict(key="creative_link", label="Creative Files - Links", owner="marketing", type="url"),
        dict(key="exported_creative_name", label="Exported - Creative Name", owner="promo", type="text"),
        dict(key="click_through_url", label="Click-Through URL", owner="marketing", type="url"),
        dict(key="tracking_pixel", label="1x1 / Tracking Pixel", owner="promo", type="text"),
        dict(key="targeting_requests", label="Targeting Requests", owner="marketing", type="text"),
        dict(key="premium_preroll", label="Premium Pre-Roll", owner="promo", type="select",
             options=["", "CBS News", "Soccer Live", "Sports HQ", "MTVE TVE"]),
        dict(key="essential_bumper", label="Essential Bumper", owner="promo", type="select",
             options=["", "Yes", "No"]),
        dict(key="dedicated_promos", label="Dedicated Promos", owner="promo", type="text"),
        dict(key="pitch_for_stb", label="Pitch for STB", owner="promo", type="text"),
    ]),
    dict(key="pause_ads", label="Pause Ads", fields=[
        dict(key="messaging", label="Messaging / Beat / Phase", owner="marketing", type="text"),
        dict(key="flight_start", label="Flight Start", owner="marketing", type="date"),
        dict(key="flight_end", label="Flight End", owner="marketing", type="date"),
        dict(key="freewheel_order_link", label="FreeWheel Order Link", owner="promo", type="text"),
        dict(key="platform", label="Platform", owner="marketing", type="select",
             options=["", "CTV", "Desktop"]),
        dict(key="creative_link", label="Creative Files - Links", owner="marketing", type="url"),
        dict(key="creative_name", label="Creative Name", owner="marketing", type="text"),
        dict(key="click_through_url", label="Click-Through URL", owner="marketing", type="url"),
        dict(key="tracking_pixel", label="1x1 / Tracking Pixel", owner="promo", type="text"),
        dict(key="targeting_requests", label="Targeting Requests", owner="marketing", type="text"),
    ]),
    dict(key="display", label="Display", fields=[
        dict(key="messaging", label="Messaging / Beat / Phase", owner="marketing", type="text"),
        dict(key="flight_start", label="Flight Start", owner="marketing", type="date"),
        dict(key="flight_end", label="Flight End", owner="marketing", type="date"),
        dict(key="platform", label="Platform", owner="marketing", type="select",
             options=["", "Standard Banners", "Apple News"]),
        dict(key="gam_line_items", label="GAM Line Items", owner="promo", type="text"),
        dict(key="creative_link", label="Creative Files - Links", owner="marketing", type="url"),
        dict(key="creative_name", label="Creative Name", owner="marketing", type="text"),
        dict(key="click_through_url", label="Click-Through URL", owner="marketing", type="url"),
        dict(key="tracking_pixel", label="1x1 / Tracking Pixel", owner="promo", type="text"),
        dict(key="targeting_requests", label="Targeting Requests", owner="marketing", type="text"),
    ]),
    dict(key="audio", label="Audio", fields=[
        dict(key="messaging", label="Messaging / Beat / Phase", owner="marketing", type="text"),
        dict(key="flight_start", label="Flight Start", owner="marketing", type="date"),
        dict(key="flight_end", label="Flight End", owner="marketing", type="date"),
        dict(key="duration", label="Duration (seconds)", owner="marketing", type="text", placeholder="e.g. 30"),
        dict(key="creative_link", label="Creative Files - Links", owner="marketing", type="url"),
        dict(key="megaphone_line_item", label="Megaphone Line Item Link(s)", owner="promo", type="text"),
        dict(key="podcast_targets", label="Podcast Targets", owner="marketing", type="select",
             options=["", "MTVE", "CBS", "Sports", "News"]),
    ]),
    dict(key="hpto", label="HPTO", fields=[
        dict(key="date_booked", label="Date Booked", owner="marketing", type="date"),
        dict(key="creative_banners", label="Creative Files - Banners", owner="marketing", type="url"),
        dict(key="creative_skybox_cid", label="Creative Files - Skybox CID", owner="marketing", type="text"),
        dict(key="gam_order_name", label="GAM Order Name", owner="promo", type="text"),
        dict(key="click_through_url", label="Click-Through URL", owner="marketing", type="url"),
        dict(key="tracking_pixel", label="1x1 / Tracking Pixel", owner="promo", type="text"),
    ]),
    dict(key="video_domination", label="Video Domination", fields=[
        dict(key="flight_start", label="Flight Start", owner="marketing", type="date"),
        dict(key="flight_end", label="Flight End", owner="marketing", type="date"),
        dict(key="freewheel_order_name", label="FreeWheel Order Name", owner="promo", type="text"),
        dict(key="creative_link", label="Creative Files - Links", owner="marketing", type="url"),
        dict(key="creative_name", label="Creative Name", owner="marketing", type="text"),
        dict(key="click_through_url", label="Click-Through URL", owner="marketing", type="url"),
        dict(key="targeting", label="Targeting", owner="marketing", type="text"),
        dict(key="tracking_pixel", label="1x1 / Tracking Pixel", owner="promo", type="text"),
    ]),
]

NET_NEW_OPTIONS = ["New", "Reused – Prior Flight", "Refresh of Existing"]


def app_data() -> dict:
    return {"campaigns": campaigns(), "tabs": TABS, "netNewOptions": NET_NEW_OPTIONS}


def build(out: Path | None = None) -> Path:
    html = TEMPLATE.replace("/*APP_DATA*/", json.dumps(app_data(), ensure_ascii=False))
    out = out or OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paramount Promo — Creative Trafficking</title>
<style>
:root{--navy:#0B3D91;--blue:#1F6FEB;--bg:#eef2f9;--card:#fff;--ink:#1a2540;--muted:#6b7690;
 --line:#e2e8f4;--ok:#1a9d63;--no:#d0453b;--chip:#e8eefb;--focus:rgba(31,111,235,.25);
 --mkt:#0B3D91;--promo:#6b7690;}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#e9eef8,#eef2f9);color:var(--ink);
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:980px;margin:0 auto;padding:0 18px 140px}
header{position:sticky;top:0;z-index:20;background:var(--navy);color:#fff;
 padding:16px 18px;box-shadow:0 4px 18px rgba(11,61,145,.28)}
.hwrap{max-width:980px;margin:0 auto;display:flex;align-items:center;gap:14px}
header h1{font-size:18px;margin:0;font-weight:700;letter-spacing:.2px}
header p{margin:2px 0 0;font-size:12.5px;opacity:.85}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;
 padding:20px 22px;margin:18px 0;box-shadow:0 6px 22px rgba(20,40,90,.06)}
.card h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--blue);
 margin:0 0 4px}
.card .sub{color:var(--muted);font-size:12.5px;margin:0 0 16px}
.field{margin:14px 0}
.field label{display:block;font-weight:600;font-size:13.5px;margin:0 0 6px}
.field label .req{color:var(--no);margin-left:3px}
.hint{color:var(--muted);font-size:12px;margin-top:5px}
input[type=text],input[type=date],input[type=url],select{width:100%;padding:10px 12px;font-size:14px;
 border:1.5px solid var(--line);border-radius:10px;background:#fff;color:var(--ink);
 transition:border-color .15s, box-shadow .15s;appearance:none}
select{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%236b7690' stroke-width='2.5'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
 background-repeat:no-repeat;background-position:right 11px center;padding-right:32px;cursor:pointer}
input:focus,select:focus{outline:none;border-color:var(--blue);box-shadow:0 0 0 4px var(--focus)}
input:read-only,input.promo-ro{background:#f3f5fa;color:var(--muted);cursor:not-allowed}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:560px){.row{grid-template-columns:1fr}}
.hidden{display:none!important}
.badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
 border-radius:999px;padding:2px 8px;margin-left:6px;vertical-align:middle}
.badge.mkt{background:#e8eefb;color:var(--mkt)}
.badge.promo{background:#eef1f6;color:var(--promo)}
.tabbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:6px}
.tabbtn{border:1.5px solid var(--line);background:#fff;color:var(--muted);border-radius:10px;
 padding:9px 14px;font-size:13px;font-weight:700;cursor:pointer}
.tabbtn.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.tabbtn .count{opacity:.75;font-weight:600}
.line{border:1.5px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0;position:relative;background:#fbfcfe}
.line .lhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.line .lhead b{font-size:13px;color:var(--muted)}
.rmBtn{border:0;background:#f3d9d7;color:var(--no);width:26px;height:26px;border-radius:50%;
 cursor:pointer;font-size:14px;line-height:1;display:grid;place-items:center}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media(max-width:760px){.grid3{grid-template-columns:1fr 1fr}}
@media(max-width:520px){.grid3{grid-template-columns:1fr}}
.netnew{border:1.5px dashed #c9d6f3;border-radius:12px;padding:10px 12px;margin-top:10px;background:#f6f9ff}
.addBtn{border:1.5px dashed var(--blue);background:#fff;color:var(--blue);border-radius:12px;
 padding:11px 16px;font-size:13.5px;font-weight:700;cursor:pointer;width:100%;margin-top:6px}
.empty{color:var(--muted);font-size:13px;padding:10px 2px}
.bar{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid var(--line);
 box-shadow:0 -6px 22px rgba(20,40,90,.08);padding:14px 18px;z-index:30}
.barw{max-width:980px;margin:0 auto;display:flex;align-items:center;flex-wrap:wrap;gap:10px 12px}
.status{flex:1 1 200px;min-width:120px;color:var(--muted);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.btn{border:0;border-radius:11px;padding:12px 18px;font-size:14.5px;font-weight:700;cursor:pointer}
.btn.primary{background:var(--blue);color:#fff}
.btn.ghost{background:#eef2f9;color:var(--navy)}
.btn:disabled{opacity:.45;cursor:not-allowed}
</style></head>
<body>
<header><div class="hwrap">
  <div><h1>Creative Trafficking</h1><p>Paramount Promo — one intake format for every team's creative delivery</p></div>
</div></header>
<div class="wrap">

  <div class="card">
    <h2>Case</h2><p class="sub">These carry through onto every creative line below.</p>
    <div class="row">
      <div class="field"><label>Salesforce Case #</label>
        <input type="text" id="sf_case" placeholder="e.g. 00123456"></div>
      <div class="field"><label>Creative / Marketing Manager</label>
        <input type="text" id="creative_manager" placeholder="submitter's name"></div>
    </div>
    <div class="field"><label>Campaign Name</label>
      <select id="campaign"><option value="">Select campaign…</option></select>
      <div class="hint">Mirrors the Salesforce Campaign this creative is for.</div></div>
  </div>

  <div class="card">
    <h2>Creative lines</h2>
    <p class="sub">
      <span class="badge mkt">Marketing</span> fields are filled by whoever's submitting the creative.
      <span class="badge promo">Promo</span> fields are filled by Promo Ops after intake — left read-only here.
      Every line also gets a <b>Net New Creative</b> flag so Promo Ops knows what actually needs to be
      trafficked fresh vs. re-pointed at an existing flight's asset.
    </p>
    <div class="tabbar" id="tabbar"></div>
    <div id="tabbody"></div>
  </div>
</div>

<div class="bar"><div class="barw">
  <span class="status" id="status">Add at least one creative line to continue.</span>
  <button class="btn ghost" id="copyBtn">Copy JSON</button>
  <button class="btn primary" id="dlBtn" disabled>Download plan file</button>
</div></div>

<script>
const APP = /*APP_DATA*/;
const $ = s => document.querySelector(s);
const state = {tab: APP.tabs[0].key, lines: {}};
APP.tabs.forEach(t => state.lines[t.key] = []);

$("#campaign").innerHTML += APP.campaigns.map(c=>`<option value="${c.name}">${c.name}</option>`).join("");

function tabOf(key){ return APP.tabs.find(t=>t.key===key); }

function renderTabbar(){
  $("#tabbar").innerHTML = APP.tabs.map(t=>{
    const n = state.lines[t.key].length;
    return `<button type="button" class="tabbtn ${t.key===state.tab?'on':''}" data-t="${t.key}">${t.label} <span class="count">(${n})</span></button>`;
  }).join("");
  $("#tabbar").querySelectorAll(".tabbtn").forEach(b=>b.addEventListener("click",()=>{
    state.tab = b.dataset.t; render();
  }));
}

function fieldInput(tabKey, idx, f, value){
  const id = `f_${tabKey}_${idx}_${f.key}`;
  const ro = f.owner === "promo";
  const badge = `<span class="badge ${f.owner==='marketing'?'mkt':'promo'}">${f.owner==='marketing'?'Marketing':'Promo'}</span>`;
  let input;
  if(f.type === "select"){
    input = `<select id="${id}" ${ro?"disabled":""} data-k="${f.key}">` +
      (f.options||[]).map(o=>`<option value="${o}" ${o===value?"selected":""}>${o||"—"}</option>`).join("") + `</select>`;
  } else {
    const t = f.type === "date" ? "date" : (f.type === "url" ? "url" : "text");
    input = `<input type="${t}" id="${id}" data-k="${f.key}" value="${(value||"").replace(/"/g,'&quot;')}" ` +
      `${ro?'class="promo-ro" readonly placeholder="Filled by Promo Ops"':(f.placeholder?`placeholder="${f.placeholder}"`:"")}>`;
  }
  return `<div class="field"><label>${f.label}${badge}</label>${input}</div>`;
}

function renderLine(tabKey, idx, line){
  const t = tabOf(tabKey);
  const showRef = line.net_new && line.net_new !== "New";
  return `<div class="line" data-idx="${idx}">
    <div class="lhead"><b>${t.label} line ${idx+1}</b>
      <button type="button" class="rmBtn" data-rm="${idx}" title="Remove line">×</button></div>
    <div class="grid3">${t.fields.map(f=>fieldInput(tabKey, idx, f, line[f.key])).join("")}</div>
    <div class="netnew">
      <div class="field"><label>Net New Creative<span class="badge mkt">Marketing</span></label>
        <select data-k="net_new">${APP.netNewOptions.map(o=>`<option ${o===(line.net_new||"New")?"selected":""}>${o}</option>`).join("")}</select>
        <div class="hint">Is this a brand-new asset, or reused/refreshed from a prior flight?</div></div>
      <div class="field ${showRef?"":"hidden"}" data-priorref>
        <label>Prior Creative Reference</label>
        <input type="text" data-k="prior_creative_ref" value="${(line.prior_creative_ref||"").replace(/"/g,'&quot;')}"
          placeholder="prior Creative Name, Click-Through URL, or Case #">
      </div>
    </div>
  </div>`;
}

function renderTabbody(){
  const t = tabOf(state.tab);
  const lines = state.lines[t.key];
  $("#tabbody").innerHTML =
    (lines.length ? lines.map((l,i)=>renderLine(t.key,i,l)).join("")
                  : `<div class="empty">No ${t.label} lines yet — add one below.</div>`) +
    `<button type="button" class="addBtn" id="addLineBtn">+ Add ${t.label} line</button>`;
  $("#addLineBtn").addEventListener("click", ()=>{
    state.lines[t.key].push({net_new: "New"});
    render();
  });
  $("#tabbody").querySelectorAll(".line").forEach(el=>{
    const idx = Number(el.dataset.idx);
    el.querySelectorAll("[data-rm]").forEach(b=>b.addEventListener("click",()=>{
      state.lines[t.key].splice(idx,1); render();
    }));
    el.querySelectorAll("[data-k]").forEach(inp=>{
      inp.addEventListener("input", ()=>{
        state.lines[t.key][idx][inp.dataset.k] = inp.value;
        if(inp.dataset.k === "net_new"){
          const ref = el.querySelector("[data-priorref]");
          if(ref) ref.classList.toggle("hidden", inp.value === "New");
        }
        validate();
      });
      inp.addEventListener("change", ()=>{
        state.lines[t.key][idx][inp.dataset.k] = inp.value;
      });
    });
  });
}

function render(){ renderTabbar(); renderTabbody(); validate(); }

function totalLines(){ return APP.tabs.reduce((n,t)=>n+state.lines[t.key].length, 0); }

function validate(){
  const ok = totalLines() > 0;
  $("#dlBtn").disabled = !ok;
  $("#status").textContent = ok
    ? `${totalLines()} creative line(s) ready — Download plan file to attach to the Case.`
    : "Add at least one creative line to continue.";
  return ok;
}

function buildPlan(){
  const plan = {
    salesforce_case: $("#sf_case").value.trim(),
    campaign_name: $("#campaign").value,
    creative_manager: $("#creative_manager").value.trim(),
  };
  APP.tabs.forEach(t=>{ plan[t.key] = state.lines[t.key]; });
  return plan;
}
function fname(){
  const p = buildPlan();
  const base = p.salesforce_case || p.campaign_name || "creative-trafficking";
  return base.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")+".creative.json";
}
$("#dlBtn").addEventListener("click", ()=>{
  if(!validate()) return;
  const blob = new Blob([JSON.stringify(buildPlan(),null,2)],{type:"application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = fname(); a.click();
});
$("#copyBtn").addEventListener("click", async ()=>{
  await navigator.clipboard.writeText(JSON.stringify(buildPlan(),null,2));
  $("#copyBtn").textContent = "Copied ✓"; setTimeout(()=>$("#copyBtn").textContent="Copy JSON",1400);
});

render();
</script>
</body></html>
"""


if __name__ == "__main__":
    print(f"Wrote {build()}")
