"""FreeWheel geography (country) resolver.

The team targets geography by NAME in the FreeWheel UI — they search "United
States" under Add New Country and select it. The Placement API, however, writes
`geography_targeting.include.country` as a set of numeric FW country IDs.

This resolver bridges the two: a region code (USA) maps to one or more country
NAMES (config/regions.yaml -> `countries`), and each name resolves to its FW
country ID via the country table.

Source of the table: the FreeWheel Standard Attributes taxonomy type
`content_territories` (verified to match the UI's Add-New-Country IDs exactly,
e.g. United States = 165, Canada = 27, Australia = 10, Brazil = 21). It is
exported to CSV by `FreeWheelClient.sync_countries()`; a committed seed CSV
(data/geo/seed_countries.csv) makes resolution work offline.

Matching is by normalized name. Unmatched names are reported, never guessed — a
wrong country ID would mis-target a live placement.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audience_segments import normalize_title  # reuse name normalization
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "geo"


@dataclass
class CountryMatch:
    name: str
    id: Optional[str]
    matched: bool


class CountryResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._index: dict[str, str] = {}   # normalized country name -> id
        self._loaded = False

    def load(self) -> "CountryResolver":
        self._index.clear()
        if self.data_dir.exists():
            # synced_ (live refresh) wins over seed_ when both are present.
            for path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(path)
        self._loaded = True
        return self

    def _load_csv(self, path: Path) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("country_name") or row.get("name") or "").strip()
                _id = (row.get("id") or "").strip()
                if name and _id:
                    self._index[normalize_title(name)] = _id

    def resolve(self, name: str) -> CountryMatch:
        if not self._loaded:
            self.load()
        _id = self._index.get(normalize_title(name))
        return CountryMatch(name=name, id=_id, matched=_id is not None)

    def resolve_all(self, names: list[str]) -> list[CountryMatch]:
        return [self.resolve(n) for n in names]

    def ids_for(self, names: list[str]) -> list[str]:
        """Resolved FW country IDs for a list of names (unmatched dropped)."""
        return [m.id for m in self.resolve_all(names) if m.id]


# Country NAME -> ISO code. regions.yaml lists country NAMES; FreeWheel's state/dma/city
# tables key geography by ISO country code, so we bridge the two to scope sub-country geo
# resolution to a region's footprint. Keep in sync with scripts/sync_geo.py.
NAME_TO_ISO = {
    "United States": "US", "Canada": "CA", "Australia": "AU", "Mexico": "MX",
    "Argentina": "AR", "Chile": "CL", "Colombia": "CO", "Peru": "PE", "Brazil": "BR",
    "United Kingdom": "GB", "Ireland": "IE", "France": "FR", "Italy": "IT",
    "Germany": "DE", "Switzerland": "CH", "Austria": "AT", "Finland": "FI",
    "Denmark": "DK", "Norway": "NO", "Sweden": "SE", "Spain": "ES",
}


@dataclass
class GeoMatch:
    query: str
    id: Optional[str]
    label: str = ""

    @property
    def matched(self) -> bool:
        return self.id is not None


class GeoResolver:
    """Resolve state / DMA / city NAMES a CM enters -> FreeWheel geo IDs.

    Sub-country geo is written on a placement as
    ``geography_targeting.include.{state,dma,city}`` using the numeric FreewheelID from
    FreeWheel's Geography Dataset (see scripts/sync_geo.py). Names never reach the API.

    - **State** is scoped by ISO country (a region maps to its countries' ISO codes) — the
      same 2-letter code ("CA") means California under US and a province under CA, so we
      never resolve a state without a country scope.
    - **DMA** is a US-only Nielsen concept; matched by DMA number ("501") or name.
    - **City** names are wildly ambiguous ("Springfield" is in 30+ states), so a city is
      entered as ``"City, ST"`` and resolved within the region's ISO set + that state.

    Raw numeric IDs always pass through unchanged (back-compat / power users).
    """

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        # state: (iso, key) -> id, where key is the normalized code or name
        self._state: dict[tuple[str, str], str] = {}
        # (iso, state_id) -> state code, for building "City, ST" scopes and form labels
        self._state_code_by_id: dict[tuple[str, str], str] = {}
        self._states_by_iso: dict[str, list[dict]] = {}
        self._dma: dict[str, str] = {}         # normalized code/name -> id
        self._dmas: list[dict] = []            # ordered [{id, code, name}] for the form
        self._city_loaded = False
        self._city: dict[tuple[str, str, str], str] = {}   # (iso, state_id, name) -> id
        self._loaded = False

    # -- loading -----------------------------------------------------------------
    def load(self) -> "GeoResolver":
        self._load_states()
        self._load_dmas()
        self._loaded = True
        return self

    def _load_states(self) -> None:
        path = self.data_dir / "state.csv"
        if not path.exists():
            return
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                iso, fid = r["country_iso"].strip(), r["fw_id"].strip()
                code, name = r["code"].strip(), r["name"].strip()
                if not (iso and fid):
                    continue
                if code:
                    self._state[(iso, normalize_title(code))] = fid
                if name:
                    self._state[(iso, normalize_title(name))] = fid
                self._state_code_by_id[(iso, fid)] = code
                self._states_by_iso.setdefault(iso, []).append(
                    {"id": fid, "code": code, "name": name})

    def _load_dmas(self) -> None:
        path = self.data_dir / "dma.csv"
        if not path.exists():
            return
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                fid, code, name = r["fw_id"].strip(), r["dma_code"].strip(), r["name"].strip()
                if not fid:
                    continue
                if code:
                    self._dma[normalize_title(code)] = fid
                if name:
                    self._dma[normalize_title(name)] = fid
                    # also index the city part before the ", ST" suffix ("New York")
                    head = name.rsplit(",", 1)[0].strip()
                    self._dma.setdefault(normalize_title(head), fid)
                self._dmas.append({"id": fid, "code": code, "name": name})

    def _load_cities(self) -> None:
        """City is big (200k+ rows) — load lazily, only when a plan targets cities."""
        if self._city_loaded:
            return
        path = self.data_dir / "city.csv"
        if path.exists():
            with path.open(encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    self._city[(r["country_iso"].strip(), r["state_fw_id"].strip(),
                                normalize_title(r["name"].strip()))] = r["fw_id"].strip()
        self._city_loaded = True

    # -- region helpers ----------------------------------------------------------
    @staticmethod
    def isos_for_countries(country_names: list[str]) -> list[str]:
        return [iso for iso in (NAME_TO_ISO.get(n) for n in country_names) if iso]

    def states_for(self, isos: list[str]) -> list[dict]:
        """Form picker options: [{id, code, name}] for the given ISO countries."""
        if not self._loaded:
            self.load()
        out: list[dict] = []
        for iso in isos:
            for s in self._states_by_iso.get(iso, []):
                out.append({**s, "iso": iso})
        return out

    def dmas(self) -> list[dict]:
        if not self._loaded:
            self.load()
        return list(self._dmas)

    # -- resolution --------------------------------------------------------------
    def resolve_states(self, isos: list[str], values: list[str]) -> list[GeoMatch]:
        if not self._loaded:
            self.load()
        out: list[GeoMatch] = []
        for v in values:
            q = str(v).strip()
            if q.isdigit():
                out.append(GeoMatch(q, q, q))
                continue
            fid = next((self._state[(iso, normalize_title(q))]
                        for iso in isos if (iso, normalize_title(q)) in self._state), None)
            out.append(GeoMatch(q, fid, q))
        return out

    def resolve_dmas(self, values: list[str]) -> list[GeoMatch]:
        if not self._loaded:
            self.load()
        out: list[GeoMatch] = []
        for v in values:
            q = str(v).strip()
            if q.isdigit() and q not in self._dma:  # a raw FW id, not a DMA number
                # DMA numbers ARE digits too; treat 3-digit 5xx as a DMA code first.
                pass
            key = normalize_title(q)
            fid = self._dma.get(key)
            if fid is None and q.isdigit():
                fid = q  # raw FW geo id passthrough
            out.append(GeoMatch(q, fid, q))
        return out

    def resolve_cities(self, isos: list[str], values: list[str]) -> list[GeoMatch]:
        """Each value is "City, ST" (or a raw FW city id). ST scopes the ambiguity."""
        self._load_cities()
        out: list[GeoMatch] = []
        for v in values:
            q = str(v).strip()
            if q.isdigit():
                out.append(GeoMatch(q, q, q))
                continue
            if "," not in q:
                out.append(GeoMatch(q, None, q))   # need a state qualifier
                continue
            city_part, st = (p.strip() for p in q.rsplit(",", 1))
            fid = None
            for iso in isos:
                sid = self._state.get((iso, normalize_title(st)))
                if not sid:
                    continue
                fid = self._city.get((iso, sid, normalize_title(city_part)))
                if fid:
                    break
            out.append(GeoMatch(q, fid, q))
        return out
