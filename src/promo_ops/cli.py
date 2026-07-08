"""Command-line interface for promo-ops.

    promo-ops build   <plan.yaml> [--out FILE]     build Order+Placements -> JSON
    promo-ops preview <plan.yaml>                   human-readable tier breakdown
    promo-ops push    <plan.yaml> --target NAME     push (dry-run unless --live)
    promo-ops build-from-sheet <SHEET_ID> [--out F] build from a campaign-plan sheet
    promo-ops from-case <CASE_ID> [--out FILE]      build from a Salesforce Case
    promo-ops sync-segments                         refresh audience-segment CSVs

Build/preview require no credentials. push/from-case/sync-segments talk to external
systems and read credentials from the environment (.env).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from .models import Order
from .order_builder import OrderBuilder
from .plan_loader import load_plan, support_plan_from_dict


def _order_to_json(order: Order) -> str:
    return json.dumps(dataclasses.asdict(order), indent=2, ensure_ascii=False)


def _cmd_build(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    order = OrderBuilder().build(plan)
    out = _order_to_json(order)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(out)
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    order = OrderBuilder().build(plan)
    _print_preview(order)
    return 0


def _print_preview(order: Order) -> None:
    adv = order.advertiser.get("name") or order.advertiser.get("name_contains") or "(set Advertiser)"
    adv_id = order.advertiser.get("resolved_id")
    print(f"ADVERTISER: {adv}" + (f"  (id {adv_id})" if adv_id else ""))
    print(f"  CAMPAIGN (existing parent): {order.campaign.get('name')}"
          + (f"  (id {order.campaign.get('resolved_id')})" if order.campaign.get('resolved_id') else ""))
    print(f"    INSERTION ORDER (new): {order.name}")
    print(f"      Region: {order.region}   Network: {order.network_id}")
    tmpl = order.template_ref
    if tmpl.get("template_io_id"):
        print(f"      Model after IO: {tmpl.get('template_io_id')}")
    print(f"      Placements: {len(order.placements)}")
    for p in order.placements:
        tag = "  ⟨GUARANTEED → existing order⟩" if p.guaranteed else ""
        meta = []
        if p.priority_level is not None:
            meta.append(f"priority={p.priority_level}")
        if p.frequency_cap:
            meta.append(f"cap={p.frequency_cap}")
        print(f"\n  PLACEMENT: {p.name}  [{p.format_code}]{tag}")
        if meta:
            print(f"    {'   '.join(meta)}")
        if p.exclusions:
            print(f"    Exclude (label): {', '.join(p.exclusions)}")
        if p.guaranteed:
            print(f"    Arguments: genre={p.arguments.get('genre')} | recommended_show={p.arguments.get('recommended_show')!r}")
        for tier in p.targeting.tiers:
            print(f"    Tier {tier.id} — {tier.name}")
            for d in tier.dimensions:
                if d.key == "audience_segments":
                    ids = [s.get("segment_id") or "(no id)" for s in d.resolved]
                    print(f"      • {d.key}: {len(d.resolved)} segment(s) resolved"
                          f"{' [' + ', '.join(ids) + ']' if ids else ''}")
                    if d.notes:
                        print(f"          ! {d.notes}")
                else:
                    preview = ", ".join(str(v) for v in d.values[:6])
                    more = f" (+{len(d.values) - 6} more)" if len(d.values) > 6 else ""
                    suffix = ""
                    if d.resolved and d.resolved[0].get("id") is not None:
                        suffix = f"  [{len(d.resolved)}/{len(d.values)} resolved to FW IDs]"
                    print(f"      • {d.key}: {preview}{more}{suffix}")
                    if d.notes and d.key != "audience_segments":
                        print(f"          ! {d.notes}")


def _push_target(order: Order, target: str, live: bool) -> dict[str, Any]:
    if target == "freewheel":
        from .integrations.freewheel import FreeWheelClient
        return FreeWheelClient().create_order(order, dry_run=not live)
    if target == "gam":
        from .integrations.gam import GoogleAdManagerClient
        return GoogleAdManagerClient().create_order(order, dry_run=not live)
    raise ValueError(f"Unknown target: {target}")


def _cmd_push(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    order = OrderBuilder().build(plan)
    result = _push_target(order, args.target, args.live)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not args.live:
        print("\n(dry-run — pass --live to actually create)", file=sys.stderr)
    return 0


def _cmd_from_case(args: argparse.Namespace) -> int:
    from .integrations.salesforce import SalesforceClient
    plan_dict = SalesforceClient().case_to_plan_dict(args.case_id)
    plan = support_plan_from_dict(plan_dict)
    order = OrderBuilder().build(plan)
    out = _order_to_json(order)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(out)
    return 0


def _cmd_build_from_sheet(args: argparse.Namespace) -> int:
    from .integrations.gsheets import read_plan_template
    plan_dict = read_plan_template(args.sheet_id)
    plan = support_plan_from_dict(plan_dict)
    order = OrderBuilder().build(plan)
    out = _order_to_json(order)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(out)
    return 0


def _cmd_sync_segments(args: argparse.Namespace) -> int:
    from .integrations.gsheets import sync_audience_segments
    written = sync_audience_segments(sheet_id=args.sheet_id)
    print(f"Synced {len(written)} tab(s):")
    for p in written:
        print(f"  {p}")
    return 0


def _cmd_sync_attributes(args: argparse.Namespace) -> int:
    from .integrations.freewheel import FreeWheelClient
    written = FreeWheelClient().sync_standard_attributes()
    print(f"Synced {len(written)} standard-attribute type(s):")
    for p in written:
        print(f"  {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="promo-ops", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build Order+Placements to JSON")
    p_build.add_argument("plan")
    p_build.add_argument("--out")
    p_build.set_defaults(func=_cmd_build)

    p_prev = sub.add_parser("preview", help="Human-readable tier breakdown")
    p_prev.add_argument("plan")
    p_prev.set_defaults(func=_cmd_preview)

    p_push = sub.add_parser("push", help="Push to an external system")
    p_push.add_argument("plan")
    p_push.add_argument("--target", required=True, choices=["freewheel", "gam"])
    p_push.add_argument("--live", action="store_true", help="Actually create (default dry-run)")
    p_push.set_defaults(func=_cmd_push)

    p_case = sub.add_parser("from-case", help="Build from a Salesforce Case")
    p_case.add_argument("case_id")
    p_case.add_argument("--out")
    p_case.set_defaults(func=_cmd_from_case)

    p_sheet = sub.add_parser("build-from-sheet", help="Build from a campaign-plan Google Sheet")
    p_sheet.add_argument("sheet_id")
    p_sheet.add_argument("--out")
    p_sheet.set_defaults(func=_cmd_build_from_sheet)

    p_sync = sub.add_parser("sync-segments", help="Refresh audience-segment CSVs from the sheet")
    p_sync.add_argument("--sheet-id")
    p_sync.set_defaults(func=_cmd_sync_segments)

    p_attr = sub.add_parser("sync-attributes", help="Refresh Standard Attribute CSVs from FreeWheel")
    p_attr.set_defaults(func=_cmd_sync_attributes)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
