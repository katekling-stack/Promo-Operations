"""FreeWheel Site Group resolver — Pluto TV channels & promo categories.

Pluto targeting is done via FreeWheel **Site Groups** named by convention
(config/pluto.yaml):

  Tier 2 channels:            "SG: PlutoTV Channels: {region}: {name}"
  Tier 3 promo (domestic):    "SG: PlutoTV Promo Category: {name}: {region}"
  Tier 3 category (intl):     "SG: PlutoTV Category: {name}: {region}"

On the placement they write to `content_targeting.network_items.include.sets[].
site_group` (int64 IDs).

Like Video Series, the team searches by keyword and **selects all** matches
(e.g. "Westerns" -> "Classic Movie Westerns", "Pluto TV Westerns 2", ...), letting
delivery run against whichever are correct. So resolution here is a keyword
select-all within a scope (a fixed name prefix + optional suffix that pin the
Pluto section + region), not an exact-name lookup.

Source: Site API v4 `list-site-groups`, filtered to the `SG: PlutoTV` set and
exported by `FreeWheelClient.sync_site_groups()`; a committed seed
(data/site_groups/seed_site_groups.csv) makes it work offline. "DO NOT USE"
entries are skipped.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "site_groups"


def _norm(s: str) -> str:
    """Normalize a site-group name/keyword for tolerant matching.

    Handles the punctuation variants seen in the live data so keywords match:
      * & / + / the word "and" are equivalent and dropped
        ("History & Science" == "History + Science"; "Law & Order" == "Law and Order")
      * dots are stripped ("S.W.A.T." == "SWAT")
      * ":" is a separator; whitespace is collapsed (tolerates no/double space after colon)
    """
    s = (s or "").lower()
    s = s.replace(".", "")
    s = re.sub(r"[&+:]", " ", s)
    s = re.sub(r"\band\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class SiteGroupMatch:
    keyword: str
    site_groups: list[dict] = field(default_factory=list)  # [{id, name}]

    @property
    def matched(self) -> bool:
        return bool(self.site_groups)


class SiteGroupResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._rows: list[dict] = []          # [{name, id, norm}]
        self._loaded = False

    def load(self) -> "SiteGroupResolver":
        self._rows = []
        seen: set[str] = set()
        if self.data_dir.exists():
            for path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(path, seen)
        self._loaded = True
        return self

    def _load_csv(self, path: Path, seen: set[str]) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("name") or "").strip()
                _id = (row.get("id") or "").strip()
                if not (name and _id) or _id in seen:
                    continue
                low = name.lower()
                if "do not use" in low or re.search(r"\btest\b", low):
                    continue   # skip DNU + Test site groups (never target Test channels)
                seen.add(_id)
                self._rows.append({"name": name, "id": _id, "norm": _norm(name)})

    def select_all(self, keyword: str, prefix: str = "", suffix: str = "") -> SiteGroupMatch:
        """All site groups in scope (prefix..suffix) whose name contains keyword.

        Mirrors the UI workflow: search the keyword within the Pluto section and
        select every match.
        """
        if not self._loaded:
            self.load()
        npre, nsuf, nkw = _norm(prefix), _norm(suffix), _norm(keyword)
        out = []
        for r in self._rows:
            n = r["norm"]
            if npre and not n.startswith(npre):
                continue
            if nsuf and not n.endswith(nsuf):
                continue
            if nkw and nkw not in n:
                continue
            out.append({"id": r["id"], "name": r["name"]})
        return SiteGroupMatch(keyword=keyword, site_groups=out)

    def select_exact(self, keyword: str, prefix: str = "", suffix: str = "") -> SiteGroupMatch:
        """Site groups whose name is EXACTLY prefix + keyword + suffix (normalized) —
        used for SELF-EXCLUSION of a promoted show's own Channel SG, so only the
        channel named for the title is excluded (not every channel containing the
        title words)."""
        if not self._loaded:
            self.load()
        target = _norm(f"{prefix}{keyword}{suffix}")
        out = [{"id": r["id"], "name": r["name"]} for r in self._rows if r["norm"] == target]
        return SiteGroupMatch(keyword=keyword, site_groups=out)
