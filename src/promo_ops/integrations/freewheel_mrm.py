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

    # --- writes ---------------------------------------------------------- #

    def _post_xml(self, path: str, body: str) -> ET.Element:
        def call() -> ET.Element:
            self._ensure_token()
            r = self._session.post(
                f"{self.base}{path}", data=body,
                headers={"Authorization": f"Bearer {self._token}",
                         "Content-Type": "application/xml", "accept": "application/xml"},
                timeout=60)
            if is_transient_status(r.status_code):
                raise TransientAPIError(r.status_code, f"MRM {path} temporarily unavailable")
            if r.status_code not in (200, 201):
                raise RuntimeError(f"MRM POST {path} -> HTTP {r.status_code}: {r.text[:200]!r}")
            return ET.fromstring(r.text)
        return with_retries(
            call, attempts=self._retry_attempts, base_delay=self._retry_base_delay,
            retry_on=lambda e: isinstance(e, (TransientAPIError, requests.exceptions.RequestException)),
            sleep=self._sleep)

    def find_brand(self, advertiser_id: str, name: str) -> Optional[str]:
        """Exact-name (case-insensitive) ACTIVE brand id under an advertiser, or None.
        Scans the live list so it sees brands created since the last sync."""
        want = " ".join(str(name or "").strip().lower().split())
        for b in self.list_brands(advertiser_id):
            if (b["status"] or "").upper() == "ACTIVE" \
                    and " ".join(b["name"].strip().lower().split()) == want:
                return b["id"]
        return None

    def create_brand(self, advertiser_id: str, name: str,
                     industry_id: Optional[str] = None) -> str:
        """Create a Brand under an advertiser and return its id. Only `name` is required;
        pass industry_id to set the Custom Industry (kids brands = Rating: G, id 5289)."""
        from xml.sax.saxutils import escape
        ind = (f"<industry><industry_id>{int(industry_id)}</industry_id></industry>"
               if industry_id else "")
        root = self._post_xml(f"/services/v3/advertisers/{advertiser_id}/brands",
                              f"<brand><name>{escape(name)}</name>{ind}</brand>")
        bid = self._text(root, "id")
        if not bid:
            raise RuntimeError(f"MRM create-brand returned no id: {ET.tostring(root)[:160]!r}")
        return bid

    def find_or_create_brand(self, advertiser_id: str, name: str,
                             industry_id: Optional[str] = None) -> tuple[str, bool]:
        """Return (brand_id, created?). Finds the brand by exact name, else creates it
        (with the given industry_id, e.g. kids -> Rating: G)."""
        existing = self.find_brand(advertiser_id, name)
        if existing:
            return existing, False
        return self.create_brand(advertiser_id, name, industry_id), True

    def brand_global_mapping(self, advertiser_id: str, brand_id: str) -> Optional[str]:
        """The GLOBAL_BRAND entity_id a brand is mapped to, or None. Empty means the
        matching global brand doesn't exist yet (must be created via 'Create a Brand in
        FW' so FreeWheel auto-maps it by name)."""
        root = self._get_xml(f"/services/v3/advertisers/{advertiser_id}/brands/{brand_id}")
        gm = root.find("global_mapping")
        if gm is None:
            return None
        eid = gm.find("entity_id")
        return (eid.text or "").strip() if eid is not None and eid.text else None

