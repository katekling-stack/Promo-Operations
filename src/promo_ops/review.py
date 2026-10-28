"""The Review step: turn a plan into the checked preview a CM should read before anything is created.

Pure and local -- it builds the order from the tool's own config/data and NEVER calls FreeWheel.
Used by the hosted app (`/review`); the Tier 1 alert wording is shared with `promo-ops push`."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Order


def audience_alerts(order: Order) -> list[str]:
    """The Tier 1 audience alerts for a built order (a regional segment missing, nothing regional
    at all, hand-picked segments from another region), each line once, in order."""
    seen: list[str] = []
    for p in order.placements:
        for tier in p.targeting.tiers:
            for d in tier.dimensions:
                if d.key == "audience_segments" and d.notes:
                    for line in d.notes.split("\n"):
                        if line not in seen:
                            seen.append(line)
    return seen


def blocking_problems(order: Order) -> list[str]:
    """Reasons this order must NOT be pushed (each once). Today: Tier 1 with no audience at all --
    the plan names shows but none has a segment in the order's region, so Tier 1 would run across
    the whole platform at the top priority. Cleared by requesting a regional segment for at least
    one show."""
    problems: list[str] = []
    for p in order.placements:
        for tier in p.targeting.tiers:
            for d in tier.dimensions:
                if getattr(d, "blocking", False):
                    msg = (f"Tier 1 has no {order.region} audience segment for any show in this plan, so it "
                           f"would run across the whole platform. Request a {order.region} segment for at "
                           "least one show (see the request list), then push again.")
                    if msg not in problems:
                        problems.append(msg)
    return problems


def segment_requests(shows: list[str], region: str) -> list[dict[str, str]]:
    """Shows that still need a REGIONAL Tier 1 segment requested: {show, region, status, exists_as}.
    Status is "no segment anywhere" or "only in another region" (a standard / other-region segment
    exists but isn't used). Same classification the Tier 1 alerts and `promo-ops dda-requests` use."""
    from .audience_segments import AudienceSegmentResolver
    cov = AudienceSegmentResolver().load().region_coverage(list(shows or []), region)
    rows = [{"show": n, "region": region, "status": "no segment anywhere", "exists_as": ""} for n in cov["none"]]
    rows += [{"show": f["show"], "region": region, "status": "only in another region",
              "exists_as": f["using"]} for f in cov["elsewhere"]]
    return rows


def plan_fingerprint(raw: Any) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _dimension(d) -> dict[str, Any]:
    ids = [s.get("segment_id") for s in d.resolved if s.get("segment_id")] if d.key == "audience_segments" else []
    shown = [str(v) for v in d.values[:6]]
    return {"key": d.key, "label": d.label,
            "count": len(d.resolved) if d.key == "audience_segments" else len(d.values),
            "preview": ids[:6] if d.key == "audience_segments" else shown,
            "more": max(0, (len(ids) if d.key == "audience_segments" else len(d.values)) - 6),
            "resolved": len(d.resolved), "notes": d.notes}


def _placement(p) -> dict[str, Any]:
    return {"name": p.name, "format": p.format_code, "guaranteed": bool(p.guaranteed),
            "priority": p.priority_level, "frequency_cap": p.frequency_cap,
            "exclusions": list(p.exclusions or []),
            "tiers": [{"id": t.id, "name": t.name, "dimensions": [_dimension(d) for d in t.dimensions]}
                      for t in p.targeting.tiers]}


def _refused(*problems: str) -> dict[str, Any]:
    return {"ok": False, "blocked": False, "problems": list(problems), "summary": {}, "alerts": [],
            "placements": [], "requests": [], "plan_hash": None}


def review_plan(raw: Any) -> dict[str, Any]:
    """Preview of what pushing this plan would create. `ok` is False (with `problems`) when the plan
    can't be built or would create nothing."""
    from .order_builder import OrderBuilder
    from .plan_loader import support_plan_from_dict, validate_plan

    if not isinstance(raw, dict) or not raw:
        return _refused("That doesn't look like a plan file. Use the .plan.json the campaign form downloads.")
    try:
        plan = support_plan_from_dict(raw)
        problems = validate_plan(plan)
        if problems:
            return {**_refused(*problems), "plan_hash": plan_fingerprint(raw)}
        order = OrderBuilder().build(plan)
    except ValueError as exc:
        return _refused(str(exc))
    except Exception:  # noqa: BLE001 - a plan we can't read must not show internals
        return _refused("The tool couldn't read this plan. Re-download it from the form and try again.")

    if not order.placements:
        return {**_refused(
            f"This plan builds 0 placements, so nothing would be created for {order.campaign.get('name')!r}. "
            "Check the campaign's brand is set up in the tool, and (for a Kids campaign) that a Kids "
            "audience is selected."), "plan_hash": plan_fingerprint(raw)}

    existing = order.scene_lift_io_id or getattr(order, "existing_io_id", None)
    flight = order.flight
    blocked = blocking_problems(order)
    return {
        "ok": not blocked, "blocked": bool(blocked), "problems": blocked, "plan_hash": plan_fingerprint(raw),
        "summary": {
            "io_name": order.name, "brand": order.brand, "region": order.region,
            "advertiser": order.advertiser.get("name") or order.advertiser.get("name_contains"),
            "campaign": order.campaign.get("name"),
            "flight": f"{flight.start} to {flight.end}",
            "placements": len(order.placements),
            "destination": f"existing IO {existing}" if existing else "a new IO",
        },
        "alerts": audience_alerts(order),
        "requests": segment_requests(plan.showlist, order.region),
        "placements": [_placement(p) for p in order.placements],
    }
