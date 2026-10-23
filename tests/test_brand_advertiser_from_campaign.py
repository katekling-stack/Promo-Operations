"""The IO Brand is created under the advertiser that OWNS the campaign the IO is going into.

FreeWheel rejects an IO whose Brand belongs to a different advertiser than its campaign
("The brand (id: N) does not belong to the advertiser of the campaign"). Guessing the advertiser
from region + a kids flag broke for campaigns whose real advertiser differs from that guess
(Pluto TV - Kids - BR sits under the kids advertiser while its config wasn't flagged kids), and
left a stray Brand behind under the wrong advertiser. The campaign itself is the source of truth;
the region mapping is only the fallback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from promo_ops.brands_resolver import BrandResolver
from promo_ops.integrations import freewheel_mrm
from promo_ops.integrations.freewheel import FreeWheelClient


class _FakeMRM:
    calls: list[tuple] = []

    def find_or_create_brand(self, advertiser_id, name, industry_id=None):
        _FakeMRM.calls.append((str(advertiser_id), name, industry_id))
        return "999", True

    def brand_global_mapping(self, advertiser_id, brand_id):
        return "1"


@pytest.fixture
def client(monkeypatch):
    for k in ("FREEWHEEL_NETWORK_ID", "FREEWHEEL_USERNAME", "FREEWHEEL_PASSWORD",
              "FREEWHEEL_MRM_CLIENT_ID", "FREEWHEEL_MRM_CLIENT_SECRET"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setattr(freewheel_mrm, "FreeWheelMRMClient", _FakeMRM)
    _FakeMRM.calls = []
    return FreeWheelClient()


def _order(region="BR", kids=False):
    return SimpleNamespace(io_brand="Kung Fu Panda - Kids (Promo) (BR)", brand_id=None,
                           region=region, io_brand_kids=kids)


def _campaign_reply(advertiser_id):
    return {"data": {"campaign": {"id": "72285933", "advertiser_id": advertiser_id}}}


def test_brand_goes_under_the_campaigns_own_advertiser(client, monkeypatch):
    seen = []
    monkeypatch.setattr(client, "_invoke",
                        lambda tool, **kw: seen.append((tool, kw)) or _campaign_reply("1207830"))
    heuristic = BrandResolver().load().advertiser_for("BR", False)
    assert str(heuristic) != "1207830"          # the region guess would have been wrong here

    note = client._ensure_io_brand(_order(kids=False), campaign_id="72285933")

    assert _FakeMRM.calls[0][0] == "1207830"
    assert note["advertiser_id"] == "1207830"
    assert seen and seen[0][1]["campaign_id"] == 72285933


def test_falls_back_to_the_region_mapping_when_the_campaign_cant_be_read(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("network blip")
    monkeypatch.setattr(client, "_invoke", boom)

    client._ensure_io_brand(_order(kids=False), campaign_id="72285933")

    assert _FakeMRM.calls[0][0] == str(BrandResolver().load().advertiser_for("BR", False))


def test_falls_back_when_the_campaign_reply_has_no_advertiser(client, monkeypatch):
    monkeypatch.setattr(client, "_invoke", lambda tool, **kw: {"data": {"campaign": {}}})

    client._ensure_io_brand(_order(kids=True), campaign_id="72285933")

    assert _FakeMRM.calls[0][0] == str(BrandResolver().load().advertiser_for("BR", True))


def test_no_campaign_id_means_no_lookup_and_the_old_behavior(client, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("must not call FreeWheel when there is no campaign id")
    monkeypatch.setattr(client, "_invoke", forbidden)

    client._ensure_io_brand(_order(kids=False))

    assert _FakeMRM.calls[0][0] == str(BrandResolver().load().advertiser_for("BR", False))


def test_a_region_with_no_mapping_still_works_when_the_campaign_is_known(client, monkeypatch):
    monkeypatch.setattr(client, "_invoke", lambda tool, **kw: _campaign_reply("4242"))

    note = client._ensure_io_brand(_order(region="ZZ"), campaign_id="72285933")

    assert _FakeMRM.calls[0][0] == "4242" and note["advertiser_id"] == "4242"


def test_a_region_with_no_mapping_and_no_campaign_still_warns_instead_of_guessing(client):
    note = client._ensure_io_brand(_order(region="ZZ"))

    assert "No (Promo) advertiser mapping" in note["warning"] and not _FakeMRM.calls
