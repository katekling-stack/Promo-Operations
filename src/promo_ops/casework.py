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

import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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
    addons: list[str] = field(default_factory=list)   # VD / takeover notes + links
    error: Optional[str] = None

    def summary(self) -> dict[str, Any]:
        """Compact record for the run log (one line per Case)."""
        return {"case_id": self.case_id, "ok": self.ok, "io_id": self.io_id,
                "io_link": self.io_link, "placements": self.placements,
                "needs_info": self.validation or None, "error": self.error}

    def comment_body(self) -> str:
        if self.validation:
            return ("⚠️ Promo Ops could not build this campaign — please fix and re-flag:\n"
                    + "\n".join(f"• {p}" for p in self.validation))
        if self.error:
            return f"⚠️ Promo Ops hit an error creating the FreeWheel draft: {self.error}"
        lines = [f"✅ FreeWheel draft created (NOT_BOOKED): {self.io_link}",
                 f"{self.placements} placements built. CM to-dos before booking:"]
        lines += [f"• {t}" for t in self.todos]
        if self.addons:
            lines.append("Add-ons (Video Domination / Takeover):")
            lines += [f"• {a}" for a in self.addons]
        return "\n".join(lines)


def _process_addons(plan, order, fw, create: bool, network_id: str) -> list[str]:
    """Handle the plan's Video Domination + Takeover add-ons: push the Pluto VD as its
    own draft IO; surface Operative VD / takeover bookings as CM to-dos. Returns notes
    for the Case comment. Never raises — an add-on failure is reported, not fatal."""
    from .addons import build_addons
    notes: list[str] = []
    built = build_addons(plan)
    vd, tk = built["video_domination"], built["takeover"]
    if vd and vd.engine == "freewheel":                       # Pluto VD -> FreeWheel draft
        if vd.unresolved_categories:
            notes.append(f"Pluto VD: no SG match for categories {vd.unresolved_categories} "
                         "— check the region's Pluto category names.")
        cid = plan.campaign.get("resolved_id")
        vd_name = vd.freewheel_placement["name"]
        if not cid:
            notes.append("Pluto VD ready but campaign id missing — could not push.")
        elif create and hasattr(fw, "find_insertion_order_by_name") and \
                fw.find_insertion_order_by_name(str(cid), vd_name):
            existing = fw.find_insertion_order_by_name(str(cid), vd_name)
            notes.append(f"Pluto Video Domination already exists (reused): "
                         f"{io_url(network_id, str(cid), str(existing))}")
        else:
            try:
                res = fw.create_addon_order(
                    cid, vd_name, [vd.freewheel_placement],
                    flight={"start": plan.flight.start, "end": plan.flight.end},
                    dry_run=not create)
                vio = _io_from_result(res)
                notes.append(f"Pluto Video Domination draft: {io_url(network_id, str(cid), str(vio))}"
                             if vio else "Pluto Video Domination built (dry-run).")
            except Exception as exc:
                notes.append(f"Pluto VD could not be created: {exc}")
    elif vd and vd.engine == "operative":                     # Operative VD -> booking to-do
        notes.append(f"Video Domination ({vd.label}): copy Operative order {vd.operative_order_id} "
                     f"“{vd.operative_order_name}”, set dates, push to GAM. {vd.note or ''}".strip())
    if tk:                                                     # Takeover -> booking to-do
        notes.append(f"Takeover ({tk.label}): book in Operative as “{tk.operative_order_name}” "
                     f"with {len(tk.product_lines)} product line(s), then Push All to GAM under "
                     f"{tk.gam_push_advertiser}.")
    return notes


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
    network_id = str(order.network_id or env("FREEWHEEL_NETWORK_ID") or "")
    campaign_id = str(order.campaign.get("resolved_id") or "")

    # Idempotency: if an IO with this name already exists under the campaign, reuse it
    # instead of creating a duplicate (safe re-flagging / poll retries).
    if create and campaign_id and hasattr(fw, "find_insertion_order_by_name"):
        existing = fw.find_insertion_order_by_name(campaign_id, order.name)
        if existing:
            link = io_url(network_id, campaign_id, str(existing))
            result = CaseResult(case_id, ok=True, io_id=str(existing), io_link=link,
                                placements=len(order.placements), todos=todos,
                                addons=["Existing draft reused — no duplicate created. "
                                        "Delete the IO first to rebuild."])
            sf.post_case_comment(case_id, result.comment_body())
            sf.update_case_reason(case_id, sf.SUBMITTED_REASON)
            return result

    try:
        res = fw.create_order(order, dry_run=not create)
    except Exception as exc:  # surface the failure back on the Case, don't crash the poll
        result = CaseResult(case_id, ok=False, placements=len(order.placements),
                            todos=todos, error=str(exc))
        sf.post_case_comment(case_id, result.comment_body())
        sf.update_case_status(case_id, sf.NEEDS_INFO_STATUS)   # Status -> Needs Info
        return result

    io_id = _io_from_result(res)
    link = io_url(network_id, campaign_id, str(io_id or "")) if io_id else None
    addon_notes = _process_addons(plan, order, fw, create, network_id)
    result = CaseResult(case_id, ok=True, io_id=io_id, io_link=link,
                        placements=len(order.placements), todos=todos, addons=addon_notes)
    sf.post_case_comment(case_id, result.comment_body())
    sf.update_case_reason(case_id, sf.SUBMITTED_REASON)        # Reason -> Submitted to FreeWheel
    return result


def process_ready_cases(*, sf, fw, create: bool = True) -> list[CaseResult]:
    """Process every Case flagged READY_STATUS (the poll entry point)."""
    return [process_case(cid, sf=sf, fw=fw, create=create) for cid in sf.list_ready_cases()]


@dataclass
class PollCycle:
    """Summary of one poll pass over the Ready queue."""
    cycle: int
    results: list[CaseResult] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def processed(self) -> int:
        return len(self.results)

    @property
    def submitted(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def needs_info(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    def render(self) -> str:
        if self.error:
            return f"cycle {self.cycle}: ERROR polling Ready queue — {self.error}"
        if not self.results:
            return f"cycle {self.cycle}: no Cases ready."
        return (f"cycle {self.cycle}: {self.processed} processed "
                f"({self.submitted} submitted, {self.needs_info} needs-info).")

    def to_record(self, ts: str) -> dict[str, Any]:
        """One JSONL run-log record for this cycle."""
        return {"ts": ts, "cycle": self.cycle, "processed": self.processed,
                "submitted": self.submitted, "needs_info": self.needs_info,
                "error": self.error, "cases": [r.summary() for r in self.results]}


def run_poll_cycle(*, sf, fw, create: bool = True) -> PollCycle:
    """One poll pass. A failure LISTING the queue is caught (so the daemon survives a
    transient Salesforce error); per-Case failures are already handled in process_case."""
    try:
        results = process_ready_cases(sf=sf, fw=fw, create=create)
    except Exception as exc:
        return PollCycle(cycle=0, error=str(exc))
    return PollCycle(cycle=0, results=results)


def _default_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def append_run_log(path, cycle: PollCycle, now: Callable[[], str] = _default_now) -> None:
    """Append one JSONL record for a poll cycle (audit trail for the unattended loop)."""
    import json
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(cycle.to_record(now()), ensure_ascii=False) + "\n")


def read_run_log(path) -> dict[str, Any]:
    """Aggregate a JSONL run log into a status summary."""
    import json
    from pathlib import Path
    p = Path(path)
    recs: list[dict] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {
        "cycles": len(recs),
        "submitted": sum(r.get("submitted", 0) for r in recs),
        "needs_info": sum(r.get("needs_info", 0) for r in recs),
        "errors": sum(1 for r in recs if r.get("error")),
        "last_ts": recs[-1]["ts"] if recs else None,
        "last": recs[-1] if recs else None,
    }


def poll_loop(*, sf, fw, interval: float, create: bool = True,
              max_cycles: Optional[int] = None,
              on_cycle: Optional[Callable[[PollCycle], None]] = None,
              sleep: Callable[[float], None] = _time.sleep,
              log_path=None, now: Callable[[], str] = _default_now) -> list[PollCycle]:
    """Run the Ready-queue poll on an interval. Idempotent per-Case, so overlapping or
    repeated cycles never create duplicate IOs. `max_cycles` bounds the run (None = run
    forever); `log_path` persists a JSONL record per cycle; `sleep`/`on_cycle`/`now` are
    injectable for tests. Returns the cycle summaries."""
    cycles: list[PollCycle] = []
    n = 0
    while max_cycles is None or n < max_cycles:
        n += 1
        pc = run_poll_cycle(sf=sf, fw=fw, create=create)
        pc.cycle = n
        (on_cycle or (lambda c: print(c.render())))(pc)
        if log_path:
            append_run_log(log_path, pc, now=now)
        cycles.append(pc)
        if max_cycles is not None and n >= max_cycles:
            break
        sleep(interval)
    return cycles
