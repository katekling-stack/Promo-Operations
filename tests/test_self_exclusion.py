"""Self-exclusion: the promoted show's own Video Series + Channel SGs are excluded on
every set (so it never promos against itself). Resolution needs synced series/SG data,
so we stub the resolvers to test the mechanism deterministically."""

from __future__ import annotations

from promo_ops.integrations.freewheel import FreeWheelClient
from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import load_plan


class _FakeSeries:
    def resolve(self, show, limit=200):
        from promo_ops.series import SeriesMatch
        return SeriesMatch(show=show, series=[{"id": "555001", "name": show}])

    def resolve_all(self, shows):
        return [self.resolve(s) for s in shows]


def test_series_resolver_matches_underscore_and_spaced_names():
    """(10 Streaming) / Network 10 series come underscored ("masterchef_australia")
    and spaced ("MasterChef Australia"). One keyword must catch BOTH — for the Tier-2
    showlist include AND self-exclusion."""
    from promo_ops.series import SeriesResolver
    ids = [s["id"] for s in SeriesResolver().load().resolve("MasterChef Australia").series]
    assert "1179587696" in ids   # masterchef_australia (underscored)
    assert "134200301" in ids    # MasterChef Australia (spaced)


def test_promoted_series_excluded_on_every_set(monkeypatch):
    builder = OrderBuilder()
    monkeypatch.setattr(builder.engine, "series_resolver", _FakeSeries())
    order = builder.build(load_plan("plans/frisco-king-usa.yaml"))
    # every remnant relationship set excludes the promoted show's own series
    remnant = [p for p in order.placements if not p.guaranteed and p.tier]
    assert remnant
    for p in remnant:
        assert "555001" in p.exclude_series
        body = FreeWheelClient._placement_body(p)
        for s in body["relationship_targeting"]["set"]:
            exc = s.get("content_targeting", {}).get("network_items", {}).get("exclude", {})
            assert "555001" in exc.get("series", [])
