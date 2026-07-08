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
