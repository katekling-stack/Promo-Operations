"""Per-breakout targeting: the optional (10 Streaming) AU lines and (My5) UK lines can carry
their OWN showlist / genres / audience segments / ratings. A field the breakout section sets
replaces the main value on those lines only; a field it leaves empty inherits the main
value. Main lines and the plan object itself are never touched."""

from __future__ import annotations

from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict
from promo_ops.ratings import RatingRestrictionResolver

AU = dict(promoted_title="Traitors Australia", region="AU",
          campaign={"name": "Paramount + - AU"}, content_type="show",
          content_id="956519957", season_or_messaging="Sell", durations=[30],
          showlist=["NCIS"], genres=["Sports"])

UK = dict(promoted_title="Frasier", region="UK", campaign={"name": "Paramount + - UK"},
          durations=[30], genres=["Comedy"], showlist=["Cheers"],
          recommended_show_id="970002006", content_type="show")


def _dim_values(p, key):
    out = []
    for t in p.targeting.tiers:
        for d in t.dimensions:
            if d.key == key:
                out += list(d.values)
    return out


def _split(order, tag):
    breakout = [p for p in order.placements if tag in p.name]
    main = [p for p in order.placements if tag not in p.name and p.tier]
    assert breakout and main, (len(breakout), len(main))
    return breakout, main


def _build(base, po, breakout=None):
    raw = {**base, "product_overrides": po}
    if breakout is not None:
        raw["breakout_targeting"] = breakout
    plan = support_plan_from_dict(raw)
    return plan, OrderBuilder().build(plan)


def test_au_10_streaming_overrides_apply_only_to_those_lines():
    r = RatingRestrictionResolver().load()
    excl = set(r.resolve("AU", ["R18+"]))
    incl = set(r.resolve("AU", ["M"]))
    assert excl and incl
    _, order = _build(AU, {"network_10": True}, {"network_10": {
        "showlist": ["Landman"], "genres": ["Drama"], "audience_segments": ["SEG-X"],
        "rating_restrictions": ["R18+"], "rating_inclusions": ["M"]}})
    n10, main = _split(order, "(10 Streaming)")

    for p in n10:
        assert set(_dim_values(p, "content_affinity_showlist")) <= {"Landman"}
        assert set(_dim_values(p, "genre")) <= {"Drama"}
        assert excl <= set(p.extra_exclude_video_groups)
        assert incl <= set(p.rating_include_video_groups)
    assert any("Landman" in _dim_values(p, "content_affinity_showlist") for p in n10)
    assert any("Drama" in _dim_values(p, "genre") for p in n10)
    assert any("SEG-X" in _dim_values(p, "audience_segments") for p in n10)

    for p in main:                       # main lines keep the main plan's targeting
        assert "Landman" not in _dim_values(p, "content_affinity_showlist")
        assert "Drama" not in _dim_values(p, "genre")
        assert "SEG-X" not in _dim_values(p, "audience_segments")
        assert not (excl & set(p.extra_exclude_video_groups))
        assert not (incl & set(p.rating_include_video_groups))
    assert any("NCIS" in _dim_values(p, "content_affinity_showlist") for p in main)
    assert any("Sports" in _dim_values(p, "genre") for p in main)


def test_partial_override_inherits_everything_else():
    _, order = _build(AU, {"network_10": True}, {"network_10": {"showlist": ["Landman"]}})
    n10, _ = _split(order, "(10 Streaming)")
    assert any("Landman" in _dim_values(p, "content_affinity_showlist") for p in n10)
    assert any("Sports" in _dim_values(p, "genre") for p in n10)        # genres inherited
    assert not any("NCIS" in _dim_values(p, "content_affinity_showlist") for p in n10)


def test_no_breakout_targeting_leaves_breakout_lines_on_main_targeting():
    _, order = _build(AU, {"network_10": True})
    n10, _ = _split(order, "(10 Streaming)")
    assert any("NCIS" in _dim_values(p, "content_affinity_showlist") for p in n10)
    assert any("Sports" in _dim_values(p, "genre") for p in n10)


def test_my5_breakout_overrides_apply_only_to_my5_lines():
    _, order = _build(UK, {"my5_breakout": True}, {"my5_breakout": {
        "showlist": ["Taskmaster"], "genres": ["Entertainment"]}})
    my5, main = _split(order, "(My5)")
    assert any("Taskmaster" in _dim_values(p, "content_affinity_showlist") for p in my5)
    assert any("Entertainment" in _dim_values(p, "genre") for p in my5)
    for p in main:
        assert "Taskmaster" not in _dim_values(p, "content_affinity_showlist")
        assert "Entertainment" not in _dim_values(p, "genre")


def test_a_breakout_override_for_the_other_product_is_ignored():
    # my5 overrides must not leak onto 10 Streaming lines (or vice versa).
    _, order = _build(AU, {"network_10": True}, {"my5_breakout": {"showlist": ["Taskmaster"]}})
    n10, _ = _split(order, "(10 Streaming)")
    assert not any("Taskmaster" in _dim_values(p, "content_affinity_showlist") for p in n10)


def test_building_does_not_mutate_the_plan():
    plan, _ = _build(AU, {"network_10": True}, {"network_10": {
        "showlist": ["Landman"], "genres": ["Drama"], "rating_restrictions": ["R18+"]}})
    assert plan.showlist == ["NCIS"] and plan.genres == ["Sports"]
    assert plan.rating_restrictions == []


def test_loader_normalizes_breakout_targeting():
    plan = support_plan_from_dict({**AU, "breakout_targeting": {
        "network_10": {"showlist": ["Landman", "", "  "], "genres": [],
                       "audience_segments": ["A"], "bogus_field": ["x"]},
        "not_a_breakout": {"showlist": ["Z"]}}})
    assert plan.breakout_targeting == {"network_10": {"showlist": ["Landman"],
                                                      "audience_segments": ["A"]}}
    assert support_plan_from_dict(AU).breakout_targeting == {}
