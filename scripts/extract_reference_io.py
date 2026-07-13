"""Profile live FreeWheel IOs to reverse-engineer a brand into config.

Give it IOs, a Campaign, or an Advertiser and it walks the tree
(advertiser -> campaigns -> insertion orders -> ACTIVE placements) and prints the
config-relevant structure of each active placement: ad units, geo country, budget
model, and the content/audience relationship targeting (site groups, video groups,
series). This is the "hand me a campaign and I'll pull the examples" workflow.

Usage:
    python scripts/extract_reference_io.py --io 93584432 95298406
    python scripts/extract_reference_io.py --campaign 54440942
    python scripts/extract_reference_io.py --advertiser 1000520
    # add --json out/ to also dump raw per-IO JSON for the record

Only ACTIVE placements are shown (we only ever mirror active setups).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from promo_ops.integrations.freewheel import FreeWheelClient

WIDGETS = ["ad_product", "content_targeting", "geography_targeting",
           "audience_targeting", "budget"]


def _placement_detail(fw: FreeWheelClient, pid: str) -> dict:
    """Merge the per-widget show-a-placement reads (only one widget works per call)."""
    out: dict = {}
    for w in WIDGETS:
        r = fw._invoke("sh_1_0_show-a-placement", placement_id=int(pid), show=w, **{w: "true"})
        pl = (r or {}).get("data", {}).get("placement", {})
        if isinstance(pl, dict) and w in pl:
            out[w] = pl[w]
    return out


def _active_ad_units(detail: dict) -> list[str]:
    ap = detail.get("ad_product") or {}
    nodes = ap.get("ad_unit_node") or []
    if isinstance(nodes, dict):
        nodes = [nodes]
    return [n.get("ad_unit_id") for n in nodes
            if str(n.get("status", "")).upper() == "ACTIVE"]


def profile_io(fw: FreeWheelClient, io_id: str) -> dict:
    placements = fw.list_placements(io_id)
    active = [p for p in placements if str(p.get("status")).upper() == "ACTIVE"]
    rows = []
    for p in active:
        d = _placement_detail(fw, p["id"])
        geo = ((d.get("geography_targeting") or {}).get("include") or {}).get("country")
        rows.append({
            "id": p["id"],
            "name": p["name"],
            "ad_units": _active_ad_units(d),
            "geo_country": geo,
            "budget_model": (d.get("budget") or {}).get("budget_model"),
            "content_targeting": (d.get("content_targeting") or {}).get("include"),
            "audience_targeting": (d.get("audience_targeting") or {}).get("include"),
        })
    return {"io_id": io_id, "active": len(active), "total": len(placements),
            "placements": rows}


def ios_of_campaign(fw: FreeWheelClient, campaign_id: str) -> list[str]:
    payload = fw._invoke("sh_1_1_list-insertion-orders-of-a-campaign",
                         campaign_id=int(campaign_id), per_page=100)
    return [str(io.get("id")) for io in fw._rows(payload, "insertion_orders")]


def campaigns_of_advertiser(fw: FreeWheelClient, advertiser_id: str) -> list[str]:
    payload = fw._invoke("sh_1_1_list-campaigns", advertiser_id=int(advertiser_id),
                         per_page=100)
    return [str(c.get("id")) for c in fw._rows(payload, "campaigns")]


def _print_io(prof: dict) -> None:
    print(f"\n===== IO {prof['io_id']}: {prof['active']} ACTIVE / {prof['total']} total =====")
    for r in prof["placements"]:
        print(f"\n--- {r['name']}")
        print(f"    ad_units: {r['ad_units']}   geo: {r['geo_country']}   "
              f"budget: {r['budget_model']}")
        if r["content_targeting"]:
            print(f"    content_targeting: {json.dumps(r['content_targeting'])[:2000]}")
        if r["audience_targeting"]:
            print(f"    audience_targeting: {json.dumps(r['audience_targeting'])[:1200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--io", nargs="*", default=[])
    ap.add_argument("--campaign", nargs="*", default=[])
    ap.add_argument("--advertiser", nargs="*", default=[])
    ap.add_argument("--json", help="directory to also dump raw per-IO JSON")
    args = ap.parse_args()

    fw = FreeWheelClient()
    fw.authenticate()

    io_ids = list(args.io)
    for cid in args.campaign:
        found = ios_of_campaign(fw, cid)
        print(f"Campaign {cid}: {len(found)} IO(s) -> {found}")
        io_ids += found
    for aid in args.advertiser:
        for cid in campaigns_of_advertiser(fw, aid):
            found = ios_of_campaign(fw, cid)
            print(f"Advertiser {aid} / campaign {cid}: {len(found)} IO(s)")
            io_ids += found

    out_dir = Path(args.json) if args.json else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    for io_id in io_ids:
        prof = profile_io(fw, io_id)
        _print_io(prof)
        if out_dir:
            (out_dir / f"io_{io_id}.json").write_text(json.dumps(prof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
