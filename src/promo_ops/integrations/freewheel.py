"""FreeWheel client (Streaming Hub — shmcp.freewheel.com).

Confirmed against the Streaming Hub MCP reference (shmcp.freewheel.com/reference):

FreeWheel object hierarchy:  Advertiser -> Campaign -> Insertion Order -> Placement
Our model maps as:           advertiser -> campaign -> Order (= Insertion Order)
                                                        -> Placement(s)

Confirmed V3 REST endpoints (base path /services/v3):
  Advertisers   GET  /services/v3/advertisers                         (list; filter VCBS)
                GET  /services/v3/advertisers/{id}
  Campaigns     GET  /services/v3/campaigns
                POST /services/v3/campaign
                GET  /services/v3/campaign/{id}
                GET  /services/v3/campaign/{id}/insertion_orders
  Insertion     GET  /services/v3/insertion_orders
  Orders        POST /services/v3/campaign/{campaign_id}/insertion_order
                GET  /services/v3/insertion_order/{id}
                GET  /services/v3/insertion_order/{id}/placements
                PUT  /services/v3/insertion_order/{id}/book         (activate/book)
  Placements    GET  /services/v3/placements
                POST /services/v3/placement/create
                GET  /services/v3/placement/{id}
                PUT  /services/v3/placement/{id}/activate

IMPORTANT: V3 endpoints take **XML** request bodies (V4 take JSON). See
`# XML-SCHEMA:` markers — the exact XML element names for create Campaign / IO /
Placement / targeting still need to be confirmed from the OpenAPI spec or a live
call, since the reference lists paths/methods but not full V3 bodies.

Auth: two options.
  (A) Custom Connector (recommended) — connect shmcp.freewheel.com to Claude via
      OAuth 2.1 PKCE; the 309 tools become directly available and creds never touch
      code. Preferred for interactive building/validation.
  (B) Programmatic — sealed-box login (streaming_hub_get_login_public_key +
      streaming_hub_login_encrypted with {environment, username, password}) to get a
      session_id, then invoke_tool. Preferred for headless automation. Implemented
      below; requires pynacl for the sealed box.

Environment values: "production" or "staging" (test network 520310 = staging).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import requests

from ..config import env, require_env
from ..models import Order

STREAMING_HUB_URL = "https://shmcp.freewheel.com"


class FreeWheelClient:
    def __init__(self):
        self.hub_url = env("FREEWHEEL_HUB_URL", STREAMING_HUB_URL).rstrip("/")
        self.network_id = require_env("FREEWHEEL_NETWORK_ID")
        self.environment = env("FREEWHEEL_ENVIRONMENT", "staging")  # staging|production
        self._username = require_env("FREEWHEEL_USERNAME")
        self._password = require_env("FREEWHEEL_PASSWORD")
        self.advertiser_filter = env("FREEWHEEL_ADVERTISER_NAME_FILTER", "VCBS")
        self._session = requests.Session()
        self._session_id: Optional[str] = None

    # --- auth (option B: sealed-box programmatic login) ------------------ #

    def _call_tool(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """Invoke a Streaming Hub MCP tool via the invoke_tool gateway."""
        payload = {"tool_name": tool_name, "parameters": parameters}
        if self._session_id:
            payload["session_id"] = self._session_id
        resp = self._session.post(
            f"{self.hub_url}/invoke_tool",  # CONFIRM: MCP transport (JSON-RPC /mcp)
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def authenticate(self) -> str:
        """Sealed-box login → session_id. Requires pynacl."""
        try:
            from nacl.public import PublicKey, SealedBox
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "pynacl not installed (needed for FreeWheel sealed-box login). "
                "Run: pip install pynacl"
            ) from exc
        import base64

        key_info = self._call_tool("streaming_hub_get_login_public_key", {})
        public_key_b64 = key_info["public_key_b64"]
        plaintext = json.dumps({
            "environment": self.environment,
            "username": self._username,
            "password": self._password,
        }).encode()
        sealed = SealedBox(PublicKey(base64.b64decode(public_key_b64))).encrypt(plaintext)
        ciphertext = base64.b64encode(sealed).decode()

        result = self._call_tool("streaming_hub_login_encrypted", {"ciphertext": ciphertext})
        self._session_id = result["session_id"]
        return self._session_id

    def _ensure_auth(self) -> None:
        if not self._session_id:
            self.authenticate()

    def _api(self, tool_name: str, **parameters: Any) -> Any:
        """Call a v3/v4 API tool by its Streaming Hub tool name."""
        self._ensure_auth()
        return self._call_tool(tool_name, parameters)

    # --- reads ----------------------------------------------------------- #

    def find_advertisers(self, name_contains: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """List advertisers matching all `name_contains` fragments (default VCBS)."""
        fragments = name_contains or [self.advertiser_filter]
        result = self._api("sh_1_1_list-advertisers")
        advertisers = _items(result)
        return [
            a for a in advertisers
            if all(f.lower() in str(a.get("name", "")).lower() for f in fragments)
        ]

    def list_active_campaigns(self) -> list[dict[str, Any]]:
        """List campaigns (filter active client-side; see `status`)."""
        return _items(self._api("sh_1_1_list-campaigns"))

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self._api("sh_1_1_show-a-campaign", campaign_id=campaign_id)

    def _resolve_campaign_id(self, order: Order) -> Optional[str]:
        """Find the existing campaign id by name (the IO's parent campaign)."""
        target = (order.campaign.get("name") or "").strip().lower()
        if not target:
            return None
        for c in self.list_active_campaigns():
            if str(c.get("name", "")).strip().lower() == target:
                return _id_of(c) or c.get("id")
        return None

    def get_campaign_template(self, campaign_id: str, io_id: Optional[str] = None) -> dict[str, Any]:
        """Fetch a campaign (and optionally an IO) to use as a region-code template."""
        campaign = self.get_campaign(campaign_id)
        if io_id:
            campaign["_insertion_order"] = self._api(
                "sh_1_1_get-a-insertion-order", insertion_order_id=io_id
            )
        return campaign

    # --- writes ---------------------------------------------------------- #

    def create_order(self, order: Order, dry_run: bool = True) -> dict[str, Any]:
        """Create the campaign's Insertion Order + Placements in FreeWheel.

        dry_run=True (default) returns the calls it *would* make; dry_run=False
        executes: create/reuse campaign -> create IO -> create each placement.
        """
        plan = self.to_freewheel_plan(order)
        if dry_run:
            return {"dry_run": True, "planned_calls": plan}

        # The IO nests under an EXISTING named campaign (e.g. "Paramount + - USA").
        # Resolve it by id, else by name under the advertiser; we do NOT create it.
        campaign_id = order.campaign.get("resolved_id") or self._resolve_campaign_id(order)
        if not campaign_id:
            raise RuntimeError(
                f"Campaign {order.campaign.get('name')!r} not found under advertiser "
                f"{order.advertiser.get('name') or order.advertiser.get('name_contains')!r}. "
                f"Confirm the exact Advertiser + Campaign names in the plan."
            )

        io = self._api(
            "sh_1_1_create-an-insertion-order",
            campaign_id=campaign_id,
            body=plan["insertion_order_body"],
        )
        io_id = _id_of(io)

        placements = []
        for pl_body in plan["placement_bodies"]:
            placements.append(self._api("sh_1_1_create-a-placement", body=pl_body))

        return {"campaign_id": campaign_id, "insertion_order": io, "placements": placements}

    @staticmethod
    def to_freewheel_plan(order: Order) -> dict[str, Any]:
        """Translate our Order into the FreeWheel call plan.

        V3 bodies are XML strings. `# XML-SCHEMA:` marks where exact element names
        must be confirmed from the OpenAPI spec / a live sample before going live.
        The structured dicts below are the source of truth; `_to_v3_xml` renders
        them to XML once the schema is confirmed.
        """
        # The IO nests under an existing campaign; we do not create a campaign.
        parent = {
            "advertiser_name": order.advertiser.get("name"),
            "advertiser_name_contains": order.advertiser.get("name_contains"),
            "campaign_name": order.campaign.get("name"),
        }
        insertion_order_body = {  # XML-SCHEMA: confirm <insertion_order> elements
            "name": order.name,   # e.g. "Frisco King - USA"
            "start_date": order.flight.start,
            "end_date": order.flight.end,
        }
        # Remnant placements attach to the new IO; guaranteed ones (Premium Pre-Roll,
        # Essential) attach to an existing guaranteed order.
        placement_bodies, guaranteed_bodies = [], []
        for p in order.placements:
            body = {  # XML-SCHEMA: confirm <placement> + targeting + exclusions
                "name": p.name,
                "type": p.format_code,
                "endpoints": p.endpoints,
                "frequency_cap": p.frequency_cap,
                "exclusions": p.exclusions,          # promoted show excluded everywhere
                "targeting": [
                    {
                        "tier": t.id,
                        "dimensions": [
                            {"key": d.key, "values": d.values, "resolved_segments": d.resolved}
                            for d in t.dimensions
                        ],
                    }
                    for t in p.targeting.tiers
                ],
            }
            if p.guaranteed:
                body["arguments"] = p.arguments   # {genre, recommended_show}
                guaranteed_bodies.append(body)
            else:
                placement_bodies.append(body)
        return {
            "parent": parent,
            "insertion_order_body": insertion_order_body,
            "placement_bodies": placement_bodies,
            "guaranteed_placement_bodies": guaranteed_bodies,  # -> existing guaranteed order
        }


def _items(result: Any) -> list[dict[str, Any]]:
    """Normalize a list response (shape varies; adjust once confirmed live)."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("items", "data", "advertisers", "campaigns", "results"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


def _id_of(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        return result.get("id") or result.get("_id") or (result.get("data") or {}).get("id")
    return None
