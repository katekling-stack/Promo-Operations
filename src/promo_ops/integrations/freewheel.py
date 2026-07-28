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
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from ..config import env, require_env
from ..models import Order

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

    # --- auth (OAuth 2.1 PKCE) ------------------------------------------ #

    def authenticate(self) -> str:
        s = self._session
        client_id = s.post(
            f"{self.hub_url}/oauth/register",
            json={"client_name": "promo-ops", "redirect_uris": [REDIRECT_URI],
                  "grant_types": ["authorization_code", "refresh_token"],
                  "response_types": ["code"], "token_endpoint_auth_method": "none"},
            timeout=30,
        ).json()["client_id"]

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
        code, loc, hops = None, r.headers.get("Location"), 0
        while loc and hops < 5:
            if "code=" in loc:
                code = parse_qs(urlparse(loc).query).get("code", [None])[0]
                break
            r = s.get(urljoin(self.hub_url, loc), allow_redirects=False, timeout=30)
            loc, hops = r.headers.get("Location"), hops + 1
        if not code:
            raise RuntimeError("FreeWheel login failed (no auth code). Check credentials/environment.")

        tok = s.post(f"{self.hub_url}/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
            "client_id": client_id, "code_verifier": verifier}, timeout=30).json()
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
        """Call an API tool via invoke_tool; unwrap the {ok,data} payload."""
        self._ensure_auth()
        r = self._mcp("tools/call", {"name": "invoke_tool",
                                     "arguments": {"tool_name": tool_name, "parameters": parameters}})
        try:
            return json.loads(r["result"]["content"][0]["text"])
        except (KeyError, TypeError, json.JSONDecodeError):
            return r

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
        """Find an existing campaign id by exact name (the IO's parent)."""
        payload = self._invoke("sh_1_1_list-campaigns", name=name.split(" - ")[0], per_page=50)
        for c in self._rows(payload, "campaigns"):
            if str(c.get("name", "")).strip() == name.strip():
                return str(c.get("id"))
        return None

    def get_insertion_order(self, io_id: str) -> dict[str, Any]:
        return self._invoke("sh_1_1_get-a-insertion-order", insertion_order_id=int(io_id))

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
        plan = self.to_freewheel_plan(order)
        if dry_run:
            return {"dry_run": True, "planned_calls": plan}

        campaign_id = order.campaign.get("resolved_id") or self.resolve_campaign_id(
            order.campaign.get("name", ""))
        if not campaign_id:
            raise RuntimeError(
                f"Parent campaign {order.campaign.get('name')!r} not found. "
                f"Confirm the exact Advertiser + Campaign names.")

        io = self._invoke("sh_1_1_create-an-insertion-order",
                          campaign_id=int(campaign_id), body=plan["insertion_order_body"])
        io_id = ((io.get("data") or {}).get("insertion_order") or {}).get("id")

        placements = []
        for body in plan["placement_bodies"]:
            b = {k: v for k, v in body.items() if not k.startswith("_")}  # drop reference-only keys
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
            # Brand left BLANK by design: the assigned CM creates/maps the Brand under
            # the advertiser and sets it before booking the IO. (brand_id available in
            # order.template_ref for reference.)
            # Left NOT_BOOKED (draft) on create — never auto-book/go-live.
            "currency": "USD",
            "schedule": {"start_time": order.flight.start, "end_time": order.flight.end},
        }
        placement_bodies = [FreeWheelClient._placement_body(p) for p in order.placements]
        return {
            "parent": parent,
            "insertion_order_body": insertion_order_body,
            "placement_bodies": placement_bodies,
        }

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
    _FC_UNIT_MIN = {"min": 1, "minute": 1, "hr": 60, "hour": 60, "day": 1440, "week": 10080}

    @staticmethod
    def _fc_period_minutes(cap: Optional[str]) -> Optional[str]:
        # Handles "1 per 30 min", "1 per hr" (implicit 1), "1 per 21 days", "1 per 4 hrs".
        if not cap:
            return None
        m = re.search(r"per\s*(\d+)?\s*(minute|min|hour|hr|day|week)s?", cap, re.I)
        if not m:
            return None
        qty = int(m.group(1)) if m.group(1) else 1
        return str(qty * FreeWheelClient._FC_UNIT_MIN[m.group(2).lower()])

    @staticmethod
    def _fc_value(cap: Optional[str]) -> str:
        # The impression count before "per" ("2 per day" -> "2"; default "1").
        m = re.match(r"\s*(\d+)\s*per", cap or "", re.I)
        return m.group(1) if m else "1"

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
        if sets:
            body["relationship_targeting"] = {"set": sets}
        if p.recommended_show_value in (None, "") and sets:
            body["_cm_adds_in_ui"] = {
                "recommended_show": "placeholder 'TBD' pre-built — replace with the ShowID"}
        return body

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
        rec_key = cfg.get("recommended_show_key", "recommended_show")
        rec_placeholder = cfg.get("recommended_show_placeholder", "TBD")

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

        def base_exclude(**extra):
            e = dict(extra)
            if excl_vg_brand:
                e["video_group"] = sorted(set(e.get("video_group", []) + excl_vg_brand))
            if excl_sg_all:
                e["site_group"] = sorted(set(excl_sg_all))
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
            pmain = pause.get("main_site_groups", [])
            pplat = pause.get("platform_site_groups", [])
            plat_subsets = [{"site_group": pmain}, {"site_group": pplat}]
            ex = base_exclude(video_group=pause.get("exclude_video_groups", []))
            kv = pause.get("exclude_key_values", [])
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
                node = FreeWheelClient._content(sd.get("include", []), sd.get("exclude"))
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
            # Older-kids-only: ALWAYS exclude the Younger (Nick Jr) VG, globally.
            kids_excl = {}
            if older in kids_vgs and younger and younger not in kids_vgs:
                kids_excl["video_group"] = [younger]
            excl = base_exclude(**kids_excl)
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
            if genre_vgs:
                sets.append({"set_name": "Genre", **FreeWheelClient._content(
                    [{"site_group": pplus}, {"video_group": genre_vgs}],
                    base_exclude(video_group=excl_clips))})
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
            rs = rec_show_set(pplus)
            if rs:
                sets.append(rs)
        elif p.tier == 2:
            if series:
                sets.append({"set_name": "Affinity Shows", **FreeWheelClient._content(
                    [{"series": series}, {"site_group": main}], base_exclude())})
            if channels:
                sets.append({"set_name": "Channels", **FreeWheelClient._content(
                    [{"site_group": channels}], base_exclude())})
        elif p.tier == 3:
            if genre_vgs:
                sets.append({"set_name": "Genre", **FreeWheelClient._content(
                    [{"site_group": main}, {"video_group": genre_vgs}],
                    base_exclude(video_group=excl_clips))})
            if categories:
                sets.append({"set_name": "Pluto Categories", **FreeWheelClient._content(
                    [{"site_group": categories}], base_exclude())})
        else:  # tier 4 — platform-constrained RON
            sets.append({"set_name": "Genre", **FreeWheelClient._content(
                [{"site_group": main}], base_exclude())})
        return sets

    @staticmethod
    def _apply_geo_and_ad_units(body: dict[str, Any], p) -> None:
        """Geo + ad units — shared by remnant and guaranteed placements."""
        # Geo: API writes COUNTRY IDs (int64). Names ("United States") are what the
        # team searches in the UI and are resolved to IDs via the country table.
        if p.geo_country_ids:
            body["geography_targeting"] = {"include": {"country": p.geo_country_ids}}
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
