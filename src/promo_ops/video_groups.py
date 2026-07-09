"""Genre -> FreeWheel Video Group resolver (Tier 3 / guaranteed "Genre").

Genre targeting is done via Video Groups named "VG: Genre: <genre>" (e.g.
"VG: Genre: Western", "VG: Genre: Crime Drama"), written to
content_targeting.network_items.include.set[].video_group. This is how Dutton
Ranch targets genre — not via Standard Attributes (which don't persist).

The Video Group list (`list-video-groups`, ~638k) has no name filter, so — like
Series/Site Groups — the genre subset is synced once (FreeWheelClient
.sync_genre_video_groups -> data/video_groups) and matched locally by the genre
name after the "VG: Genre: " prefix. A committed seed covers offline/tests.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .audience_segments import normalize_title
from .config import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "video_groups"
PREFIX = "VG: Genre: "


@dataclass
class GenreMatch:
    genre: str
    video_groups: list[dict] = field(default_factory=list)   # [{id, name}]

    @property
    def matched(self) -> bool:
        return bool(self.video_groups)


class GenreVideoGroupResolver:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self._by_genre: dict[str, list[dict]] = {}   # normalized genre -> [{id,name}]
        self._loaded = False

    def load(self) -> "GenreVideoGroupResolver":
        self._by_genre = {}
        seen: set[str] = set()
        if self.data_dir.exists():
            for path in sorted(self.data_dir.glob("*.csv")):
                self._load_csv(path, seen)
        self._loaded = True
        return self

    def _load_csv(self, path: Path, seen: set[str]) -> None:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                _id = (row.get("id") or "").strip()
                name = (row.get("name") or "").strip()
                if not (_id and name) or _id in seen or not name.startswith(PREFIX):
                    continue
                seen.add(_id)
                genre = normalize_title(name[len(PREFIX):])
                self._by_genre.setdefault(genre, []).append({"id": _id, "name": name})

    def resolve(self, genre: str) -> GenreMatch:
        if not self._loaded:
            self.load()
        return GenreMatch(genre=genre,
                          video_groups=list(self._by_genre.get(normalize_title(genre), [])))

    def ids_for(self, genres: list[str]) -> list[str]:
        out, seen = [], set()
        for g in genres:
            for vg in self.resolve(g).video_groups:
                if vg["id"] not in seen:
                    seen.add(vg["id"]); out.append(vg["id"])
        return out
