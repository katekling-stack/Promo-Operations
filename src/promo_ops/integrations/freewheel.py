"""FreeWheel Streaming Hub client — verified against the live API.

Transport and object model were confirmed read-only against shmcp.freewheel.com
(production network 520311). See docs/FREEWHEEL.md for the full findings.

  Auth:      OAuth 2.1 PKCE (register -> authorize+csrf -> login -> token) -> JWT
  Transport: POST /mcp JSON-RPC; call `invoke_tool` with {tool_name, parameters}
  Hierarchy: Advertiser -> Campaign -> Insertion Order -> Placement (per Tier)

Reads (find_advertisers, resolve_campaign_id, get_insertion_order, list_placements)
are verified working. Writes (create IO / placement) build the confirmed field sets;
the placement *targeting* body is the one remaining item to capture before a live
targeted create — marked `# TODO(targeting)`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from ..config import env, require_env
from ..models import Order
from ..retry import TransientAPIError, is_transient_status, with_retries

HUB_URL = "https://shmcp.freewheel.com"
REDIRECT_URI = "http://localhost/callback"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class FreeWheelClient:
    def __init__(self):
        self.hub_url = env("FREEWHEEL_HUB_URL", HUB_URL).rstrip("/")
        self.network_id = require_env("FREEWHEEL_NETWORK_ID")
        self.environment = env("FREEWHEEL_ENVIRONMENT", "production")  # production|staging
        self._username = require_env("FREEWHEEL_USERNAME")
        self._password = require_env("FREEWHEEL_PASSWORD")
        self.advertiser_filter = env("FREEWHEEL_ADVERTISER_NAME_FILTER", "VCBS")
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "promo-ops/0.1"
        self._token: Optional[str] = None
        self._tool_name_cache: dict[str, str] = {}
        # Retry transient failures (network blips, 429/5xx) with backoff; NOT 4xx.
        self._retry_attempts = int(env("FREEWHEEL_RETRY_ATTEMPTS", "4"))
        self._retry_base_delay = float(env("FREEWHEEL_RETRY_BASE_DELAY", "2"))
        self._sleep = time.sleep   # injectable in tests

    # --- auth (OAuth 2.1 PKCE) ------------------------------------------ #

    @staticmethod
    def _auth_json(resp: "requests.Response", step: str) -> dict:
        """Parse an auth-step response as JSON with a clear error on failure. A transient
        gateway status (429/5xx — e.g. FreeWheel's hub returning a 502 'Bad Gateway' HTML
        page during an outage) becomes a retryable TransientAPIError so with_retries backs
        off, instead of a raw JSONDecodeError on the HTML body."""
        if is_transient_status(resp.status_code):
            raise TransientAPIError(
                resp.status_code,
                f"FreeWheel login service is temporarily unavailable at {step} "
                f"(HTTP {resp.status_code}) — try again shortly")
        try:
            return resp.json()
        except ValueError:
            raise RuntimeError(
                f"FreeWheel {step} returned an unexpected non-JSON response "
                f"(HTTP {resp.status_code}): {resp.text[:120]!r}")

    def authenticate(self) -> str:
        s = self._session
        client_id = self._auth_json(s.post(
            f"{self.hub_url}/oauth/register",
            json={"client_name": "promo-ops", "redirect_uris": [REDIRECT_URI],
                  "grant_types": ["authorization_code", "refresh_token"],
                  "response_types": ["code"], "token_endpoint_auth_method": "none"},
            timeout=30), "register")["client_id"]

        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = _b64url(secrets.token_bytes(12))

        r = s.get(f"{self.hub_url}/oauth/authorize", params={
            "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state},
            allow_redirects=True, timeout=30)
        csrf = parse_qs(urlparse(r.url).query).get("csrf_token", [None])[0]

        r = s.post(f"{self.hub_url}/oauth/login", data={
            "username": self._username, "password": self._password,
            "environment": self.environment, "csrf_token": csrf},
            allow_redirects=False, timeout=30)
        if is_transient_status(r.status_code):
            raise TransientAPIError(
                r.status_code, f"FreeWheel login service is temporarily unavailable "
                f"(HTTP {r.status_code}) — try again shortly")
        code, loc, hops = None, r.headers.get("Location"), 0
        while loc and hops < 5:
            if "code=" in loc:
                code = parse_qs(urlparse(loc).query).get("code", [None])[0]
                break
            r = s.get(urljoin(self.hub_url, loc), allow_redirects=False, timeout=30)
            loc, hops = r.headers.get("Location"), hops + 1
        if not code:
            raise RuntimeError("FreeWheel login failed (no auth code). Check credentials/environment.")

        tok = self._auth_json(s.post(f"{self.hub_url}/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
            "client_id": client_id, "code_verifier": verifier}, timeout=30), "token")
        self._token = tok.get("access_token")
        if not self._token:
            raise RuntimeError(f"FreeWheel token exchange failed: {tok}")
        self._mcp("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "promo-ops", "version": "0.1"}})
        return self._token

    def _ensure_auth(self) -> None:
        if not self._token:
            self.authenticate()

    # --- MCP transport --------------------------------------------------- #

    def _mcp(self, method: str, params: dict, id_: int = 1) -> Any:
        resp = self._session.post(
            f"{self.hub_url}/mcp",
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params},
            timeout=60)
        text = resp.text
        if text.startswith("event:") or "data:" in text[:24]:
            m = re.search(r"data:\s*(\{.*\})", text)
            return json.loads(m.group(1)) if m else text
        return resp.json()

    def _invoke(self, tool_name: str, **parameters: Any) -> Any:
        """Call an API tool via invoke_tool; unwrap the {ok,data} payload. Retries
        transient failures (connection/timeout, 429/5xx) with backoff; 4xx (e.g. 422
        validation / IO-limit) raise immediately."""
        def call() -> Any:
            self._ensure_auth()
            r = self._mcp("tools/call", {"name": "invoke_tool",
                                         "arguments": {"tool_name": tool_name, "parameters": parameters}})
            try:
                out: Any = json.loads(r["result"]["content"][0]["text"])
            except (KeyError, TypeError, json.JSONDecodeError):
                out = r
            if isinstance(out, dict) and out.get("ok") is False \
                    and is_transient_status(out.get("status_code")):
                raise TransientAPIError(out.get("status_code"), out.get("error"))
            return out

        return with_retries(
            call, attempts=self._retry_attempts, base_delay=self._retry_base_delay,
            retry_on=lambda e: isinstance(e, (TransientAPIError, requests.exceptions.RequestException)),
            sleep=self._sleep)

    @staticmethod
    def _rows(payload: dict, plural: str) -> list[dict]:
        """Normalize a V3 list payload: data.<plural>.<singular> -> list."""
        data = (payload or {}).get("data", {})
        coll = data.get(plural, {}) if isinstance(data, dict) else {}
        if isinstance(coll, dict):
            for v in coll.values():
                if isinstance(v, list):
                    return v
                if isinstance(v, dict) and "id" in v:
                    return [v]
        return []

    # --- reads (verified) ------------------------------------------------ #

    def find_advertisers(self, name_contains: Optional[list[str]] = None) -> list[dict[str, Any]]:
        fragments = name_contains or [self.advertiser_filter]
        payload = self._invoke("sh_1_1_list-advertisers", name=fragments[0], per_page=50)
        return [a for a in self._rows(payload, "advertisers")
                if all(f.lower() in str(a.get("name", "")).lower() for f in fragments)]

    def resolve_campaign_id(self, name: str) -> Optional[str]:
        """Find an existing campaign id by exact name (the IO's parent).

        Query with the FULL name first: the API's `name` filter narrows the result set,
        so the exact campaign isn't truncated by the page cap. (The brand prefix alone —
        e.g. "Paramount +" — overflows 50 rows, dropping later regions like GSA/IT/FR.)
        Falls back to the brand-prefix sweep for older/edge naming."""
        name = name.strip()
        for query in (name, name.split(" - ")[0]):
            payload = self._invoke("sh_1_1_list-campaigns", name=query, per_page=100)
            for c in self._rows(payload, "campaigns"):
                if str(c.get("name", "")).strip() == name:
                    return str(c.get("id"))
        return None

    def list_campaigns_by_name(self, name_prefix: str, per_page: int = 100) -> list[dict[str, Any]]:
        """Campaigns whose name matches a prefix (the API's `name` filter is honored;
        its `advertiser_id`/`page` filters are not, so we discover by brand prefix)."""
        payload = self._invoke("sh_1_1_list-campaigns", name=name_prefix, per_page=per_page)
        return self._rows(payload, "campaigns")

    # Brand-name prefixes to sweep — union covers every promo brand family. Some
    # broad prefixes overflow the API's 50-row page, so we also sweep finer prefixes
    # (e.g. "Paramount + - Kids"); results union+dedupe, so overlap is harmless.
    BRAND_PREFIXES = (
        "Paramount +", "Paramount + - Kids", "Paramount Pictures",
        "Paramount Pictures - Kids", "Paramount Consumer", "Pluto TV",
        "Pluto TV - Kids", "Nick", "Nick - Kids", "Nick Jr", "Nickelodeon",
        "CBS", "CBS News", "CBS Sports", "CBS Network", "BET", "BET Media", "MTVE")

    def discover_brand_campaigns(self, prefixes: Optional[tuple[str, ...]] = None
                                 ) -> list[dict[str, Any]]:
        """Sweep campaigns by brand-name prefix -> the raw material for a brand sync.

        The Streaming Hub `list-campaigns` tool honors the `name` filter but ignores
        `advertiser_id`/`page`, so we query each brand prefix and union the results
        (deduped by name). Returns {name, id} rows; brand_sync.reconcile() filters
        out non-brand noise and diffs against config. Read-only.
        """
        seen: dict[str, dict[str, Any]] = {}
        for prefix in (prefixes or self.BRAND_PREFIXES):
            for c in self.list_campaigns_by_name(prefix):
                name = (c.get("name") or "").strip()
                if name:
                    seen.setdefault(name, {"name": name, "id": c.get("id")})
        return list(seen.values())

    def get_insertion_order(self, io_id: str) -> dict[str, Any]:
        return self._invoke("sh_1_1_get-a-insertion-order", insertion_order_id=int(io_id))

    def find_insertion_order_by_name(self, campaign_id: str, name: str,
                                     max_pages: int = 6, per_page: int = 100) -> Optional[str]:
        """Return the id of an existing IO with this exact name under the campaign, else
        None. Used for idempotency — so re-processing a Case doesn't create a duplicate
        IO. Paginates (a campaign can hold up to 500 IOs)."""
        target = (name or "").strip()
        if not target:
            return None
        for page in range(1, max_pages + 1):
            payload = self._invoke("sh_1_1_list-insertion-orders-of-a-campaign",
                                   campaign_id=int(campaign_id), per_page=per_page, page=page)
            rows = self._rows(payload, "insertion_orders")
            if not rows:
                break
            for io in rows:
                if str(io.get("name", "")).strip() == target:
                    return str(io.get("id"))
            if len(rows) < per_page:
                break
        return None

    def list_placements(self, io_id: str) -> list[dict[str, Any]]:
        payload = self._invoke("sh_1_1_list-insertion-order-placements",
                               insertion_order_id=int(io_id), per_page=50)
        return self._rows(payload, "placements")

    def search_series(self, show: str, per_page: int = 50) -> list[dict[str, Any]]:
        """Keyword-search series by name; return ALL matches ({id, name}).

        Per ops workflow: select every match for the keyword and let delivery run
        against whichever are correct — no exact match needed.
        """
        payload = self._invoke("sh_1_0_liststandardseries", name=show, per_page=per_page)
        return (payload or {}).get("data", {}).get("series", [])

    def resolve_showlist(self, shows: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Keyword-resolve a whole showlist to all matching series (select-all)."""
        return {show: self.search_series(show) for show in shows}

    def sync_audience_items(self, out_dir: Optional[str] = None, max_pages: int = 200) -> str:
        """Paginate all audience items into a synced CSV (name,id,external_id).

        Feeds Tier 1 DDA resolution ("GL-DDA-1P-SHOW_<Show>"). The API has no name
        filter, so we sync the full set (~6k) once and match locally.
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..audience_segments import DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        path = out / "synced_audience_items.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["show", "segment_name", "segment_id", "platform", "region", "source"])
            page, total_pages, empty_retries = 1, None, 0
            while page <= max_pages:
                payload = self._invoke("sh_1_0_list-audience-items", page=page, per_page=50)
                ai = (((payload or {}).get("data") or {}).get("AudienceItemsResp") or {}).get("audience_items") or {}
                items = ai.get("items") or ai.get("audience_item") or []
                if isinstance(items, dict):
                    items = [items]
                if total_pages is None:
                    try:
                        total_pages = int(ai.get("@total_page")) if ai.get("@total_page") else None
                    except (TypeError, ValueError):
                        total_pages = None
                if not items:
                    # Retry a transient empty page a few times before giving up.
                    if empty_retries < 3 and (total_pages is None or page <= total_pages):
                        empty_retries += 1
                        continue
                    break
                empty_retries = 0
                for it in items:
                    name = it.get("name", "")
                    # Show name inferred from GL-DDA-1P-SHOW_<Show> convention.
                    show = name.split("SHOW_", 1)[1].replace("_", " ") if "SHOW_" in name else ""
                    w.writerow([show, name, it.get("id"), "DDA", "", "audience_items"])
                if total_pages and page >= total_pages:
                    break
                page += 1
        return str(path)

    def list_standard_attributes(self) -> dict[str, Any]:
        """Return the full Standard Attributes taxonomy (genres, brands, channels...)."""
        payload = self._invoke("sh_1_0_liststandardattributes")
        return (payload or {}).get("data", {}).get("standard_attributes", {})

    def sync_standard_attributes(self, out_dir: Optional[str] = None) -> list[str]:
        """Write synced_<type>.csv (columns type,name,id) for every attribute type."""
        import csv as _csv
        from pathlib import Path as _Path
        from ..standard_attributes import DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        written = []
        for attr_type, coll in self.list_standard_attributes().items():
            rows = []
            if isinstance(coll, dict):
                for v in coll.values():
                    if isinstance(v, list):
                        rows = v
                        break
            if not rows:
                continue
            path = out / f"synced_{attr_type}.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                w = _csv.writer(fh)
                w.writerow(["type", "name", "id"])
                for item in rows:
                    if isinstance(item, dict) and item.get("id") and item.get("name"):
                        w.writerow([attr_type, item["name"], item["id"]])
            written.append(str(path))
        return written

    def sync_countries(self, out_dir: Optional[str] = None) -> str:
        """Export the FW country table (name -> id) for geo targeting.

        Source: Standard Attributes taxonomy type `content_territories`, verified to
        match the MRM "Add New Country" IDs exactly (United States=165, Canada=27,
        Australia=10, Brazil=21). Feeds CountryResolver so a region's country NAMES
        (config/regions.yaml) resolve to the int64 IDs the Placement API requires.
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..geo import DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        coll = self.list_standard_attributes().get("content_territories", {})
        if isinstance(coll, dict):
            for v in coll.values():
                if isinstance(v, list):
                    rows = v
                    break
        rows = [r for r in rows if r.get("id") and r.get("country_name")]
        rows.sort(key=lambda r: str(r["country_name"]).lower())
        path = out / "synced_countries.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["country_name", "id", "source"])
            for r in rows:
                w.writerow([r["country_name"], r["id"], "content_territories"])
        return str(path)

    def sync_ad_units(self, out_dir: Optional[str] = None, max_pages: int = 60) -> str:
        """Export standard + custom ad units (name -> id) for ad_product assignment.

        Source: Ad Unit API v4 `list-standard-and-custom-ad-units` (~197 units). Feeds
        AdUnitResolver so config ad-unit NAMES (config/ad_units.yaml) resolve to the
        int64 IDs `ad_product.ad_unit_node[].ad_unit_id` requires.
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..ad_units import DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        rows, page = [], 1
        while page <= max_pages:
            res = self._invoke("sh_1_0_list-standard-and-custom-ad-units",
                               show="all", per_page=50, page=page)
            au = (res or {}).get("data", {}).get("ad_units", {})
            items = au.get("ad_unit", [])
            if isinstance(items, dict):
                items = [items]
            if not items:
                break
            rows += items
            if page >= int(au.get("@total_pages", "1") or 1):
                break
            page += 1
        rows = [r for r in rows if r.get("id") and r.get("name")]
        rows.sort(key=lambda r: str(r["name"]).lower())
        path = out / "synced_ad_units.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["name", "id", "status", "source"])
            for r in rows:
                w.writerow([r["name"], r["id"], r.get("status", ""), "ad_unit_api_v4"])
        return str(path)

    def sync_site_groups(self, out_dir: Optional[str] = None, name_prefix: str = "SG: PlutoTV",
                         per_page: int = 500, max_pages: int = 80) -> str:
        """Export the Pluto Site Groups (name -> id) for Tier 2/3 targeting.

        Source: Site API v4 `list-site-groups` (~33k total; filtered to `name_prefix`,
        ~14k SG: PlutoTV). Feeds SiteGroupResolver so Pluto channel/category keywords
        resolve (select-all) to the site_group IDs written to
        content_targeting.network_items.include.sets[].site_group.
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..site_groups import DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        kept, page, total_pages = [], 1, None
        while page <= max_pages:
            r = self._invoke("sh_1_0_list-site-groups", per_page=per_page, page=page)
            sg = (r or {}).get("data", {}).get("site_groups", {})
            items = sg.get("site_group", [])
            if isinstance(items, dict):
                items = [items]
            if total_pages is None:
                try:
                    total_pages = int(sg.get("@total_page"))
                except (TypeError, ValueError):
                    total_pages = None
            if not items:
                break
            for it in items:
                nm = str(it.get("name", ""))
                if nm.startswith(name_prefix):
                    kept.append(it)
            if total_pages and page >= total_pages:
                break
            page += 1
        kept.sort(key=lambda it: str(it.get("name", "")).lower())
        path = out / "synced_site_groups.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["name", "id", "status", "external_id", "source"])
            for it in kept:
                w.writerow([it.get("name"), it.get("id"), it.get("status"),
                            it.get("external_id"), "site_group_api_v4"])
        return str(path)

    def sync_series(self, out_dir: Optional[str] = None, per_page: int = 500,
                    max_pages: int = 600) -> str:
        """Export the Video Series index (id -> name) for Tier 2 series targeting.

        Source: Video API v4 `list-series` (~229k, the Asset Group namespace the
        placement `series` field requires). No name filter, so we sync the full index
        once and keyword select-all locally (SeriesResolver). Re-auths on transient
        errors. Writes data/series/synced_series.csv (git-ignored; large).
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..series import DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        path = out / "synced_series.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["id", "name", "status"])
            page, total_pages, n = 1, None, 0
            while page <= max_pages:
                try:
                    r = self._invoke("sh_1_0_list-series", per_page=per_page, page=page)
                except Exception:
                    self.authenticate()
                    continue
                d = (r or {}).get("data", {}).get("serieses", {})
                ser = d.get("series", [])
                if isinstance(ser, dict):
                    ser = [ser]
                if total_pages is None:
                    try:
                        total_pages = int(d.get("@total_page"))
                    except (TypeError, ValueError):
                        total_pages = None
                if not ser:
                    break
                for s in ser:
                    if s.get("id") and s.get("name"):
                        w.writerow([s["id"], s["name"], s.get("status", "")])
                        n += 1
                if total_pages and page >= total_pages:
                    break
                page += 1
        return str(path)

    def sync_genre_video_groups(self, out_dir: Optional[str] = None, per_page: int = 500,
                                max_pages: int = 30, stop_after_empty: int = 3) -> str:
        """Export the genre Video Groups ("VG: Genre: ...") for Tier 3 / guaranteed.

        Source: Video API v4 `list-video-groups` sorted OLDEST-first — the curated
        "VG: Genre:" set (domestic + regional) was created early, so it lands in the
        first pages. Sorting oldest-first also avoids the pagination-drift that a full
        newest-first scan suffers while new video groups are being created. Stops after
        `stop_after_empty` consecutive pages with no genre VGs. Feeds
        GenreVideoGroupResolver. Writes data/video_groups/synced_genre_video_groups.csv.
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..video_groups import DATA_DIR, PREFIX

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        path = out / "synced_genre_video_groups.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["id", "name", "status"])
            page, empty_streak = 1, 0
            while page <= max_pages and empty_streak < stop_after_empty:
                try:
                    r = self._invoke("sh_1_0_list-video-groups", per_page=per_page,
                                     page=page, sort="created_at")
                except Exception:
                    self.authenticate()
                    continue
                vg = (r or {}).get("data", {}).get("video_groups", {}).get("video_group", [])
                if isinstance(vg, dict):
                    vg = [vg]
                if not vg:
                    break
                found = 0
                for g in vg:
                    if str(g.get("name", "")).startswith(PREFIX) and g.get("id"):
                        w.writerow([g["id"], g["name"], g.get("status", "")])
                        found += 1
                empty_streak = empty_streak + 1 if found == 0 else 0
                page += 1
        return str(path)

    def sync_brand_video_groups(self, out_dir: Optional[str] = None, per_page: int = 500,
                                max_pages: int = 40, stop_after_empty: int = 8) -> str:
        """Export the brand / business-division Video Groups ("VG: Biz Div-Brand: ...")
        offered under the Genre picker for network/brand targeting (e.g. "VG: Biz Div-Brand:
        VCBS: Cable Adults: BET").

        Same source + oldest-first strategy as sync_genre_video_groups — this curated set
        was created early, so it lands in the first pages. Feeds GenreVideoGroupResolver
        (the "Brand: ..." keys). Writes data/video_groups/synced_brand_video_groups.csv.
        """
        import csv as _csv
        from pathlib import Path as _Path
        from ..video_groups import BRAND_PREFIX, DATA_DIR

        out = _Path(out_dir) if out_dir else DATA_DIR
        out.mkdir(parents=True, exist_ok=True)
        path = out / "synced_brand_video_groups.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["id", "name", "status"])
            page, empty_streak = 1, 0
            while page <= max_pages and empty_streak < stop_after_empty:
                try:
                    r = self._invoke("sh_1_0_list-video-groups", per_page=per_page,
                                     page=page, sort="created_at")
                except Exception:
                    self.authenticate()
                    continue
                vg = (r or {}).get("data", {}).get("video_groups", {}).get("video_group", [])
                if isinstance(vg, dict):
                    vg = [vg]
                if not vg:
                    break
                found = 0
                for g in vg:
                    if str(g.get("name", "")).startswith(BRAND_PREFIX) and g.get("id"):
                        w.writerow([g["id"], g["name"], g.get("status", "")])
                        found += 1
                empty_streak = empty_streak + 1 if found == 0 else 0
                page += 1
        return str(path)

    def get_campaign_template(self, campaign_id: str, io_id: Optional[str] = None) -> dict[str, Any]:
        out: dict[str, Any] = {"campaign_id": campaign_id}
        if io_id:
            out["insertion_order"] = self.get_insertion_order(io_id)
            out["placements"] = self.list_placements(io_id)
        return out

    # --- writes ---------------------------------------------------------- #

    def delete_insertion_order(self, io_id: str) -> dict[str, Any]:
        """Delete an IO. NOTE: this CASCADES to its placements (validated on test).

        Prefer this for cleanup — the direct placement DELETE currently errors
        ("json is not supported") via the gateway, but removing the IO removes its
        placements too.
        """
        return self._invoke("sh_1_1_delete-an-insertion-order", insertion_order_id=int(io_id))

    def create_order(self, order: Order, dry_run: bool = True) -> dict[str, Any]:
        """Create the Insertion Order + per-tier Placements under the parent campaign.

        dry_run=True (default) returns the exact calls it would make. dry_run=False
        resolves the campaign, creates the IO, then creates placements.

        Validated on the test network (520310): create-IO and create-placement accept
        JSON object bodies via the gateway; IO is created NOT_BOOKED (draft).
        """
        # On a live push, find-or-create the IO Brand (if the CM picked/typed one that
        # isn't already resolved) BEFORE building the plan, so exclusivity carries it.
        brand_note = None if dry_run else self._ensure_io_brand(order)
        plan = self.to_freewheel_plan(order)
        if dry_run:
            return {"dry_run": True, "planned_calls": plan}

        campaign_id = order.campaign.get("resolved_id") or self.resolve_campaign_id(
            order.campaign.get("name", ""))
        if not campaign_id:
            raise RuntimeError(
                f"Parent campaign {order.campaign.get('name')!r} not found. "
                f"Confirm the exact Advertiser + Campaign names.")

        # Add placements INTO an existing IO (no new IO) when routed there: a Scene Lift
        # target IO, or an explicit "add to existing IO" id (e.g. Season 2 -> Season 1 IO).
        append_io = getattr(order, "scene_lift_io_id", None) or getattr(order, "existing_io_id", None)
        if append_io:
            io_id = append_io
            io = {"append_to_existing_io": io_id}
        else:
            io = self._invoke("sh_1_1_create-an-insertion-order",
                              campaign_id=int(campaign_id), body=plan["insertion_order_body"])
            io_id = ((io.get("data") or {}).get("insertion_order") or {}).get("id")

        placements = []
        for body in plan["placement_bodies"]:
            b = {k: v for k, v in body.items() if not k.startswith("_")}  # drop reference-only keys
            b["insertion_order_id"] = io_id
            placements.append(self._invoke("sh_1_0_create-a-placement", body=b))
        out = {"campaign_id": campaign_id, "insertion_order": io, "placements": placements}
        if brand_note:
            out["brand"] = brand_note
        return out

    def _ensure_io_brand(self, order: Order) -> Optional[dict[str, Any]]:
        """Live find-or-create of the IO Brand when the CM picked/typed one that isn't
        already resolved to a synced brand_id. Sets order.brand_id and returns a note
        (created?, and whether the Global Mapping is missing so the team must create the
        global brand via 'Create a Brand in FW'). Returns None when there's nothing to do."""
        if not getattr(order, "io_brand", None) or order.brand_id:
            return None
        from .freewheel_mrm import FreeWheelMRMClient
        from ..brands_resolver import BrandResolver
        adv = BrandResolver().load().advertiser_for(order.region, bool(order.io_brand_kids))
        if not adv:
            return {"name": order.io_brand,
                    "warning": f"No (Promo) advertiser mapping for {order.region} "
                               f"(kids={order.io_brand_kids}); IO Brand left unset."}
        # IO-Brand mapping needs the MRM API (client-credentials). It's an enhancement, not
        # a requirement — if those creds aren't configured, skip the auto-map with a clear
        # note (the CM sets the Brand by hand in FW) rather than crashing the whole push.
        from ..config import env
        if not (env("FREEWHEEL_MRM_CLIENT_ID") and env("FREEWHEEL_MRM_CLIENT_SECRET")):
            return {"name": order.io_brand,
                    "warning": "MRM API credentials not set (FREEWHEEL_MRM_CLIENT_ID / "
                               "FREEWHEEL_MRM_CLIENT_SECRET); IO Brand left unset. Set the "
                               "Brand manually in FreeWheel, or add the creds to .env to "
                               "auto-map it."}
        mrm = FreeWheelMRMClient()
        industry_id = "5289" if order.io_brand_kids else None   # kids -> Industry Rating: G
        brand_id, created = mrm.find_or_create_brand(adv, order.io_brand, industry_id=industry_id)
        order.brand_id = brand_id
        note: dict[str, Any] = {"name": order.io_brand, "brand_id": brand_id,
                                "created": created, "advertiser_id": adv}
        if order.io_brand_kids:
            note["industry"] = "Rating: G"
        if not mrm.brand_global_mapping(adv, brand_id):
            note["global_mapping_missing"] = True
            note["action"] = (f"Global brand for {order.io_brand!r} not found — create it via "
                              f"'Create a Brand in FW' so FreeWheel auto-maps it by name.")
        return note

    def create_addon_order(self, campaign_id: str, io_name: str,
                           placement_bodies: list[dict], flight: Optional[dict] = None,
                           dry_run: bool = True) -> dict[str, Any]:
        """Create an IO + raw placement bodies (e.g. the Pluto Video Domination line)
        under an existing campaign. `placement_bodies` are ready create-placement dicts
        (from addons.build_video_domination). NOT_BOOKED draft, like create_order."""
        io_body: dict[str, Any] = {"name": io_name, "currency": "USD"}
        if flight and flight.get("start"):
            io_body["schedule"] = {"start_time": flight.get("start"), "end_time": flight.get("end")}
        if dry_run:
            return {"dry_run": True, "campaign_id": campaign_id,
                    "insertion_order_body": io_body, "placement_bodies": placement_bodies}
        io = self._invoke("sh_1_1_create-an-insertion-order",
                          campaign_id=int(campaign_id), body=io_body)
        io_id = ((io.get("data") or {}).get("insertion_order") or {}).get("id")
        placements = []
        for body in placement_bodies:
            b = {k: v for k, v in body.items() if not k.startswith("_")}
            b["insertion_order_id"] = io_id
            placements.append(self._invoke("sh_1_0_create-a-placement", body=b))
        return {"campaign_id": campaign_id, "insertion_order": io, "placements": placements}

    @staticmethod
    def to_freewheel_plan(order: Order) -> dict[str, Any]:
        """Build the FreeWheel call plan from our Order (confirmed field sets)."""
        parent = {
            "advertiser": order.advertiser.get("name") or order.advertiser.get("name_contains"),
            "advertiser_id": order.advertiser.get("resolved_id"),
            "campaign_name": order.campaign.get("name"),
            "campaign_id": order.campaign.get("resolved_id"),
        }
        insertion_order_body = {   # confirmed IO fields (see docs/FREEWHEEL.md)
            "name": order.name,                       # e.g. "Frisco King - USA"
            # Brand: stamped when the plan picks one (resolved to the advertiser's FW
            # brand_id from the synced Brand list). Left BLANK when unset, for the CM to
            # map before booking. Left NOT_BOOKED (draft) on create — never auto-book.
            "currency": "USD",
            "schedule": {"start_time": order.flight.start, "end_time": order.flight.end},
        }
        if getattr(order, "brand_id", None):
            insertion_order_body["brand_id"] = str(order.brand_id)
        # Primary Trafficker — the submitting CM owns the draft they requested.
        if getattr(order, "primary_trafficker", None):
            insertion_order_body["primary_trafficker"] = order.primary_trafficker
        # Order-level frequency caps (delivery.frequency_cap array). Resolved by the
        # builder from kids/adult + region (kids 1/15min; adult 1/30min, +20/month USA).
        io_caps = [c for c in (FreeWheelClient._freq_cap_entry(s)
                               for s in (order.frequency_caps or [])) if c]
        if io_caps:
            insertion_order_body["delivery"] = {"frequency_cap": io_caps}
        placement_bodies = [FreeWheelClient._placement_body(p) for p in order.placements]
        # Custom Exclusivity: when the IO carries a Brand, every placement excludes that
        # Brand — Scope ALL_AD_UNITS for below-paying lines (standard + tiered remnant),
        # TARGETED_AD_UNITS_ONLY for guaranteed lines (pre-roll / bumper / lockdown / etc).
        # This also replaces FreeWheel's default (so the kids-only "Rating: G" industry
        # exclude is never carried through).
        if getattr(order, "brand_id", None):
            for p, body in zip(order.placements, placement_bodies):
                body["exclusivity"] = FreeWheelClient._exclusivity(
                    order.brand_id, bool(getattr(p, "guaranteed", False)))
        # Placement flighting schedule in the TARGET MARKET's time zone (regions.yaml).
        # FreeWheel takes the schedule at the placement level (the IO field is ignored).
        schedule = FreeWheelClient._placement_schedule(order.region, order.flight)
        if schedule:
            for body in placement_bodies:
                body.setdefault("schedule", dict(schedule))
        # Daypart (time-of-day) targeting in the market's time zone. Empty dayparts = 24/7
        # (no daypart_targeting emitted — the placement runs all day).
        daypart = FreeWheelClient._daypart_targeting(order.region, getattr(order, "dayparts", None))
        if daypart:
            for body in placement_bodies:
                body.setdefault("daypart_targeting", dict(daypart))
        out = {
            "parent": parent,
            "insertion_order_body": insertion_order_body,
            "placement_bodies": placement_bodies,
        }
        # Flag when placements append into an existing IO (Scene Lift or explicit).
        append_io = getattr(order, "scene_lift_io_id", None) or getattr(order, "existing_io_id", None)
        if append_io:
            out["append_to_existing_io"] = append_io
        return out

    @staticmethod
    def _region_timezone(region: Optional[str]) -> Optional[str]:
        from ..config import regions_config
        return (regions_config().get("regions", {}).get(region or "", {}) or {}).get("timezone")

    @staticmethod
    def _placement_schedule(region: Optional[str], flight) -> Optional[dict[str, Any]]:
        """Placement schedule {start_time, end_time, time_zone} in the market's time zone.
        Times are FW's 'YYYY-MM-DDTHH:MM' — a bare date becomes T00:00 (start) / T23:59
        (end). Returns None when there's no flight start (CM sets it) — never a partial."""
        start, end = getattr(flight, "start", None), getattr(flight, "end", None)
        tz = FreeWheelClient._region_timezone(region)
        if not start or not tz:
            return None
        # Start clock time in the market TZ (regions.yaml). USA = 03:00 (3 AM ET = 12 AM PT,
        # so it goes live West-to-East on the date); everywhere else defaults to midnight.
        from ..config import regions_config
        start_hm = ((regions_config().get("regions", {}).get(region or "", {}) or {})
                    .get("flight_start_time") or "00:00")

        def stamp(d: str, end_of_day: bool) -> str:
            d = str(d).strip()
            return d if "T" in d else f"{d}T{'23:59' if end_of_day else start_hm}"

        sched = {"start_time": stamp(start, False), "time_zone": tz}
        if end:
            sched["end_time"] = stamp(end, True)
        return sched

    @staticmethod
    def _daypart_targeting(region: Optional[str], dayparts) -> Optional[dict[str, Any]]:
        """FreeWheel daypart_targeting {time_zone, part:[{start_day,end_day,start_time,
        end_time}]} in the market's time zone. Empty/None dayparts -> None (= 24/7, field
        omitted so the placement runs all day)."""
        if not dayparts:
            return None
        tz = FreeWheelClient._region_timezone(region)
        parts = [{"start_day": w["start_day"], "end_day": w["end_day"],
                  "start_time": w["start_time"], "end_time": w["end_time"]}
                 for w in dayparts
                 if w.get("start_day") and w.get("end_day")
                 and w.get("start_time") and w.get("end_time")]
        if not parts:
            return None
        body: dict[str, Any] = {"part": parts}
        if tz:
            body["time_zone"] = tz
        return body

    @staticmethod
    def _parse_freq_cap(cap: Optional[str]) -> list[dict[str, Any]]:
        """'1 per 30 min' -> [{value:1, period:'30 minutes'}] (period tokens CONFIRM)."""
        if not cap:
            return []
        m = re.match(r"\s*(\d+)\s*per\s*(.+)", cap, re.I)
        if not m:
            return [{"value": 1, "period": cap}]
        return [{"value": int(m.group(1)), "period": m.group(2).strip(), "type": "IMPRESSION"}]

    # Minutes for a frequency-cap window ("1 per 30 min" -> 30). Mirrors the FW
    # delivery.frequency_cap.period (an integer number of minutes, as a string).
    # A "month" is 30 days (43200 min) — matches the "20 per month" cap on production USA
    # adult IOs (period "43200").
    _FC_UNIT_MIN = {"min": 1, "minute": 1, "hr": 60, "hour": 60, "day": 1440,
                    "week": 10080, "month": 43200, "mo": 43200}

    @staticmethod
    def _fc_period_minutes(cap: Optional[str]) -> Optional[str]:
        # Handles "1 per 30 min", "1 per hr" (implicit 1), "1 per 21 days", "20 per month".
        if not cap:
            return None
        m = re.search(r"per\s*(\d+)?\s*(minute|min|hour|hr|day|week|month|mo)s?", cap, re.I)
        if not m:
            return None
        qty = int(m.group(1)) if m.group(1) else 1
        return str(qty * FreeWheelClient._FC_UNIT_MIN[m.group(2).lower()])

    @staticmethod
    def _freq_cap_entry(cap: Optional[str]) -> Optional[dict[str, Any]]:
        """One human cap string -> a FreeWheel frequency_cap dict {value,type,period},
        matching the live format ({"value":"1","type":"IMPRESSION","period":"30"})."""
        period = FreeWheelClient._fc_period_minutes(cap)
        if not period:
            return None
        return {"value": FreeWheelClient._fc_value(cap), "type": "IMPRESSION", "period": period}

    @staticmethod
    def _fc_value(cap: Optional[str]) -> str:
        # The impression count before "per" ("2 per day" -> "2"; default "1").
        m = re.match(r"\s*(\d+)\s*per", cap or "", re.I)
        return m.group(1) if m else "1"

    @staticmethod
    def _deconflict_set(s: dict) -> None:
        """Drop any item present in BOTH include and exclude of a relationship set (exclude
        wins). FreeWheel rejects the same id in include+exclude — which happens when the
        promoted show is in its own affinity list (targeted) AND self-excluded."""
        for blk, sub in ((s.get("audience_targeting"), None),
                         (s.get("content_targeting"), "network_items")):
            if not isinstance(blk, dict):
                continue
            node = blk.get(sub) if sub else blk
            if not isinstance(node, dict):
                continue
            inc, exc = node.get("include"), node.get("exclude")
            if not isinstance(inc, dict) or not isinstance(exc, dict):
                continue
            for dim, exvals in exc.items():
                if dim not in inc:
                    continue
                exset = set(exvals if isinstance(exvals, list) else [exvals])
                incvals = inc[dim] if isinstance(inc[dim], list) else [inc[dim]]
                kept = [v for v in incvals if v not in exset]
                if kept:
                    inc[dim] = kept
                else:
                    del inc[dim]
            if not inc:
                node.pop("include", None)

    @staticmethod
    def _placement_body(p) -> dict[str, Any]:
        """Assemble the FreeWheel create-placement body, mirroring the Dutton Ranch IO.

        Structure (verified by reading Dutton placements back with expand flags):
          budget   : IMPRESSION_TARGET / 1e9 (remnant)  |  ALL_IMPRESSION (guaranteed)
          delivery : priority TYPE + pacing + frequency_cap {value,type,period(min)}
          override : {mode:BELOW_PAYING_ADS, value:-N} (remnant) | {precedence_level:HIGH}
          price    : {price_model: ACTUAL_ECPM}
          ad_product: NOT_LINKED, ad_unit_node[] {ad_unit_id,status:ACTIVE,price,budget_exempt}
          targeting: relationship_targeting.set[] named sets (Affinity Shows / Channels /
                     Genre / Pluto Categories) — NOT top-level content/audience targeting.
        """
        fc_min = FreeWheelClient._fc_period_minutes(p.frequency_cap)
        frequency_cap = ({"value": FreeWheelClient._fc_value(p.frequency_cap),
                          "type": "IMPRESSION", "period": fc_min}
                         if fc_min else None)
        body: dict[str, Any] = {
            "name": p.name,
            "placement_type": "PROMO",
            "price": {"price_model": "ACTUAL_ECPM"},
            "delivery": {
                "priority": "GUARANTEED" if p.guaranteed else "PREEMPTIBLE",
                "pacing": "FAST_AS",
                **({"frequency_cap": frequency_cap} if frequency_cap else {}),
            },
        }
        if p.guaranteed:
            body["budget"] = {"budget_model": "ALL_IMPRESSION"}
            body["override"] = {"precedence_level": getattr(p, "precedence_level", None) or "HIGH"}
        else:
            body["budget"] = {"budget_model": "IMPRESSION_TARGET", "impression": 1000000000}
            # Priority level -> override.value (negative), mode BELOW_PAYING_ADS.
            if isinstance(p.priority_level, int):
                body["override"] = {"mode": "BELOW_PAYING_ADS", "value": -p.priority_level}

        FreeWheelClient._apply_geo_and_ad_units(body, p)

        sets = FreeWheelClient._relationship_sets(p)
        # ADULT self-exclusion: exclude the promoted title's own audience segment(s) on
        # EVERY set's audience_targeting (merging with a set's include, e.g. Tier 1's DDA).
        aud_excl = sorted(set(getattr(p, "exclude_audience_items", []) or []))
        if sets and aud_excl:
            for s in sets:
                at = s.setdefault("audience_targeting", {})
                ex = at.setdefault("exclude", {})
                ex["audience_item"] = sorted(set(ex.get("audience_item", []) or []) | set(aud_excl))
        # FreeWheel 422s if the SAME item is in a set's include AND exclude (e.g. the
        # promoted show in its own affinity list AND self-excluded). Exclude wins — drop
        # the overlap from the include so a self-contradicting plan never blocks the push.
        for _s in sets:
            FreeWheelClient._deconflict_set(_s)
        if sets:
            body["relationship_targeting"] = {"set": sets}
        # Placement-level content exclude (separate from the relationship sets) —
        # Pluto TV brands exclude the Samsung TV Plus SGs on EVERY placement, incl.
        # plain-remnant lines that have no relationship sets.
        # Set-less lines (flat remnant) have no relationship sets to carry excludes, so
        # ALL excludes (Samsung, self-series, self-channel + brand SGs/VGs) go in the
        # placement-level content_targeting, paired with the main SGs as the include.
        # (Placements WITH sets carry these in the set excludes; the API drops a
        # placement-level content_targeting when sets are present.)
        if not sets:
            ex_sgs = sorted(set(getattr(p, "extra_exclude_site_groups", []) or [])
                            | set(getattr(p, "content_exclude_site_groups", []) or []))
            ex_series = sorted(set(getattr(p, "exclude_series", []) or []))
            ex_vgs = sorted(set(getattr(p, "extra_exclude_video_groups", []) or []))
            ex_videos = sorted(set(getattr(p, "exclude_videos", []) or []))
            excl: dict[str, Any] = {}
            if ex_sgs:
                excl["site_group"] = ex_sgs
            if ex_series:
                excl["series"] = ex_series
            if ex_vgs:
                excl["video_group"] = ex_vgs
            if ex_videos:
                excl["video"] = ex_videos
            include_sgs = list(getattr(p, "main_site_groups", []) or [])
            if excl and include_sgs:
                body["content_targeting"] = {"include": {"site_group": include_sgs},
                                             "exclude": excl}
        if p.recommended_show_value in (None, "") and sets:
            body["_cm_adds_in_ui"] = {
                "recommended_show": "placeholder 'TBD' pre-built — replace with the ShowID"}
        # Rating INCLUDES: AND the market's rating VG(s) into every argument — each set's
        # content targeting for set-having lines, or the placement-level content targeting
        # for set-less flat lines. The promo then runs ONLY on that rating's content.
        rating_inc = sorted(set(getattr(p, "rating_include_video_groups", []) or []))
        if rating_inc:
            if sets:
                for st in sets:
                    holder = st.setdefault("content_targeting", {}).setdefault("network_items", {})
                    FreeWheelClient._and_rating_vgs(holder, rating_inc)
            else:
                FreeWheelClient._and_rating_vgs(body.setdefault("content_targeting", {}), rating_inc)
        FreeWheelClient._exclude_wins(body)
        return body

    @staticmethod
    def _exclusivity(brand_id: str, guaranteed: bool) -> dict[str, Any]:
        """Custom Exclusivity that excludes the IO-level Brand. Scope is ALL_AD_UNITS for
        below-paying lines (standard + tiered remnant) and TARGETED_AD_UNITS for guaranteed
        lines (pre-roll / bumper / lockdown). Enum values + the singular `item` exclude
        shape were confirmed by live create + read-back (the `items` array silently didn't
        apply, and the scope is TARGETED_AD_UNITS — not ..._ONLY, which FreeWheel rejects)."""
        scope = "TARGETED_AD_UNITS" if guaranteed else "ALL_AD_UNITS"
        return {
            "level_of_exclusivity": "CUSTOM",
            "scope_of_exclusivity": scope,
            # "Let Content's Setting Dictate Sponsorship Exemptions". PROMO placements
            # validate this against [CONTENT_SETTING_DICTATE, EXEMPT_FROM_UEX, NO_EXEMPT];
            # required for the TARGETED scope (guaranteed lines).
            "exemptions_uex": "CONTENT_SETTING_DICTATE",
            "custom_exclusivity_exemption": {
                "exclude": {"item": {"id": int(brand_id), "type": "BRAND"}}},
        }

    @staticmethod
    def _and_rating_vgs(holder: dict[str, Any], vgs: list[str]) -> None:
        """AND a required content video_group into an include holder (in place). `holder`
        is whatever dict carries the "include" key — a set's network_items or a flat
        placement's content_targeting. A bare single-subset include is promoted to the
        multi-set AND form so the rating is a distinct AND-ed argument, not OR-ed in.

        FreeWheel caps an advanced include at 3 AND-ed sets. When there's room the rating
        goes in as its own subset (cleanest); at the cap it is merged into an existing
        site-group-only subset (site_group AND video_group within one subset — a true AND,
        same shape as the live Kids sets), so the set count never exceeds 3."""
        vgs = sorted(vgs)
        inc = holder.get("include")
        if not isinstance(inc, dict) or not inc:
            holder["include"] = {"video_group": vgs}
            return
        multi = isinstance(inc.get("set"), list)
        subs = [{k: v for k, v in s.items() if k != "relation_in_set"}
                for s in (inc["set"] if multi else [inc])]
        if len(subs) < 3:
            subs.append({"video_group": vgs})                      # dedicated AND subset
        else:
            # At the 3-set cap: merge into a site-group-only subset (no new set). Fall back
            # to any video-group-free subset; last resort OR into the first subset.
            target = (next((s for s in subs if s.get("site_group") and not s.get("video_group")), None)
                      or next((s for s in subs if not s.get("video_group")), None))
            if target is not None:
                target["video_group"] = vgs
            else:
                subs[0]["video_group"] = sorted(set((subs[0].get("video_group") or []) + vgs))
        if len(subs) == 1:
            holder["include"] = subs[0]
        else:
            holder["include"] = {"relation_between_sets": ["AND"] * (len(subs) - 1),
                                 "set": [{**s, "relation_in_set": "OR"} for s in subs]}

    @staticmethod
    def _exclude_wins(body: dict) -> None:
        """A site group must never be in both include and exclude (FreeWheel rejects it,
        422). An exclude ALWAYS wins — drop the conflicting site group from the include
        (so 'exclude from all placements' overrides any targeting that would run there).
        If that empties a subset's targeting, the subset is dropped; if it empties a
        whole relationship set's include, the set is dropped. Applies to each set and
        the flat content_targeting."""
        def has_targeting(s: dict) -> bool:
            return any(k != "relation_in_set" and v for k, v in s.items())

        def clean(node: dict) -> bool:
            """Filter excluded site groups out of the include; return False if the
            include ends up with no targeting (caller drops the set)."""
            ex = set((node.get("exclude") or {}).get("site_group") or [])
            inc = node.get("include")
            if not isinstance(inc, dict):
                return True
            multi = isinstance(inc.get("set"), list)
            subs = inc["set"] if multi else [inc]
            for s in subs:
                if isinstance(s, dict) and ex and s.get("site_group"):
                    kept = [g for g in s["site_group"] if g not in ex]
                    if kept:
                        s["site_group"] = kept
                    else:
                        s.pop("site_group", None)
            subs = [s for s in subs if isinstance(s, dict) and has_targeting(s)]
            if not subs:
                return False
            if multi and len(subs) > 1:
                inc["set"] = subs
                inc["relation_between_sets"] = ["AND"] * (len(subs) - 1)
            else:                                    # collapse to a single-subset include
                node["include"] = {k: v for k, v in subs[0].items() if k != "relation_in_set"}
            return True

        rt = body.get("relationship_targeting")
        if isinstance(rt, dict) and isinstance(rt.get("set"), list):
            kept = []
            for st in rt["set"]:
                node = (st.get("content_targeting") or {}).get("network_items")
                if not isinstance(node, dict) or clean(node):
                    kept.append(st)
            if kept:
                rt["set"] = kept
            else:
                body.pop("relationship_targeting", None)
        ct = body.get("content_targeting")
        if isinstance(ct, dict):
            clean(ct.get("network_items") if isinstance(ct.get("network_items"), dict) else ct)

    # --- relationship targeting (mirrors Dutton Ranch) ------------------- #

    @staticmethod
    def _content(subsets: list[dict], exclude: Optional[dict] = None) -> Optional[dict]:
        """content_targeting.network_items node: AND the subsets (each OR internally).

        One subset -> `include` holds it directly (verified to persist); two or more
        -> {relation_between_sets: AND, set: [{..., relation_in_set: OR}, ...]}.
        """
        subs = [s for s in subsets if s and any(v for v in s.values())]
        if not subs:
            return None
        # relation_between_sets is an ARRAY with (N-1) relations for N sets
        # ("the number of sets should be one greater than the number of relations").
        include = (dict(subs[0]) if len(subs) == 1
                   else {"relation_between_sets": ["AND"] * (len(subs) - 1),
                         "set": [{**s, "relation_in_set": "OR"} for s in subs]})
        node: dict[str, Any] = {"include": include}
        if exclude:
            node["exclude"] = exclude
        return {"content_targeting": {"network_items": node}}

    @staticmethod
    def _relationship_sets(p) -> list[dict[str, Any]]:
        """Build relationship_targeting.set[] mirroring the Dutton Ranch IO.

        The platform/biz-div "main SGs" are AND-ed into the audience/showlist/genre
        targeting in every tier; Pause Ads use their own platform footprint (no Pluto);
        genre is targeted via "VG: Genre:" Video Groups; the Recommended Show set is a
        custom key-value. Uses placement.targeting_ids (resolved IDs) + config
        constants (config/relationship_targeting.yaml).
        """
        from ..config import relationship_targeting_config
        cfg = relationship_targeting_config().get("domestic_usa", {})
        main = cfg.get("main_site_groups", [])
        pplus = cfg.get("pplus_site_group", [])
        excl_sg = cfg.get("exclude_site_groups", [])
        excl_clips = cfg.get("exclude_video_groups", [])
        rec_placeholder = cfg.get("recommended_show_placeholder", "TBD")
        # Recommended Show argument:
        #   P+ (and other non-Pluto adult): key "recommended_show", applied GLOBALLY.
        #   Pluto TV: key "recommended_shows" (plural), applied DOMESTICALLY only (the
        #             feature isn't rolled out for Pluto internationally).
        is_pluto = bool(getattr(p, "is_pluto_brand", False))
        is_pplus = bool(getattr(p, "is_pplus_brand", False))
        rec_key = "recommended_shows" if is_pluto else cfg.get("recommended_show_key", "recommended_show")
        # Recommended Show is ONLY for P+ (global) and Pluto (domestic). Every other brand
        # (MTVE, CBS, BET, …) gets NONE. Movies never get it either (Show-ID-only feature).
        add_rec_show = (is_pplus or (is_pluto and bool(getattr(p, "region_is_domestic", False)))) \
            and bool(getattr(p, "recommended_show_enabled", True))

        t = p.targeting_ids or {}
        dda = sorted(set(t.get("dda", [])))
        series = sorted(set(t.get("series", [])))
        channels = sorted(set(t.get("channels", [])))
        categories = sorted(set(t.get("categories", [])))
        # Genre = genre VGs + this brand's content VG (e.g. the MTV / BET brand VG).
        genre_vgs = sorted(set(t.get("genre_vgs", [])) | set(getattr(p, "include_video_groups", [])))
        # Per-brand platform "main SGs" override (falls back to the shared default).
        main = list(getattr(p, "main_site_groups", []) or main)

        # Shared DNR + this brand's always-exclude site/video groups (e.g. CBS News
        # excludes the Pluto News category SGs).
        excl_sg_all = list(excl_sg) + list(getattr(p, "extra_exclude_site_groups", []))
        excl_vg_brand = list(getattr(p, "extra_exclude_video_groups", []))
        excl_series = list(getattr(p, "exclude_series", []))   # promoted show's own series
        excl_videos = list(getattr(p, "exclude_videos", []))   # movie video-asset excludes

        def base_exclude(**extra):
            e = dict(extra)
            if excl_vg_brand:
                e["video_group"] = sorted(set(e.get("video_group", []) + excl_vg_brand))
            if excl_sg_all:
                e["site_group"] = sorted(set(excl_sg_all))
            if excl_series:
                e["series"] = sorted(set(e.get("series", []) + excl_series))
            if excl_videos:
                e["video"] = sorted(set(e.get("video", []) + excl_videos))
            return e or None

        def rec_show_set(platform_sg):
            # Always pre-built; blank value -> placeholder for the CM to replace
            # (FreeWheel rejects an empty key-value).
            value = p.recommended_show_value or rec_placeholder
            s = {"set_name": "Recommended Show",
                 "custom_targeting": {"include": {"key_value": f"{rec_key}={value}"}}}
            c = FreeWheelClient._content([{"site_group": platform_sg}], base_exclude())
            if c:
                s.update(c)
            return s

        sets: list[dict[str, Any]] = []

        if p.format == "pause_ads":
            pause = cfg.get("pause", {})
            # Per-brand pause main override (e.g. Paramount Pictures) wins over the default.
            pmain = list(getattr(p, "pause_main_site_groups", []) or pause.get("main_site_groups", []))
            # No-Pluto regions (e.g. IE) drop the Pluto SG from the pause main set.
            if not getattr(p, "region_has_pluto", True):
                pluto_sg = pause.get("pluto_main_site_group")
                pmain = [sg for sg in pmain if sg != pluto_sg]
            pplat = pause.get("platform_site_groups", [])
            plat_subsets = [{"site_group": pmain}, {"site_group": pplat}]
            ex = base_exclude(video_group=pause.get("exclude_video_groups", []))
            # Domestic (US) uses the short key-value exclude list; international regions
            # use the fuller one.
            kv = pause.get("exclude_key_values", [])
            if not getattr(p, "region_is_domestic", True):
                kv = pause.get("exclude_key_values_international") or kv
            custom_excl = ({"custom_targeting": {"exclude": {"key_value": kv}}} if kv else {})
            if p.tier == 1:
                s = {"set_name": "Affinity Shows", **custom_excl}
                if dda:
                    s["audience_targeting"] = {"include": {"audience_item": dda}}
                s.update(FreeWheelClient._content(plat_subsets, ex))
                sets.append(s)
            elif p.tier == 2:
                s = {"set_name": "Affinity Shows", **custom_excl,
                     **FreeWheelClient._content([{"series": series}] + plat_subsets, ex)}
                sets.append(s)
            elif p.tier == 3:
                s = {"set_name": "Genre", **custom_excl,
                     **FreeWheelClient._content([{"video_group": genre_vgs}] + plat_subsets, ex)}
                sets.append(s)
            else:  # tier 4
                sets.append({"set_name": "Affinity Shows", **custom_excl,
                             **FreeWheelClient._content(plat_subsets, ex)})
            return sets

        # Brand-constant relationship sets (built verbatim from config) — e.g. Pluto
        # En Español's fixed "Targeting VOD" / "En Espanol" sets. Each set's include is
        # a list of subsets (AND-ed, OR within) and an explicit exclude.
        static_sets = getattr(p, "static_relationship_sets", None) or []
        if static_sets:
            out: list[dict[str, Any]] = []
            for sd in static_sets:
                # Fold the promoted show's own series into each static set's exclude too,
                # so the self-exclusion holds on every argument here as well.
                exclude = dict(sd.get("exclude") or {})
                if excl_series:
                    exclude["series"] = sorted(set(exclude.get("series", []) + excl_series))
                node = FreeWheelClient._content(sd.get("include", []), exclude or None)
                if node:
                    out.append({"set_name": sd.get("set_name"), **node})
            return out

        # Kids: one "Kids" set = (kids Video Groups + Kids content SG) AND main SGs.
        # Mirrors the P+ Kids IOs; used by both remnant and guaranteed Kids lines.
        kids_vgs = sorted(set(getattr(p, "kids_video_groups", []) or []))
        if kids_vgs:
            kids_sg = getattr(p, "kids_content_site_group", None)
            kcfg = relationship_targeting_config().get("kids", {})
            older, younger = kcfg.get("older_video_group"), kcfg.get("younger_video_group")
            # Single-age campaigns exclude the OTHER age's Cable Kids VG, globally:
            #   older-only  -> exclude Nick Jr (younger); younger-only -> exclude Nick (older).
            # Both ages -> include both (+ the Kids COPPA VG/SG), no exclusion.
            excl_vgs = []
            if older in kids_vgs and younger and younger not in kids_vgs:
                excl_vgs.append(younger)
            if younger in kids_vgs and older and older not in kids_vgs:
                excl_vgs.append(older)
            excl = base_exclude(video_group=excl_vgs) if excl_vgs else base_exclude()
            subsets = [{"video_group": kids_vgs,
                        "site_group": [kids_sg] if kids_sg else []},
                       {"site_group": main}]
            return [{"set_name": "Kids",
                     **FreeWheelClient._content(subsets, excl)}]

        if getattr(p, "no_targeting", False):
            return []   # bare sponsorship line (ad unit + geo only)

        if p.guaranteed:
            # P+ sponsored (Plan placements): exactly one Genre argument (genre Video
            # Groups on Paramount+) + one Recommended Show argument. No showlist.
            # Format-level excludes (Bumper -> Stream Type: Live SG; Pre-Roll -> Clips VG)
            # ride on base_exclude via the placement, so they hit EVERY set below.
            if genre_vgs:
                sets.append({"set_name": "Genre", **FreeWheelClient._content(
                    [{"site_group": pplus}, {"video_group": genre_vgs}], base_exclude())})
            if add_rec_show:   # guaranteed lines are P+ (non-Pluto) -> always add
                sets.append(rec_show_set(pplus))
            return sets

        # Remnant video, per tier.
        if p.tier == 1:
            s = {"set_name": "Affinity Shows"}
            if dda:
                s["audience_targeting"] = {"include": {"audience_item": dda}}
            c = FreeWheelClient._content([{"site_group": main}], base_exclude())
            if c:
                s.update(c)
            sets.append(s)
            # Recommended Show: P+ globally (pplus SG); Pluto domestically only (Pluto SG).
            if add_rec_show:
                rs = rec_show_set(main if is_pluto else pplus)
                if rs:
                    sets.append(rs)
        elif p.tier == 2:
            if series:
                sets.append({"set_name": "Affinity Shows", **FreeWheelClient._content(
                    [{"series": series}, {"site_group": main}], base_exclude())})
            if channels:
                sets.append({"set_name": "Channels", **FreeWheelClient._content(
                    [{"site_group": channels}], base_exclude())})
            if not sets:   # no showlist/channels -> platform-constrained, still excludes promoted
                sets.append({"set_name": "Affinity Shows", **FreeWheelClient._content(
                    [{"site_group": main}], base_exclude())})
        elif p.tier == 3:
            if genre_vgs:
                sets.append({"set_name": "Genre", **FreeWheelClient._content(
                    [{"site_group": main}, {"video_group": genre_vgs}],
                    base_exclude(video_group=excl_clips))})
            elif is_pluto:
                # Pluto TV always carries a Genre argument in Tier 3 (globally), even when
                # the plan names no genres — a platform-constrained genre set (CM fills VGs).
                sets.append({"set_name": "Genre", **FreeWheelClient._content(
                    [{"site_group": main}], base_exclude(video_group=excl_clips))})
            if categories:
                sets.append({"set_name": "Pluto Categories", **FreeWheelClient._content(
                    [{"site_group": categories}], base_exclude())})
            if not sets:   # no genre/categories -> platform-constrained, still excludes promoted
                sets.append({"set_name": "Genre", **FreeWheelClient._content(
                    [{"site_group": main}], base_exclude(video_group=excl_clips))})
        else:  # tier 4 — platform-constrained RON
            sets.append({"set_name": "Genre", **FreeWheelClient._content(
                [{"site_group": main}], base_exclude())})
        return sets

    @staticmethod
    def _apply_geo_and_ad_units(body: dict[str, Any], p) -> None:
        """Geo + ad units — shared by remnant and guaranteed placements."""
        # Geo: API writes COUNTRY IDs (int64). Names ("United States") are what the
        # team searches in the UI and are resolved to IDs via the country table. Some
        # regions target a geography REGION grouping instead (e.g. LATAM = region 1069).
        include: dict[str, Any] = {}
        if getattr(p, "geo_region_ids", None):
            include["region"] = p.geo_region_ids
        elif p.geo_country_ids:
            include["country"] = p.geo_country_ids
        # Optional sub-country overlay — additive to the country/region base. FreeWheel's
        # include object holds each level under its own key (state/dma/city as FW ID sets).
        if getattr(p, "geo_state_ids", None):
            include["state"] = list(p.geo_state_ids)
        if getattr(p, "geo_dma_ids", None):
            include["dma"] = list(p.geo_dma_ids)
        if getattr(p, "geo_city_ids", None):
            include["city"] = list(p.geo_city_ids)
        # Geo EXCLUDE overlay ("run everywhere except …") — its own exclude object, same
        # per-level keys (state/dma/city). Coexists with include.
        exclude: dict[str, Any] = {}
        if getattr(p, "geo_exclude_state_ids", None):
            exclude["state"] = list(p.geo_exclude_state_ids)
        if getattr(p, "geo_exclude_dma_ids", None):
            exclude["dma"] = list(p.geo_exclude_dma_ids)
        if getattr(p, "geo_exclude_city_ids", None):
            exclude["city"] = list(p.geo_exclude_city_ids)
        geo_body: dict[str, Any] = {}
        if include:
            geo_body["include"] = include
        if exclude:
            geo_body["exclude"] = exclude
        if geo_body:
            body["geography_targeting"] = geo_body
        if p.geo_country_names:
            body["_geo_country_names"] = list(p.geo_country_names)  # UI reference
        # Ad units: link_method NOT_LINKED (mirrors Dutton — creatives linked later by
        # the CM). Each node: ad_unit_id + status ACTIVE + price + budget_exempt.
        if p.ad_unit_ids:
            body["ad_product"] = {
                "link_method": "NOT_LINKED",
                "ad_unit_node": [{"ad_unit_id": a, "status": "ACTIVE",
                                  "price": "0.01", "budget_exempt": "false"}
                                 for a in p.ad_unit_ids],
            }
        if p.ad_unit_names:
            body["_ad_unit_names"] = list(p.ad_unit_names)          # UI reference
