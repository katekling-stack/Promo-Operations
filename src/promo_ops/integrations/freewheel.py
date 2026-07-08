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
            ai = b.get("targeting", {}).get("audience_targeting", {}).get("include", {})
            if "audience_item" in ai:
                ai["audience_item"] = sorted(set(ai["audience_item"]))  # dedupe
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

    @staticmethod
    def _placement_body(p) -> dict[str, Any]:
        """Assemble the FreeWheel create-placement body from a built Placement.

        Maps resolved tier dimensions onto the confirmed create-placement targeting
        sections. `insertion_order_id` is set at create time. See docs/FREEWHEEL.md.
        """
        # FreeWheel delivery.priority is a TYPE: GUARANTEED (sponsorship) or
        # PREEMPTIBLE (remnant). The numeric tier level (1-10) is carried in the
        # placement NAME (Tier N) for the CM; frequency-cap format is set separately.
        body: dict[str, Any] = {
            "name": p.name,
            "placement_type": "PROMO",
            # Validated on production: priority TYPE + pacing are required.
            "delivery": {
                "priority": "GUARANTEED" if p.guaranteed else "PREEMPTIBLE",
                "pacing": "SMOOTH_AS" if p.guaranteed else "FAST_AS",
            },
            "_tier_priority_rank": p.priority_level,   # reference (from priorities.yaml)
            "_frequency_cap": p.frequency_cap,          # reference until FC schema wired
        }
        if p.guaranteed:
            body["_guaranteed_args"] = p.arguments  # genre + recommended_show
            return body

        tier = p.targeting.tiers[0] if p.targeting.tiers else None
        audience_items: list = []          # Tier 1 DDA + manual segments (numeric ids)
        pending_segments: list = []        # segments known by name only (need id via sync)
        series_ids: list = []              # Tier 2 showlist -> series
        standard_attr_ids: list = []       # genre / network -> standard attribute ids
        geo: list = []
        for d in (tier.dimensions if tier else []):
            if d.key == "audience_segments":
                for r in d.resolved:
                    (audience_items if r.get("segment_id") else pending_segments).append(
                        r.get("segment_id") or r.get("segment_name"))
            elif d.key == "content_affinity_showlist":
                series_ids += [r["id"] for r in d.resolved if r.get("id")]
            elif d.key in ("genre", "network"):
                standard_attr_ids += [r["id"] for r in d.resolved if r.get("id")]
            elif d.key in ("pluto_channel_list", "pluto_category"):
                pending_segments += [r.get("segment_name") for r in d.resolved]
            elif d.key == "geo":
                geo += list(d.values)

        targeting: dict[str, Any] = {}
        if audience_items:
            targeting["audience_targeting"] = {"include": {"audience_item": audience_items}}
        content: dict[str, Any] = {}
        if series_ids:
            content["network_items"] = {"include": {"sets": [{"series": series_ids}]}}
        if standard_attr_ids:
            content["standard_attributes"] = standard_attr_ids
        if content:
            targeting["content_targeting"] = content
        if geo:
            targeting["geography_targeting"] = {"include": {"region": geo}}
        body["targeting"] = targeting
        body["exclusions"] = p.exclusions        # promoted show excluded everywhere
        if pending_segments:
            body["_pending_segments_need_ids"] = pending_segments  # run sync-audience-items
        return body
