"""Short-duration tier gate (global): :10/:20 creatives don't get the premium Tiers 1-2
when a premium length (:15/:30/:45/:60/:90) is also in the plan — the premium lengths carry
Tiers 1-4 and the short lengths only get Tiers 3-4. If ONLY short lengths are present, they
get the full stack. Verified against the CA "Moonies" plan that wrongly pushed Tier 1-2 :10s."""

from __future__ import annotations

from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _tiers_by_duration(order):
    """{duration: set(tier ids)} across the tiered video placements (tier + duration set)."""
    out: dict = {}
    for p in order.placements:
        if p.tier and p.duration is not None and not p.guaranteed:
            out.setdefault(int(p.duration), set()).add(int(p.tier))
    return out


def _order(durations, region="USA", campaign="Paramount + - USA"):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="NCIS", region=region, campaign={"name": campaign},
        durations=durations, showlist=["FBI"], genres=["Drama"])))


def test_short_gated_when_premium_present():
    # :30 + :15 + :10 -> premium lengths keep 1-4; :10 only 3-4.
    by = _tiers_by_duration(_order([30, 15, 10]))
    assert by.get(30) == {1, 2, 3, 4}
    assert by.get(15) == {1, 2, 3, 4}
    assert by.get(10) == {3, 4}
    assert 1 not in by.get(10, set()) and 2 not in by.get(10, set())


def test_twenty_also_gated():
    by = _tiers_by_duration(_order([30, 20]))
    assert by.get(30) == {1, 2, 3, 4}
    assert by.get(20) == {3, 4}


def test_short_only_gets_full_stack():
    # Only short lengths present -> no premium length, so they DO get Tiers 1-4.
    by = _tiers_by_duration(_order([10, 20]))
    assert by.get(10) == {1, 2, 3, 4}
    assert by.get(20) == {1, 2, 3, 4}


def test_ca_moonies_repro():
    # The reported CA plan: [30, 15, 10] -> the :10 must NOT carry Tiers 1-2.
    by = _tiers_by_duration(_order([30, 15, 10], region="CA",
                                   campaign="Paramount + - English - CA"))
    assert by.get(10) == {3, 4}
    assert by.get(30) == {1, 2, 3, 4} and by.get(15) == {1, 2, 3, 4}


def test_premium_only_unchanged():
    by = _tiers_by_duration(_order([30, 15]))
    assert by.get(30) == {1, 2, 3, 4} and by.get(15) == {1, 2, 3, 4}
