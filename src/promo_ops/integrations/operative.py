"""Operative (Operative One) client.

The kickoff describes pushing "an Order from Operative into FreeWheel and Operative
into Google Ad Manager". This client reads the originating order/line details from
Operative so they can be reconciled against, or used to drive, the FreeWheel and GAM
pushes. Endpoint paths/auth are tenant-specific and marked `# CONFIRM:`.
"""

from __future__ import annotations

from typing import Any

import requests

from ..config import require_env


class OperativeClient:
    def __init__(self):
        self.base_url = require_env("OPERATIVE_BASE_URL").rstrip("/")
        self._api_key = require_env("OPERATIVE_API_KEY")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self._api_key}"})

    def get_order(self, operative_order_id: str) -> dict[str, Any]:
        # CONFIRM: Operative order endpoint.
        resp = self._session.get(
            f"{self.base_url}/orders/{operative_order_id}", timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def get_line_items(self, operative_order_id: str) -> list[dict[str, Any]]:
        # CONFIRM: Operative line-items endpoint.
        resp = self._session.get(
            f"{self.base_url}/orders/{operative_order_id}/line-items", timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("items", resp.json())
