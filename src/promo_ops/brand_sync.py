"""Reconcile the brand catalog against FreeWheel's real advertisers/campaigns.

FreeWheel is the source of truth: each country Advertiser holds one Campaign per
brand, so the set of brand-campaigns the tool (and the plan form) offers should be
a projection of what actually exists in FW — never hand-guessed.

This module is pure (no network): it maps FW campaign rows to our brand catalog so
we can see which brand-campaigns exist in FW but are MISSING from config (and which
config brands no longer have a matching FW campaign), and scaffold the missing ones
by cloning a same-family sibling brand from another region. The live enumeration
lives in integrations/freewheel.py (discover_brand_campaigns); the CLI wiring lives
in scripts/sync_brands_from_freewheel.py.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from .config import regions_config

# Region codes, longest-first so "GSA"/"LATAM" win over shorter tails and a bare
# "USA" doesn't shadow nothing. Sourced from config so it can't drift.
_REGION_CODES = sorted(regions_config().get("regions", {}).keys(), key=len, reverse=True)

# Ordered (family, matcher) — first match wins, so specific beats general
# (nick_jr before nick, *_kids before the adult brand).
_FAMILY_RULES: list[tuple[str, Any]] = [
    ("nick_jr", lambda n: "nick jr" in n),
    ("nick", lambda n: "nick" in n or "nickelodeon" in n),
    ("paramount_plus_kids", lambda n: "paramount +" in n and "kids" in n),
    ("paramount_plus", lambda n: "paramount +" in n),
    ("pluto_kids", lambda n: "pluto" in n and "kids" in n),
    ("pluto", lambda n: "pluto" in n),
    ("pictures_kids", lambda n: "pictures" in n and "kids" in n),
    ("pictures", lambda n: "pictures" in n),
    ("consumer_products", lambda n: "consumer products" in n),
    ("cbs_sports", lambda n: "cbs sports" in n),
    ("cbs_news", lambda n: "cbs news" in n),
    ("cbs_network", lambda n: "cbs network" in n),
    ("mtve", lambda n: "mtve" in n),
    ("bet", lambda n: "bet" in n),
]


def region_of(campaign_name: str) -> Optional[str]:
    """The trailing region code of a campaign name (e.g. 'Pluto TV - FR' -> 'FR')."""
    name = (campaign_name or "").strip()
    for code in _REGION_CODES:
        if re.search(rf"(?:^|[\s-])\(?{re.escape(code)}\)?$", name):
            return code
    return None


def brand_family(campaign_name: str) -> Optional[str]:
    """Classify a campaign into a brand family (used to pick a sibling to clone)."""
    n = (campaign_name or "").lower()
    for family, matches in _FAMILY_RULES:
        if matches(n):
            return family
    return None


def looks_like_brand_campaign(campaign_name: str) -> bool:
    """A promo brand campaign = a known family AND a known region tail.

    Filters out the non-promo campaigns that also live under the VCBS advertisers
    (sales orders, house campaigns, test campaigns) so they don't pollute the sync.
    """
    return bool(region_of(campaign_name) and brand_family(campaign_name))


def _norm(name: str) -> str:
    """Collapse whitespace so 'Paramount +  - Kids' == 'Paramount + - Kids'."""
    return re.sub(r"\s+", " ", (name or "").strip())


def reconcile(fw_campaigns: Iterable[dict[str, Any]],
              brands_cfg: dict[str, Any]) -> dict[str, Any]:
    """Diff FreeWheel's brand campaigns against the config brand catalog.

    `fw_campaigns` is a list of {name, id, advertiser_name?} rows. Matching joins on
    campaign name (whitespace-normalized) — the reliable key, since config already
    stores campaign_name. Returns matched / missing_in_config / missing_in_fw, each a
    list of small dicts ready to render or scaffold.
    """
    cfg_by_name = {_norm(v.get("campaign_name", "")): (k, v)
                   for k, v in brands_cfg.items() if v.get("campaign_name")}

    fw_by_name: dict[str, dict[str, Any]] = {}
    for c in fw_campaigns:
        name = _norm(c.get("name", ""))
        if name and looks_like_brand_campaign(name):
            fw_by_name.setdefault(name, c)   # first wins on dupes

    matched, missing_in_config = [], []
    for name, c in sorted(fw_by_name.items()):
        row = {"campaign_name": name, "campaign_id": str(c.get("id") or ""),
               "region": region_of(name), "family": brand_family(name),
               "advertiser": c.get("advertiser_name")}
        if name in cfg_by_name:
            row["brand_key"] = cfg_by_name[name][0]
            matched.append(row)
        else:
            missing_in_config.append(row)

    missing_in_fw = [{"brand_key": k, "campaign_name": v.get("campaign_name"),
                      "region": region_of(v.get("campaign_name", "")),
                      "family": brand_family(v.get("campaign_name", ""))}
                     for name, (k, v) in sorted(cfg_by_name.items())
                     if name not in fw_by_name]

    return {"matched": matched, "missing_in_config": missing_in_config,
            "missing_in_fw": missing_in_fw}


def _brand_key(family: str, region: str) -> str:
    return f"{family}_{region}".lower()


# Region groups — a clone from the same group carries the right regional shape
# (EU markets share format overrides / site-group patterns the US template lacks).
_REGION_GROUP = {
    "USA": "AMER", "CA": "AMER", "LATAM": "AMER", "BR": "AMER",
    "UK": "EU", "IE": "EU", "FR": "EU", "IT": "EU", "GSA": "EU",
    "FI": "EU", "DK": "EU", "NO": "EU", "SE": "EU", "ES": "EU", "AU": "APAC",
}


def find_sibling(family: str, region: str,
                 brands_cfg: dict[str, Any]) -> Optional[str]:
    """A config brand of the same family in another region, to clone from.

    Prefers a sibling in the same region group (EU/AMER/APAC) so a new EU market
    clones an EU template, not the US one; falls back to any same-family brand.
    """
    same_group, any_match = None, None
    want_group = _REGION_GROUP.get(region)
    for key, v in brands_cfg.items():
        cname = v.get("campaign_name", "")
        if brand_family(cname) != family or region_of(cname) == region:
            continue
        any_match = any_match or key
        if want_group and _REGION_GROUP.get(region_of(cname)) == want_group:
            same_group = same_group or key
    return same_group or any_match


# Fields that are region-specific FW IDs — a clone can't reuse them, so we blank
# them and leave a marker for a human (or a deeper FW sync) to fill.
_REGION_SPECIFIC = ("main_site_groups", "pause_main_site_groups", "template_io_id")


def scaffold_entry(fw_row: dict[str, Any], brands_cfg: dict[str, Any]) -> Optional[tuple[str, dict]]:
    """Build a new brand-catalog entry for a FW campaign missing from config.

    Clones the closest same-family sibling (so formats / ad-unit groups / kids flag
    carry over), then overlays the FW-derived identity (campaign name + id + display
    name) and blanks region-specific site-group IDs with a TODO so they're verified,
    not guessed. Returns (brand_key, entry) or None if no sibling exists to clone.
    """
    family, region = fw_row.get("family"), fw_row.get("region")
    if not (family and region):
        return None
    sib = find_sibling(family, region, brands_cfg)
    if not sib:
        return None
    import copy
    entry = copy.deepcopy(brands_cfg[sib])
    entry["campaign_name"] = fw_row["campaign_name"]
    entry["template_campaign_id"] = fw_row.get("campaign_id") or ""
    entry["display_name"] = _display_name(fw_row["campaign_name"])
    entry["_cloned_from"] = sib
    for f in _REGION_SPECIFIC:
        if f in entry:
            entry[f] = f"TODO: set {region} {f} (cloned from {sib})"
    return _brand_key(family, region), entry


def _display_name(campaign_name: str) -> str:
    """'Paramount + - Kids - FR' -> 'Paramount + - Kids (FR)'."""
    region = region_of(campaign_name)
    base = _norm(campaign_name)
    if region:
        base = re.sub(rf"(?:^|[\s-])\(?{re.escape(region)}\)?$", "", base).strip(" -")
        return f"{base} ({region})"
    return base


def render_report(result: dict[str, Any]) -> str:
    """Human-readable coverage report grouped by region."""
    lines = ["FreeWheel ↔ config brand coverage", "=" * 34, ""]
    mic, mif = result["missing_in_config"], result["missing_in_fw"]
    lines.append(f"Matched:            {len(result['matched'])}")
    lines.append(f"In FW, not config:  {len(mic)}   <- campaigns the form is missing")
    lines.append(f"In config, not FW:  {len(mif)}   <- possibly renamed/retired")
    lines.append("")
    if mic:
        lines.append("Missing from config (add these):")
        by_region: dict[str, list] = {}
        for r in mic:
            by_region.setdefault(r["region"] or "?", []).append(r)
        for region in sorted(by_region):
            lines.append(f"  {region}:")
            for r in by_region[region]:
                lines.append(f"    - {r['campaign_name']}  (campaign {r['campaign_id']})")
        lines.append("")
    if mif:
        lines.append("In config but not seen in FW (verify name/retire):")
        for r in mif:
            lines.append(f"  - {r['brand_key']}: {r['campaign_name']}")
        lines.append("")
    return "\n".join(lines)
