"""FreeWheel MRM REST client (OAuth2 client-credentials -> XML).

Separate from the Streaming Hub client (integrations/freewheel.py, which is JSON/OAuth-PKCE
and can't read Brands). This one authenticates with the PromoAdOps INTERNAL API app
credentials against the MRM Publisher API and reads the endpoints the Hub can't:

  Auth:  POST https://api.freewheel.tv/auth/token  grant_type=client_credentials
         (client_id + client_secret from env) -> Bearer token
  Read:  GET  /services/v3/advertisers[/{id}/brands]  with Accept: application/xml
         (these endpoints return XML only — "json is not supported")

Used by scripts/sync_brands.py to pull the advertiser Brand lists for the form's Brand
picker. Credentials come from FREEWHEEL_MRM_CLIENT_ID / FREEWHEEL_MRM_CLIENT_SECRET.
"""

from __future__ import annotations

import re
import time
from typing import Optional
from xml.etree import ElementTree as ET

import requests

from ..config import env, require_env
from ..retry import TransientAPIError, is_transient_status, with_retries

API_BASE = "https://api.freewheel.tv"
TOKEN_URL = f"{API_BASE}/auth/token"


class FreeWheelMRMClient:
    def __init__(self):
        self.base = env("FREEWHEEL_MRM_BASE_URL", API_BASE).rstrip("/")
        self._client_id = require_env("FREEWHEEL_MRM_CLIENT_ID")
        self._client_secret = require_env("FREEWHEEL_MRM_CLIENT_SECRET")
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._retry_attempts = int(env("FREEWHEEL_RETRY_ATTEMPTS", "4"))
        self._retry_base_delay = float(env("FREEWHEEL_RETRY_BASE_DELAY", "2"))
        self._sleep = time.sleep

    # --- auth ------------------------------------------------------------ #

    def _authenticate(self) -> str:
        r = self._session.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials",
                  "client_id": self._client_id, "client_secret": self._client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "accept": "application/json"},
            timeout=30)
        if is_transient_status(r.status_code):
            raise TransientAPIError(r.status_code, "FreeWheel MRM auth temporarily unavailable")
        try:
            tok = r.json()
        except ValueError:
            raise RuntimeError(f"MRM token endpoint returned non-JSON (HTTP {r.status_code}): "
                               f"{r.text[:120]!r}")
        self._token = tok.get("access_token")
        if not self._token:
            raise RuntimeError(f"MRM token request failed (HTTP {r.status_code}): {tok}")
        # Refresh a minute before expiry.
        self._token_exp = time.time() + int(tok.get("expires_in", 3600)) - 60
        return self._token

    def _ensure_token(self) -> str:
        if not self._token or time.time() >= self._token_exp:
            self._authenticate()
        return self._token  # type: ignore[return-value]

    # --- reads (XML) ----------------------------------------------------- #

    def _get_xml(self, path: str, params: Optional[dict] = None) -> ET.Element:
        def call() -> ET.Element:
            self._ensure_token()
            r = self._session.get(
                f"{self.base}{path}", params=params or {},
                headers={"Authorization": f"Bearer {self._token}", "accept": "application/xml"},
                timeout=60)
            if is_transient_status(r.status_code):
                raise TransientAPIError(r.status_code, f"MRM {path} temporarily unavailable")
            if r.status_code != 200:
                raise RuntimeError(f"MRM {path} -> HTTP {r.status_code}: {r.text[:160]!r}")
            return ET.fromstring(r.text)
        return with_retries(
            call, attempts=self._retry_attempts, base_delay=self._retry_base_delay,
            retry_on=lambda e: isinstance(e, (TransientAPIError, requests.exceptions.RequestException)),
            sleep=self._sleep)

    @staticmethod
    def _text(el: ET.Element, tag: str) -> str:
        child = el.find(tag)
        return (child.text or "").strip() if child is not None and child.text else ""

    def _paged(self, path: str, item_tag: str, extra: Optional[dict] = None, per_page: int = 100):
        """Yield each <item_tag> element across all pages of a list endpoint."""
        page = 1
        while True:
            root = self._get_xml(path, {**(extra or {}), "per_page": per_page, "page": page})
            items = root.findall(item_tag)
            for it in items:
                yield it
            total_pages = int(root.get("total_pages") or 1)
            if page >= total_pages or not items:
                break
            page += 1

    def list_advertisers(self, name_contains: str = "VCBS") -> list[dict]:
        out = []
        for a in self._paged("/services/v3/advertisers", "advertiser", {"name": name_contains}):
            name = self._text(a, "name")
            if name_contains.lower() in name.lower():
                out.append({"id": self._text(a, "id"), "name": name,
                            "status": self._text(a, "status")})
        return out

    def list_brands(self, advertiser_id: str) -> list[dict]:
        """All brands under an advertiser: [{id, name, status}]."""
        out = []
        for b in self._paged(f"/services/v3/advertisers/{advertiser_id}/brands", "brand"):
            out.append({"id": self._text(b, "id"), "name": self._text(b, "name"),
                        "status": self._text(b, "status")})
        return out
