"""Batch intake — one spreadsheet, one row per Salesforce case, all drafts in one run.

The daily-volume answer to "we set 20+ cases live per day." Instead of the one-at-a-time
form → plan-file → push loop, Ad Ops keeps a single sheet (Google Sheets is an approved
connector, or a plain CSV export) with one ROW per case. Each row is a full campaign plan:
a "Salesforce Case" column to match it back, the campaign/title/flight, and the targeting
as `;`-separated cells. `process_batch` builds + creates every row's FreeWheel draft
(idempotently — re-running never duplicates) and returns a per-case summary that maps
Salesforce Case # → FreeWheel IO id / link / status, written back out as a results CSV.

Design mirrors casework.process_case but with NO Salesforce dependency: the sheet IS the
intake. When the Salesforce API user lands later, poll-cases reuses the very same builder.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .casework import _io_from_result, cm_todos, io_url
from .config import env
from .integrations.gsheets import PLAN_TAB_FIELDS
from .integrations.salesforce import _split
from .order_builder import OrderBuilder
from .plan_loader import support_plan_from_dict, validate_plan

# Batch columns = every Plan-tab field (friendly label -> plan path) plus the targeting +
# exclude lists, which in a flat one-row-per-case sheet live in their own `;`-separated
# cells. Header matching is case-insensitive and trims a trailing "(...)" qualifier, so
# "Audience Segments (Tier 1)" still maps to audience_segments.
BATCH_COLUMNS: dict[str, dict[str, Any]] = dict(PLAN_TAB_FIELDS)
BATCH_COLUMNS.update({
    "genres": {"path": ["genres"], "type": "list"},
    "showlist": {"path": ["showlist"], "type": "list"},
    "pluto categories": {"path": ["pluto", "categories"], "type": "list"},
    "pluto channels": {"path": ["pluto", "channels"], "type": "list"},
    "audience segments": {"path": ["audience_segments"], "type": "list"},
    "kids audience": {"path": ["kids_audience"], "type": "list"},
    "networks": {"path": ["networks"], "type": "list"},
    "exclude series": {"path": ["exclude_series"], "type": "list"},
    "exclude channels": {"path": ["exclude_channels"], "type": "list"},
})

_TRUE_VALUES = {"y", "yes", "true", "x", "1", "✓"}


def _normalize_header(label: str) -> str:
    """Lower-case, trim, and drop a trailing parenthetical qualifier so
    'Audience Segments (Tier 1)' matches the 'audience segments' column."""
    label = label.strip().lower()
    if "(" in label:
        label = label.split("(", 1)[0].strip()
    return label


def _set_nested(target: dict[str, Any], path: list[str], value: Any) -> None:
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def row_to_plan_dict(row: dict[str, str]) -> dict[str, Any]:
    """Map one sheet row (header -> cell) into a plan dict, reusing the Plan-tab paths.
    List cells are `;`-separated; blanks are skipped; unknown columns are ignored."""
    plan: dict[str, Any] = {}
    for header, raw in row.items():
        if header is None:
            continue
        spec = BATCH_COLUMNS.get(_normalize_header(header))
        if not spec:
            continue
        raw = (raw or "").strip()
        if raw == "":
            continue
        kind = spec.get("type")
        if kind == "list":
            value: Any = _split(raw)
        elif kind == "bool":
            value = raw.lower() in _TRUE_VALUES
        else:
            value = raw
        _set_nested(plan, spec["path"], value)
    return plan


def load_batch_csv(path) -> list[dict[str, str]]:
    """Read a batch CSV into a list of header->cell dicts (one per case row).
    Rows that are entirely blank are dropped."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh)]
    return [r for r in rows if any((v or "").strip() for v in r.values())]


@dataclass
class BatchResult:
    """One case row's outcome — the Salesforce-Case-matched line of the run summary."""
    row: int                                   # 1-based data row (matches the sheet)
    salesforce_case: str = ""
    title: str = ""
    region: str = ""
    campaign: str = ""
    io_name: str = ""
    status: str = "error"                      # created | reused | dry-run | needs-info | error
    io_id: Optional[str] = None
    io_link: Optional[str] = None
    placements: int = 0
    problems: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status in ("created", "reused", "dry-run")

    def to_record(self) -> dict[str, Any]:
        note = self.error or ("; ".join(self.problems) if self.problems else "")
        return {
            "row": self.row, "salesforce_case": self.salesforce_case,
            "title": self.title, "region": self.region, "campaign": self.campaign,
            "io_name": self.io_name, "status": self.status,
            "io_id": self.io_id or "", "io_link": self.io_link or "",
            "placements": self.placements, "note": note,
        }


RESULT_COLUMNS = ["row", "salesforce_case", "title", "region", "campaign",
                  "io_name", "status", "io_id", "io_link", "placements", "note"]


def process_row(index: int, row: dict[str, str], *, fw, create: bool,
                builder: Optional[OrderBuilder] = None,
                network_id: str = "") -> BatchResult:
    """Validate → build → create one row's FreeWheel draft (idempotent). Never raises:
    a bad row becomes a needs-info / error result so the batch keeps going."""
    plan_dict = row_to_plan_dict(row)
    case = str(plan_dict.get("salesforce_case") or "")
    res = BatchResult(row=index, salesforce_case=case)
    try:
        plan = support_plan_from_dict(plan_dict)
    except Exception as exc:                                   # malformed row
        res.status, res.error = "error", str(exc)
        return res
    res.title = plan.promoted_title or ""
    res.region = plan.region or ""
    res.campaign = str((plan.campaign or {}).get("name") or "")

    problems = validate_plan(plan)
    if problems:
        res.status, res.problems = "needs-info", problems
        return res

    try:
        order = (builder or OrderBuilder()).build(plan)
    except Exception as exc:
        res.status, res.error = "error", str(exc)
        return res
    res.io_name = order.name
    res.placements = len(order.placements)
    res.todos = cm_todos(order)
    net = str(order.network_id or network_id or env("FREEWHEEL_NETWORK_ID") or "")
    # Campaign id for the IO link + idempotency check: the plan's resolved id if present,
    # else resolve the campaign by name (the same lookup create_order does live).
    campaign_id = str(order.campaign.get("resolved_id") or "")
    if create and not campaign_id and hasattr(fw, "resolve_campaign_id"):
        try:
            campaign_id = str(fw.resolve_campaign_id(order.campaign.get("name", "")) or "")
        except Exception:
            campaign_id = ""

    # Idempotency: reuse an existing IO of this name under the campaign, never duplicate.
    if create and campaign_id and hasattr(fw, "find_insertion_order_by_name"):
        existing = fw.find_insertion_order_by_name(campaign_id, order.name)
        if existing:
            res.status, res.io_id = "reused", str(existing)
            res.io_link = io_url(net, campaign_id, str(existing))
            return res

    try:
        result = fw.create_order(order, dry_run=not create)
    except Exception as exc:
        res.status, res.error = "error", str(exc)
        return res
    io_id = _io_from_result(result)
    res.io_id = str(io_id) if io_id else None
    campaign_id = str((result or {}).get("campaign_id") or campaign_id or "")
    if io_id and campaign_id:
        res.io_link = io_url(net, campaign_id, str(io_id))
    res.status = "created" if create else "dry-run"
    return res


def process_batch(rows: list[dict[str, str]], *, fw, create: bool = False,
                  builder: Optional[OrderBuilder] = None,
                  network_id: str = "") -> list[BatchResult]:
    """Process every case row. `create=False` (default) is a dry run — nothing is written
    to FreeWheel — so a planner can preview the whole sheet before going live."""
    b = builder or OrderBuilder()
    return [process_row(i, row, fw=fw, create=create, builder=b, network_id=network_id)
            for i, row in enumerate(rows, start=1)]


def write_results_csv(results: list[BatchResult], path) -> None:
    """Write the per-case summary (Case # → IO link / status) as a results CSV."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        w.writeheader()
        for r in results:
            w.writerow(r.to_record())


def render_batch_summary(results: list[BatchResult], create: bool) -> str:
    """A terminal summary: counts + one line per case (Salesforce Case → IO / status)."""
    n = len(results)
    created = sum(1 for r in results if r.status == "created")
    reused = sum(1 for r in results if r.status == "reused")
    dry = sum(1 for r in results if r.status == "dry-run")
    needs = sum(1 for r in results if r.status == "needs-info")
    errors = sum(1 for r in results if r.status == "error")
    mode = "LIVE" if create else "DRY-RUN"
    head = [f"Batch {mode}: {n} case(s)"]
    tallies = []
    if created: tallies.append(f"{created} created")
    if reused: tallies.append(f"{reused} reused")
    if dry: tallies.append(f"{dry} would-create")
    if needs: tallies.append(f"{needs} needs-info")
    if errors: tallies.append(f"{errors} error")
    if tallies:
        head.append("  " + " · ".join(tallies))
    lines = [""]
    icon = {"created": "✅", "reused": "♻️", "dry-run": "•",
            "needs-info": "⚠️", "error": "❌"}
    for r in results:
        who = r.salesforce_case or f"row {r.row}"
        tail = (r.io_link or r.io_name or "")
        if r.status in ("needs-info", "error"):
            tail = r.error or "; ".join(r.problems)
        lines.append(f"  {icon.get(r.status, '?')} {who:<16} {r.region:<6} "
                     f"{r.placements or '':>2} pl  {r.status:<10} {tail}")
    return "\n".join(head + lines)
