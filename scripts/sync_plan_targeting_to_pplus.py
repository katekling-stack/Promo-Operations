"""Mirror Tier 1 targeting onto the "Plan" (guaranteed) placements of a campaign,
then restrict them to the Paramount+ site group only.

Background: "Plan" placements are the guaranteed lines (e.g. "Premium Pre-Roll -
Premium Plan", "Bumper - Essential Plan") — see docs/reference-ios.md and the
`p.guaranteed` branch of FreeWheelClient._relationship_sets. They only run on
Paramount+ endpoints, so after copying a Tier 1 sibling's targeting onto them, every
`site_group` list under an `include` block is narrowed to just the Paramount+ SG.

DEFAULTS TO A DRY RUN. It always reads live data and always prints a full diff per
placement; it only writes to FreeWheel when both `--live` is passed AND a real
update-placement tool was discovered (see FreeWheelClient.find_tool / update_placement
— no such tool has been verified against the API yet in this codebase). Prove this on
the test network (520310) before ever pointing `--live` at production (520311).

Usage:
    python scripts/sync_plan_targeting_to_pplus.py --campaign 86543608
    python scripts/sync_plan_targeting_to_pplus.py --campaign 86543608 --live
"""

from __future__ import annotations

import argparse
import copy
import json
from typing import Any, Optional

from promo_ops.config import brands_config, relationship_targeting_config
from promo_ops.integrations.freewheel import FreeWheelClient

# "Plan" placements are the guaranteed/sponsored lines — Premium/Essential/Basic Plan.
PLAN_NAME_HINT = "plan"
TIER1_NAME_HINT = "(tier 1)"


def _default_campaign_id() -> str:
    return brands_config()["brands"]["paramount_plus_domestic"]["template_campaign_id"]


def _default_pplus_site_group() -> str:
    return relationship_targeting_config()["domestic_usa"]["pplus_site_group"][0]


def is_plan_placement(p: dict[str, Any]) -> bool:
    return PLAN_NAME_HINT in str(p.get("name", "")).lower()


def is_tier1_placement(p: dict[str, Any]) -> bool:
    return TIER1_NAME_HINT in str(p.get("name", "")).lower()


def _restrict_include_site_groups(node: Any, keep_id: str) -> None:
    """Walk every `include` subtree and force any `site_group` list down to [keep_id].

    Recurses through nested relationship-set shapes (`set: [...]`,
    `network_items: {...}`) uniformly — anything under an `include` key gets its
    site_group lists narrowed; `exclude` blocks are left untouched.
    """
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "include":
                _force_site_groups(val, keep_id)
            else:
                _restrict_include_site_groups(val, keep_id)
    elif isinstance(node, list):
        for item in node:
            _restrict_include_site_groups(item, keep_id)


def _force_site_groups(node: Any, keep_id: str) -> None:
    if isinstance(node, dict):
        if "site_group" in node:
            node["site_group"] = [keep_id]
        for val in node.values():
            _force_site_groups(val, keep_id)
    elif isinstance(node, list):
        for item in node:
            _force_site_groups(item, keep_id)


def build_plan_targeting(tier1_detail: dict[str, Any], keep_sg: str) -> dict[str, Any]:
    """Targeting-only fields (audience/content/relationship targeting) copied from a
    Tier 1 sibling, with every included site_group narrowed to the Paramount+ SG.
    Budget, delivery, ad_product, and geography are NOT touched — those describe the
    Plan placement's own guaranteed line, not the Tier 1 remnant's."""
    out: dict[str, Any] = {}
    for field in ("audience_targeting", "content_targeting", "relationship_targeting"):
        if field in tier1_detail:
            out[field] = copy.deepcopy(tier1_detail[field])
    _restrict_include_site_groups(out, keep_sg)
    return out


def find_tier1_sibling(fw: FreeWheelClient, io_id: str,
                       placements: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    tier1 = [p for p in placements if is_tier1_placement(p)
             and str(p.get("status", "")).upper() == "ACTIVE"]
    if not tier1:
        return None
    if len(tier1) > 1:
        print(f"    NOTE: IO {io_id} has {len(tier1)} active Tier 1 placements "
              f"(one per duration); using {tier1[0]['name']!r} as the targeting "
              f"reference — Tier 1 targeting doesn't vary by duration.")
    return tier1[0]


def sync_campaign(fw: FreeWheelClient, campaign_id: str, keep_sg: str, live: bool) -> None:
    payload = fw._invoke("sh_1_1_list-insertion-orders-of-a-campaign",
                         campaign_id=int(campaign_id), per_page=100)
    io_ids = [str(io.get("id")) for io in fw._rows(payload, "insertion_orders")]

    total_considered, total_updated, total_skipped = 0, 0, 0
    for io_id in io_ids:
        placements = fw.list_placements(io_id)
        plans = [p for p in placements if is_plan_placement(p)
                 and str(p.get("status", "")).upper() == "ACTIVE"]
        if not plans:
            continue
        tier1 = find_tier1_sibling(fw, io_id, placements)
        if not tier1:
            print(f"IO {io_id}: {len(plans)} Plan placement(s) but no active Tier 1 "
                  f"sibling found — skipping.")
            total_skipped += len(plans)
            continue

        tier1_detail = fw.get_placement_targeting(tier1["id"])
        new_targeting = build_plan_targeting(tier1_detail, keep_sg)

        for plan in plans:
            old_detail = fw.get_placement_targeting(plan["id"])
            old_targeting = {k: old_detail.get(k) for k in
                             ("audience_targeting", "content_targeting", "relationship_targeting")
                             if k in old_detail}
            print(f"\n--- Plan placement {plan['id']} {plan['name']!r}  "
                  f"(mirroring Tier 1 {tier1['id']} {tier1['name']!r})")
            print(f"    BEFORE: {json.dumps(old_targeting)[:1500]}")
            print(f"    AFTER:  {json.dumps(new_targeting)[:1500]}")
            total_considered += 1

            if not live:
                continue
            result = fw.update_placement(plan["id"], new_targeting, dry_run=False)
            print(f"    -> {result}")
            total_updated += 1

    verb = "Updated" if live else "Would update"
    count = total_updated if live else total_considered
    print(f"\n{verb} {count} placement(s); skipped {total_skipped} "
          f"(no Tier 1 sibling).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", default=None,
                    help="Campaign id (default: paramount_plus_domestic's "
                         "template_campaign_id from config/brands.yaml)")
    ap.add_argument("--keep-site-group", default=None,
                    help="Site group id to keep (default: pplus_site_group from "
                         "config/relationship_targeting.yaml)")
    ap.add_argument("--live", action="store_true",
                    help="Actually write updates (requires a discovered update tool; "
                         "prove this on the test network, 520310, first)")
    args = ap.parse_args()

    campaign_id = args.campaign or _default_campaign_id()
    keep_sg = args.keep_site_group or _default_pplus_site_group()

    fw = FreeWheelClient()
    fw.authenticate()

    print(f"Campaign {campaign_id}: mirroring Tier 1 -> Plan placements, "
          f"site groups narrowed to [{keep_sg}] (Paramount+)")
    print("DRY RUN — no writes will be made" if not args.live else
          "LIVE — will attempt real updates (only if an update tool is discovered)")
    sync_campaign(fw, campaign_id, keep_sg, args.live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
