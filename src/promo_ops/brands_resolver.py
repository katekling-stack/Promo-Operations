"""Brand resolver — the IO-level FreeWheel Brand a CM picks for a campaign.

Brands are synced per advertiser/region (scripts/sync_brands.py ->
data/brands/synced_brands.csv). The form offers the region's brands by name; the engine
resolves the picked name to its FreeWheel brand_id and stamps it on the Insertion Order.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .config import REPO_ROOT

DATA_FILE = REPO_ROOT / "data" / "brands" / "synced_brands.csv"


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


class BrandResolver:
    def __init__(self, data_file: Path = DATA_FILE):
        self.data_file = Path(data_file)
        # region -> list[(brand_name, brand_id)]  and  region -> {norm_name: brand_id}
        self._by_region: dict[str, list[tuple[str, str]]] = {}
        # (region, kids) -> list[(brand_name, brand_id)]: Kids brands live under the Kids advertiser
        self._by_kind: dict[tuple[str, bool], list[tuple[str, str]]] = {}
        self._index: dict[str, dict[str, str]] = {}
        # (region, kids) -> advertiser_id, for find-or-create of a new brand
        self._advertiser: dict[tuple[str, bool], str] = {}
        # brand_id -> advertiser_id, and (region, advertiser_id) -> {norm_name: brand_id}
        self._adv_of: dict[str, str] = {}
        self._by_adv: dict[tuple[str, str], dict[str, str]] = {}
        self._loaded = False

    def load(self) -> "BrandResolver":
        if self.data_file.exists():
            with open(self.data_file, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    region = (row.get("region") or "").strip()
                    name = (row.get("brand_name") or "").strip()
                    bid = (row.get("brand_id") or "").strip()
                    if not region or not name or not bid:
                        continue
                    kids = str(row.get("kids") or "0").strip() in ("1", "true", "True")
                    adv = (row.get("advertiser_id") or "").strip()
                    self._by_region.setdefault(region, []).append((name, bid))
                    self._by_kind.setdefault((region, kids), []).append((name, bid))
                    self._index.setdefault(region, {})[_norm(name)] = bid
                    if adv:
                        self._advertiser.setdefault((region, kids), adv)
                        self._adv_of[bid] = adv
                        self._by_adv.setdefault((region, adv), {})[_norm(name)] = bid
        self._loaded = True
        return self

    def advertiser_for(self, region: str, kids: bool) -> str | None:
        """The VCBS (Promo) advertiser id for a region + kids/adult, from the synced data."""
        self._ensure()
        return self._advertiser.get((region, bool(kids)))

    def advertiser_of(self, brand_id: str) -> str | None:
        """The advertiser a synced brand belongs to (None if the brand isn't in the synced list)."""
        self._ensure()
        return self._adv_of.get(str(brand_id))

    def find_for_advertiser(self, region: str, name: str, advertiser_id: str) -> str | None:
        """The brand for `name` that lives under `advertiser_id`: the same name, or the same title with
        " - Kids" added / removed before " (Promo)" (Kids and Adult brands of a title differ that way).
        None when that advertiser has no such brand (the caller then creates it there)."""
        self._ensure()
        index = self._by_adv.get((region, str(advertiser_id)), {})
        base = _norm(name)
        kids_form = base.replace(" (promo)", " - kids (promo)", 1) if " - kids (promo)" not in base else base
        adult_form = base.replace(" - kids (promo)", " (promo)", 1)
        for cand in (base, kids_form, adult_form):
            if cand in index:
                return index[cand]
        return None

    def _ensure(self):
        if not self._loaded:
            self.load()

    def brands_for(self, region: str, kids: bool | None = None) -> list[str]:
        """Distinct brand names available for a region, sorted. kids=True/False limits it to the Kids /
        Adult advertiser's brands; None (default) returns both."""
        self._ensure()
        rows = (self._by_region.get(region, []) if kids is None
                else self._by_kind.get((region, bool(kids)), []))
        return sorted({n for n, _ in rows}, key=str.lower)

    def resolve(self, region: str, name_or_id: str) -> str | None:
        """A picked brand name (or a raw numeric brand_id) -> brand_id for the region."""
        self._ensure()
        val = str(name_or_id or "").strip()
        if not val:
            return None
        if val.isdigit():
            return val
        return self._index.get(region, {}).get(_norm(val))

    def regions(self) -> list[str]:
        self._ensure()
        return sorted(self._by_region)
