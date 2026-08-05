"""Configuration loading — YAML config files and environment credentials."""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a convenience only
    pass


# Repo root = two levels up from this file (src/promo_ops/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


@functools.lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """Load and cache a YAML config file from the config/ directory."""
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def tiers_config() -> dict[str, Any]:
    return load_yaml("tiers.yaml")


def regions_config() -> dict[str, Any]:
    return load_yaml("regions.yaml")


def brands_config() -> dict[str, Any]:
    return load_yaml("brands.yaml")


def placement_templates_config() -> dict[str, Any]:
    return load_yaml("placement_templates.yaml")


def priorities_config() -> dict[str, Any]:
    return load_yaml("priorities.yaml")


def pluto_config() -> dict[str, Any]:
    return load_yaml("pluto.yaml")


def ad_units_config() -> dict[str, Any]:
    return load_yaml("ad_units.yaml")


def relationship_targeting_config() -> dict[str, Any]:
    return load_yaml("relationship_targeting.yaml")


def video_dominations_config() -> dict[str, Any]:
    return load_yaml("video_dominations.yaml")


def operative_takeovers_config() -> dict[str, Any]:
    return load_yaml("operative_takeovers.yaml")


def kids_targeting_config() -> dict[str, Any]:
    """The Kids audience -> Video Group mapping (config/relationship_targeting.yaml)."""
    return load_yaml("relationship_targeting.yaml").get("kids", {})


def frequency_caps_config() -> dict[str, Any]:
    """Order-level frequency-cap rules (config/frequency_caps.yaml)."""
    return load_yaml("frequency_caps.yaml")


def kids_video_groups(audience: list[str] | None) -> list[str]:
    """Resolve a Kids audience selection to its Video Group IDs.

    "older" -> older VG, "younger" -> younger VG; the base VG is always included when
    ANY audience is selected. Empty selection -> [] (no Kids targeting -> no Kids IOs).
    """
    audience = [str(a).strip().lower() for a in (audience or []) if str(a).strip()]
    if not audience:
        return []
    cfg = kids_targeting_config()
    vgs = [cfg.get("base_video_group")]
    if "older" in audience:
        vgs.append(cfg.get("older_video_group"))
    if "younger" in audience:
        vgs.append(cfg.get("younger_video_group"))
    return [v for v in vgs if v]


def brand_for_campaign(campaign: dict[str, Any]) -> str | None:
    """Derive the brand key from a plan's campaign (id or name).

    Each brand owns one campaign per region ("Paramount + - USA", "CBS News - USA",
    …), so the CM only needs to pick the campaign — the brand follows. Matches the
    campaign's resolved_id against each brand's template_campaign_id, else its name
    (case-insensitive) against campaign_name.
    """
    if not campaign:
        return None
    cid = str(campaign.get("resolved_id") or "").strip()
    cname = str(campaign.get("name") or "").strip().lower()
    for key, cfg in (brands_config().get("brands", {}) or {}).items():
        if cid and str(cfg.get("template_campaign_id") or "") == cid:
            return key
        if cname and str(cfg.get("campaign_name") or "").strip().lower() == cname:
            return key
    return None


def env(key: str, default: str | None = None) -> str | None:
    """Read a credential/setting from the environment."""
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    """Read a required credential; raise a clear error if missing."""
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {key!r}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value
