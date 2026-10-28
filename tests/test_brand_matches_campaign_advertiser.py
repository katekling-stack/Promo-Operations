"""A picked Brand must belong to the advertiser that owns the campaign the IO goes into, or FreeWheel
refuses the IO ("The brand does not belong to the advertiser of the campaign").
Regression: a Kids campaign carried the ADULT "PAW Patrol ... (Promo) (USA)" brand (346844, adult
advertiser) when the Kids one exists ("... - Kids (Promo) (USA)", 346843, Kids advertiser)."""

from __future__ import annotations

import pytest

from promo_ops.brands_resolver import BrandResolver
from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict

CSV = """region,kids,advertiser_id,advertiser_name,brand_id,brand_name
USA,0,1000520,VCBS English - USA - Adult (Promo),346844,PAW Patrol: The Dino Movie (Promo) (USA)
USA,1,1000521,VCBS English - USA - Kids (Promo),346843,PAW Patrol: The Dino Movie - Kids (Promo) (USA)
USA,0,1000520,VCBS English - USA - Adult (Promo),111,Only Adult Film (Promo) (USA)
USA,1,1000521,VCBS English - USA - Kids (Promo),222,Same Name (Promo) (USA)
USA,0,1000520,VCBS English - USA - Adult (Promo),333,Same Name (Promo) (USA)
"""


@pytest.fixture
def resolver(tmp_path):
    f = tmp_path / "brands.csv"
    f.write_text(CSV, encoding="utf-8")
    return BrandResolver(f).load()


def test_a_brand_is_found_under_the_campaigns_advertiser(resolver):
    kids = "1000521"
    # the adult name resolves to the kids variant of the same title
    assert resolver.find_for_advertiser("USA", "PAW Patrol: The Dino Movie (Promo) (USA)", kids) == "346843"
    # a name that exists under BOTH advertisers resolves to the one that matches
    assert resolver.find_for_advertiser("USA", "Same Name (Promo) (USA)", kids) == "222"
    assert resolver.find_for_advertiser("USA", "Same Name (Promo) (USA)", "1000520") == "333"
    # nothing under that advertiser -> None (the tool will create it there)
    assert resolver.find_for_advertiser("USA", "Only Adult Film (Promo) (USA)", kids) is None


def test_the_advertiser_of_a_brand_id_is_known(resolver):
    assert resolver.advertiser_of("346844") == "1000520" and resolver.advertiser_of("346843") == "1000521"
    assert resolver.advertiser_of("nope") is None


def _kids_order(resolver, monkeypatch, io_brand):
    monkeypatch.setattr("promo_ops.brands_resolver.BrandResolver.load", lambda self: resolver)
    order = OrderBuilder().build(support_plan_from_dict({
        "promoted_title": "Paw Patrol", "region": "USA", "campaign": {"name": "Paramount + - Kids - USA"},
        "durations": [30], "genres": ["Kids"], "kids_audience": ["younger"], "io_brand": io_brand,
        "flight": {"start": "2026-11-01", "end": "2026-12-01"}}))
    order.brand_id = resolver.resolve("USA", io_brand)
    return order


def _client(created):
    c = FreeWheelClient.__new__(FreeWheelClient)
    c._campaign_advertiser = lambda cid: "1000521"
    c.resolve_campaign_id = lambda n: "54440942"

    def inv(tool, **kw):
        if "create-an-insertion-order" in tool:
            created.append(kw["body"])
            return {"data": {"insertion_order": {"id": "777"}}}
        return {"ok": True}
    c._invoke = inv
    return c


def test_create_swaps_a_wrong_advertiser_brand_for_the_matching_one(resolver, monkeypatch):
    order = _kids_order(resolver, monkeypatch, "PAW Patrol: The Dino Movie (Promo) (USA)")
    assert order.brand_id == "346844"                       # what the plan resolved to: the ADULT brand
    created = []
    _client(created).create_order(order, dry_run=False)
    assert created[0]["brand_id"] == "346843"               # the Kids advertiser's brand went out


def test_a_correct_brand_is_left_alone(resolver, monkeypatch):
    order = _kids_order(resolver, monkeypatch, "PAW Patrol: The Dino Movie - Kids (Promo) (USA)")
    created = []
    _client(created).create_order(order, dry_run=False)
    assert created[0]["brand_id"] == "346843"


def test_a_push_error_prints_a_plain_message_not_a_traceback(tmp_path, monkeypatch, capsys):
    import json
    from promo_ops import cli
    f = tmp_path / "p.plan.json"
    f.write_text(json.dumps({"promoted_title": "T", "region": "UK", "campaign": {"name": "Paramount + - UK"},
                             "durations": [30], "genres": ["Comedy"],
                             "flight": {"start": "2026-10-01", "end": "2026-11-01"}}), encoding="utf-8")

    def boom(order, target, live):
        raise RuntimeError("FreeWheel couldn't create the Insertion Order: something specific")
    monkeypatch.setattr(cli, "_push_target", boom)
    rc = cli.main(["push", str(f), "--target", "freewheel", "--live"])
    err = capsys.readouterr().err
    assert rc == 2 and "something specific" in err and "Traceback" not in err
