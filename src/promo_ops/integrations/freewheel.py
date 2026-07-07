"""FreeWheel client (MRM / shmcp.freewheel.com).

Responsibilities:
  * Find the VCBS advertisers (name filter) and their active campaigns.
  * Clone the region-code template Order/Placement structure per brand.
  * Create the Order + Placements built by OrderBuilder, applying tiered targeting.

The FreeWheel API reference (https://shmcp.freewheel.com/reference) is auth-gated, so
the exact endpoint paths and payload schema must be confirmed against the tenant.
Points that need that confirmation are marked `# CONFIRM:`. Everything else follows
the standard OAuth2 + REST shape. Nothing here runs without credentials.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

from ..config import env, require_env
from ..models import Order


class FreeWheelClient:
    def __init__(self):
        self.base_url = require_env("FREEWHEEL_BASE_URL").rstrip("/")
        self.network_id = require_env("FREEWHEEL_NETWORK_ID")
        self._username = require_env("FREEWHEEL_USERNAME")
        self._password = require_env("FREEWHEEL_PASSWORD")
        self.advertiser_filter = env("FREEWHEEL_ADVERTISER_NAME_FILTER", "VCBS")
        self._session = requests.Session()
        self._token: Optional[str] = None

    # --- auth ------------------------------------------------------------ #

    def authenticate(self) -> str:
        """Exchange username/password for a session token.

        The API user is of the form ``AdOps.api@<network_id>``. CONFIRM the exact
        token endpoint + response field against the FreeWheel reference
        (https://shmcp.freewheel.com/reference) — it could not be reached from the
        build environment (network policy), so this follows the standard shape.
        """
        resp = self._session.post(
            f"{self.base_url}/auth/token",  # CONFIRM: exact token endpoint
            json={"username": self._username, "password": self._password},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token") or data.get("token")  # CONFIRM field
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})
        return self._token

    def _ensure_auth(self) -> None:
        if not self._token:
            self.authenticate()

    # --- reads ----------------------------------------------------------- #

    def find_advertisers(self, name_contains: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """List advertisers whose name matches all `name_contains` fragments.

        Defaults to the VCBS filter. This is how we satisfy "Advertisers that
        contain 'VCBS' in the name".
        """
        self._ensure_auth()
        fragments = name_contains or [self.advertiser_filter]
        # CONFIRM: advertisers list endpoint + pagination.
        resp = self._session.get(
            f"{self.base_url}/networks/{self.network_id}/advertisers",
            timeout=30,
        )
        resp.raise_for_status()
        advertisers = resp.json().get("items", resp.json())
        return [
            a for a in advertisers
            if all(f.lower() in (a.get("name", "").lower()) for f in fragments)
        ]

    def list_active_campaigns(self, advertiser_id: str) -> list[dict[str, Any]]:
        """Active campaigns under an advertiser — the basis for brand templates."""
        self._ensure_auth()
        # CONFIRM: campaigns endpoint + active-status filter field.
        resp = self._session.get(
            f"{self.base_url}/advertisers/{advertiser_id}/campaigns",
            params={"status": "active"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("items", resp.json())

    def get_campaign_template(self, campaign_id: str, io_id: Optional[str] = None) -> dict[str, Any]:
        """Fetch a campaign/IO to use as a region-code template to clone from."""
        self._ensure_auth()
        params = {"insertion_order_id": io_id} if io_id else {}
        resp = self._session.get(
            f"{self.base_url}/campaigns/{campaign_id}",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # --- writes ---------------------------------------------------------- #

    def create_order(self, order: Order, dry_run: bool = True) -> dict[str, Any]:
        """Create the Order + Placements in FreeWheel.

        With dry_run=True (default) this returns the payload it *would* POST, so the
        mapping can be reviewed. Set dry_run=False to actually create.
        """
        payload = self.to_freewheel_payload(order)
        if dry_run:
            return {"dry_run": True, "would_post": payload}

        self._ensure_auth()
        # CONFIRM: order creation endpoint + whether placements are nested or posted
        # separately as children.
        resp = self._session.post(
            f"{self.base_url}/networks/{self.network_id}/orders",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def to_freewheel_payload(order: Order) -> dict[str, Any]:
        """Translate our Order model into the FreeWheel order payload shape.

        CONFIRM: field names against the tenant schema. The structure below reflects
        the conceptual FreeWheel model (Order -> Placements -> Targeting).
        """
        return {
            "name": order.name,
            "advertiser": order.advertiser,
            "campaign": order.campaign,
            "network_id": order.network_id,
            "clone_from": order.template_ref,
            "flight": {
                "start": order.flight.start,
                "end": order.flight.end,
            },
            "placements": [
                {
                    "name": p.name,
                    "type": p.format_code,
                    "endpoints": p.endpoints,
                    "frequency_cap": p.frequency_cap,
                    "creative_duration_priority": p.creative_durations_priority,
                    "targeting": [
                        {
                            "tier": t.id,
                            "tier_name": t.name,
                            "dimensions": [
                                {
                                    "key": d.key,
                                    "values": d.values,
                                    "resolved_segments": d.resolved,
                                }
                                for d in t.dimensions
                            ],
                        }
                        for t in p.targeting.tiers
                    ],
                }
                for p in order.placements
            ],
        }
