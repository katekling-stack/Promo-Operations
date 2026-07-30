"""Google Ad Manager client — push the corresponding order/line items.

Mirrors the FreeWheel push: the same built Order maps to a GAM Order with one
LineItem per format. Uses the official `googleads` library (install with the `gam`
extra) and a service-account `googleads.yaml` / GAM_SERVICE_ACCOUNT_JSON.

GAM's targeting model differs from FreeWheel's (custom targeting keys/values,
audience segments, geo). `to_gam_targeting()` maps our tier dimensions onto GAM
custom-targeting criteria; the specific key IDs must be created in the GAM network
first and mapped here — marked `# MAP:`.
"""

from __future__ import annotations

from typing import Any

from ..config import env, require_env
from ..models import Order


class GoogleAdManagerClient:
    def __init__(self):
        self.network_code = require_env("GAM_NETWORK_CODE")
        self.application_name = env("GAM_APPLICATION_NAME", "paramount-promo-ops")
        self._service_account_json = require_env("GAM_SERVICE_ACCOUNT_JSON")
        self._client = None

    def _ad_manager_client(self):
        try:
            from googleads import ad_manager, oauth2
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "googleads not installed. Run: pip install -e '.[gam]'"
            ) from exc
        oauth2_client = oauth2.GoogleServiceAccountClient(
            self._service_account_json,
            oauth2.GetAPIScope("ad_manager"),
        )
        return ad_manager.AdManagerClient(
            oauth2_client, self.application_name, network_code=self.network_code
        )

    GAM_API_VERSION = "v202408"

    def preflight(self) -> dict[str, Any]:
        """Prove GAM access: connect and fetch the current network. Run `promo-ops
        gam-check` once GAM API access + a service account land."""
        client = self._ad_manager_client()
        net = client.GetService("NetworkService",
                                version=self.GAM_API_VERSION).getCurrentNetwork()
        return {"ok": True, "network_code": net.get("networkCode"),
                "display_name": net.get("displayName")}

    def create_order(self, order: Order, dry_run: bool = True) -> dict[str, Any]:
        payload = self.to_gam_payload(order)
        if dry_run:
            return {"dry_run": True, "would_create": payload}

        self._client = self._client or self._ad_manager_client()
        order_service = self._client.GetService("OrderService", version="v202408")
        li_service = self._client.GetService("LineItemService", version="v202408")

        created_order = order_service.createOrders([payload["order"]])[0]
        line_items = []
        for li in payload["line_items"]:
            li["orderId"] = created_order["id"]
            line_items.append(li)
        created_lis = li_service.createLineItems(line_items) if line_items else []
        return {"order": created_order, "line_items": created_lis}

    @staticmethod
    def to_gam_payload(order: Order) -> dict[str, Any]:
        return {
            "order": {
                "name": order.name,
                "advertiserId": order.advertiser.get("resolved_id"),  # MAP: GAM company id
                "notes": f"Promo: {order.promoted_title} ({order.region})",
            },
            "line_items": [
                {
                    "name": p.name,
                    "lineItemType": "HOUSE",  # promo/house inventory
                    "targeting": GoogleAdManagerClient.to_gam_targeting(p),
                }
                for p in order.placements
            ],
        }

    @staticmethod
    def to_gam_targeting(placement) -> dict[str, Any]:
        """Map tier dimensions onto GAM targeting. MAP: custom key IDs per network."""
        custom_criteria = []
        for tier in placement.targeting.tiers:
            for dim in tier.dimensions:
                custom_criteria.append({
                    "key": dim.key,          # MAP: GAM custom targeting key id
                    "tier": tier.id,
                    "values": dim.values,
                })
        return {"customTargeting": custom_criteria}
