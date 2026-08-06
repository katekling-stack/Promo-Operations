"""After Mid-Roll Bumper is a Domestic (US) product only — its format members must not
survive into a plan for any other market, whatever the brand config / Products toggle says."""

from __future__ import annotations

from promo_ops.plan_loader import support_plan_from_dict, DOMESTIC_ONLY_FORMATS


def _formats(region, campaign):
    plan = support_plan_from_dict(dict(
        promoted_title="X", region=region, campaign={"name": campaign},
        durations=[30], product_overrides={"after_midroll_bumper": True}))
    return set(plan.formats)


def test_after_midroll_bumper_dropped_outside_us():
    # International MTVE: the member format is stripped even when explicitly toggled on.
    assert not (DOMESTIC_ONLY_FORMATS & _formats("GSA", "MTVE - GSA"))
    assert not (DOMESTIC_ONLY_FORMATS & _formats("LATAM", "MTVE - LATAM"))


def test_after_midroll_bumper_kept_for_us():
    # Domestic MTVE keeps it.
    assert DOMESTIC_ONLY_FORMATS & _formats("USA", "MTVE - USA")
