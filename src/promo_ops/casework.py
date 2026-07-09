"""Salesforce-driven case processing — the routing pipeline.

Flow (per the team's chosen process):
  1. Planner fills the Plan+Targeting template, attaches it to a Case, and sets the
     Case Status to "Ready for Ad Ops".
  2. We pick the Case up, read core fields + the attached Targeting sheet, and
     VALIDATE. On problems: comment them back + set Status "Needs Info" (no create).
  3. Otherwise BUILD and CREATE the FreeWheel draft directly (NOT_BOOKED).
  4. COMMENT the IO link + CM to-dos back on the Case and set Status
     "Submitted to FreeWheel".

Design-first: `process_case` takes injected `sf` and `fw` clients, so the whole
pipeline is unit-tested with fakes before live Salesforce credentials exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .config import env
from .models import Order
from .order_builder import OrderBuilder
from .plan_loader import support_plan_from_dict, validate_plan


def io_url(network_id: str, campaign_id: str, io_id: str) -> str:
    return (f"https://mrm.freewheel.tv/app/{network_id}/advertising/campaigns/"
            f"{campaign_id}/?insertion_order_id={io_id}")


def cm_todos(order: Order) -> list[str]:
    """Manual steps the CM must finish before booking the IO."""
    todos = ["Map/create the Brand under the advertiser and set it on the IO."]
    placements = order.placements
    if any(p.recommended_show_value in (None, "") for p in placements
           if p.recommended_show_value is not None or getattr(p, "tier", None) == 1):
        todos.append("Replace the Recommended Show 'TBD' key-value with the ShowID "
                     "(or set Recommended Show ID on the Case).")
    # Targeting the API can't write (surfaced per placement).
    from .integrations.freewheel import FreeWheelClient
    needs_ui = set()
    for p in placements:
        body = FreeWheelClient._placement_body(p)
        for k in body.get("_cm_adds_in_ui", {}):
            needs_ui.add(k)
    for k in sorted(needs_ui):
        todos.append(f"Add in the FreeWheel UI: {k}.")
    # Unmatched targeting notes from the engine.
    for p in placements:
        for tier in p.targeting.tiers:
            for d in tier.dimensions:
                if d.notes:
                    todos.append(f"{p.name}: {d.notes}")
    return todos


@dataclass
class CaseResult:
    case_id: str
    ok: bool
    io_id: Optional[str] = None
    io_link: Optional[str] = None
    placements: int = 0
    validation: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def comment_body(self) -> str:
        if self.validation:
            return ("⚠️ Promo Ops could not build this campaign — please fix and re-flag:\n"
                    + "\n".join(f"• {p}" for p in self.validation))
        if self.error:
            return f"⚠️ Promo Ops hit an error creating the FreeWheel draft: {self.error}"
        lines = [f"✅ FreeWheel draft created (NOT_BOOKED): {self.io_link}",
                 f"{self.placements} placements built. CM to-dos before booking:"]
        lines += [f"• {t}" for t in self.todos]
        return "\n".join(lines)


def _io_from_result(res: dict) -> Optional[str]:
    io = (res or {}).get("insertion_order") or {}
    return ((io.get("data") or {}).get("insertion_order") or {}).get("id")


def process_case(case_id: str, *, sf, fw, create: bool = True,
                 builder: Optional[OrderBuilder] = None) -> CaseResult:
    """Run one Case through validate -> build -> create -> comment.

    `sf` = SalesforceClient (or a fake), `fw` = FreeWheelClient (or a fake). With
    create=False the FreeWheel call is a dry run (no live write).
    """
    plan = support_plan_from_dict(sf.case_to_plan_dict(case_id))

    problems = validate_plan(plan)
    if problems:
        result = CaseResult(case_id, ok=False, validation=problems)
        sf.post_case_comment(case_id, result.comment_body())
        sf.update_case_status(case_id, sf.NEEDS_INFO_STATUS)   # Status -> Needs Info
        return result

    order = (builder or OrderBuilder()).build(plan)
    todos = cm_todos(order)
    try:
        res = fw.create_order(order, dry_run=not create)
    except Exception as exc:  # surface the failure back on the Case, don't crash the poll
        result = CaseResult(case_id, ok=False, placements=len(order.placements),
                            todos=todos, error=str(exc))
        sf.post_case_comment(case_id, result.comment_body())
        sf.update_case_status(case_id, sf.NEEDS_INFO_STATUS)   # Status -> Needs Info
        return result

    io_id = _io_from_result(res)
    link = io_url(str(order.network_id or env("FREEWHEEL_NETWORK_ID") or ""),
                  str(order.campaign.get("resolved_id") or ""), str(io_id or "")) if io_id else None
    result = CaseResult(case_id, ok=True, io_id=io_id, io_link=link,
                        placements=len(order.placements), todos=todos)
    sf.post_case_comment(case_id, result.comment_body())
    sf.update_case_reason(case_id, sf.SUBMITTED_REASON)        # Reason -> Submitted to FreeWheel
    return result


def process_ready_cases(*, sf, fw, create: bool = True) -> list[CaseResult]:
    """Process every Case flagged READY_STATUS (the poll entry point)."""
    return [process_case(cid, sf=sf, fw=fw, create=create) for cid in sf.list_ready_cases()]
