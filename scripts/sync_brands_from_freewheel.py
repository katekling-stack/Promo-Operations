"""Sync the brand catalog to FreeWheel's real advertisers/campaigns.

FreeWheel is the source of truth for which brand-campaigns exist per country. This
script enumerates them and reports what the config (and therefore the plan form) is
missing — and can scaffold the missing entries by cloning a same-family sibling.

    # Report only (safe), live against FW — needs FREEWHEEL_* env creds:
    python scripts/sync_brands_from_freewheel.py

    # Offline: feed a JSON dump of campaigns [{"name","id","advertiser_name"}, ...]
    python scripts/sync_brands_from_freewheel.py --from-json fw_campaigns.json

    # Scaffold the missing entries into config/brands.yaml (review the diff, then
    # fill each 'TODO:' region-specific site-group id), and regenerate the form:
    python scripts/sync_brands_from_freewheel.py --from-json fw_campaigns.json --write
    python scripts/build_plan_form.py

Scaffolded entries are cloned from a sibling region and marked '_cloned_from'; their
region-specific FW ids (main_site_groups, template_io_id) are blanked with a 'TODO:'
so they're verified, never guessed. --write never edits or deletes existing brands.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import yaml

from promo_ops import brand_sync

BRANDS_YAML = REPO / "config" / "brands.yaml"


def _load_campaigns(from_json: str | None) -> list[dict]:
    if from_json:
        return json.loads(Path(from_json).read_text(encoding="utf-8"))
    from promo_ops.integrations.freewheel import FreeWheelClient
    client = FreeWheelClient()
    client.authenticate()
    return client.discover_brand_campaigns()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-json", help="offline campaign dump instead of a live FW call")
    ap.add_argument("--write", action="store_true",
                    help="scaffold missing entries into config/brands.yaml")
    args = ap.parse_args(argv)

    brands_doc = yaml.safe_load(BRANDS_YAML.read_text(encoding="utf-8")) or {}
    brands = brands_doc.get("brands", {})

    campaigns = _load_campaigns(args.from_json)
    result = brand_sync.reconcile(campaigns, brands)
    print(brand_sync.render_report(result))

    if not args.write:
        if result["missing_in_config"]:
            print("Re-run with --write to scaffold the missing entries.")
        return 0

    added = []
    for row in result["missing_in_config"]:
        scaffold = brand_sync.scaffold_entry(row, brands)
        if not scaffold:
            print(f"  ! no sibling to clone for {row['campaign_name']} — add by hand")
            continue
        key, entry = scaffold
        if key in brands:
            key = f"{key}_2"
        brands[key] = entry
        added.append((key, entry.get("_cloned_from")))

    if not added:
        print("Nothing to scaffold.")
        return 0

    BRANDS_YAML.write_text(
        yaml.safe_dump(brands_doc, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8")
    try:
        where = BRANDS_YAML.relative_to(REPO)
    except ValueError:
        where = BRANDS_YAML
    print(f"\nScaffolded {len(added)} brand(s) into {where}:")
    for key, sib in added:
        print(f"  + {key}  (cloned from {sib})")
    print("Review the diff, fill each 'TODO:' region id, then run "
          "`python scripts/build_plan_form.py`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
