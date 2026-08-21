"""Command-line interface for promo-ops.

    promo-ops build   <plan.yaml> [--out FILE]     build Order+Placements -> JSON
    promo-ops preview <plan.yaml>                   human-readable tier breakdown
    promo-ops push    <plan.yaml> --target NAME     push (dry-run unless --live)
    promo-ops build-from-sheet <SHEET_ID> [--out F] build from a campaign-plan sheet
    promo-ops salesforce-check                       preflight SF login + Case schema
    promo-ops from-case <CASE_ID> [--live]          validate+build+create from a Case
    promo-ops poll-cases [--live]                   process all "Ready for Ad Ops" Cases
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
from .retry import TransientAPIError


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


def _cmd_mirror(args: argparse.Namespace) -> int:
    """Mirror a source plan to one or more other markets (same title, swap country)."""
    import yaml
    from . import mirror as _mirror
    raw = yaml.safe_load(Path(args.plan).read_text(encoding="utf-8"))
    targets: list[str] = []
    for chunk in args.to:
        targets.extend(t.strip() for t in chunk.split(",") if t.strip())
    result = _mirror.mirror_to_markets(raw, targets)
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.plan).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    title = str(raw.get("promoted_title") or "plan")
    slug = "".join(c.lower() if c.isalnum() else "-" for c in title).strip("-")
    for region, plan in result["plans"].items():
        dest = out_dir / f"{slug}-{region.lower()}.plan.json"
        dest.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {region}: {plan['campaign']['name']}  ->  {dest}")
    for region, reason in result["skipped"].items():
        print(f"  {region}: SKIPPED — {reason}")
    if not result["plans"]:
        print("No markets mirrored.")
        return 1
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
                    elif d.resolved and d.resolved[0].get("segment_name"):
                        suffix = f'  [e.g. "{d.resolved[0]["segment_name"]}"]'
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
    try:
        result = _push_target(order, args.target, args.live)
    except TransientAPIError as e:
        # FreeWheel gateway hiccup (e.g. a 502 outage) — a clear message, not a traceback.
        code = getattr(e, "status", None)
        print(f"\n⚠️  FreeWheel's service is temporarily unavailable"
              f"{f' (HTTP {code})' if code else ''} — nothing was created.\n\n"
              "This is a FreeWheel-side hiccup, not a problem with your plan, your login, "
              "or the tool. Wait a few minutes and re-run the exact same command.",
              file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    brand = isinstance(result, dict) and result.get("brand")
    if brand:
        if brand.get("warning"):
            print(f"\n⚠️  Brand: {brand['warning']}", file=sys.stderr)
        elif brand.get("created"):
            extra = f" (Industry {brand['industry']})" if brand.get("industry") else ""
            print(f"\n🏷️  Created Brand {brand['name']!r} (id {brand['brand_id']}){extra} and "
                  "mapped it to the IO.", file=sys.stderr)
        if brand.get("global_mapping_missing"):
            print(f"❗ {brand.get('action')}", file=sys.stderr)
    if not args.live:
        print("\n(dry-run — pass --live to actually create)", file=sys.stderr)
    return 0


def _cmd_addons(args: argparse.Namespace) -> int:
    """Build the Video Domination + Takeover add-ons; optionally push the Pluto VD."""
    from dataclasses import asdict
    from .addons import build_addons
    plan = load_plan(args.plan)
    addons = build_addons(plan)
    vd, tk = addons["video_domination"], addons["takeover"]
    out = {"video_domination": asdict(vd) if vd else None,
           "takeover": asdict(tk) if tk else None}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if vd and vd.unresolved_categories:
        print(f"\n⚠️  Unresolved Pluto categories (no SG match): {vd.unresolved_categories}",
              file=sys.stderr)
    if args.live and vd and vd.engine == "freewheel":
        from .integrations.freewheel import FreeWheelClient
        cid = plan.campaign.get("resolved_id")
        if not cid:
            print("Set campaign.resolved_id to push the Pluto VD.", file=sys.stderr)
            return 2
        res = FreeWheelClient().create_addon_order(
            cid, vd.freewheel_placement["name"], [vd.freewheel_placement],
            flight={"start": plan.flight.start, "end": plan.flight.end}, dry_run=False)
        io_id = ((res.get("insertion_order") or {}).get("data") or {}).get("insertion_order", {}).get("id")
        print(f"\nPushed Pluto VD -> IO {io_id}", file=sys.stderr)
    elif not args.live:
        print("\n(dry-run — pass --live to push the Pluto VD to FreeWheel)", file=sys.stderr)
    return 0


def _cmd_from_case_file(args: argparse.Namespace) -> int:
    """Run the exact Case → plan → order pipeline from a LOCAL Case-fields JSON (+ an
    optional Targeting CSV) — no Salesforce needed. For demos/testing the SF path."""
    import csv as _csv
    from .integrations.salesforce import build_plan_dict
    from .addons import build_addons, render_booking_worksheet
    from .plan_loader import support_plan_from_dict, validate_plan
    with open(args.case_file, encoding="utf-8") as fh:
        case_fields = json.load(fh)
    rows = None
    if args.targeting:
        with open(args.targeting, encoding="utf-8-sig", newline="") as fh:
            rows = list(_csv.reader(fh))
    plan = support_plan_from_dict(build_plan_dict(case_fields, rows))
    problems = validate_plan(plan)
    if problems:
        print("⚠️  Needs info — the Case can't be built yet:")
        for p in problems:
            print(f"  • {p}")
        return 1
    order = OrderBuilder().build(plan)
    print(f"Case → {order.name}")
    print(f"  brand: {plan.brand}  region: {plan.region}  campaign: {order.campaign.get('name')}")
    print(f"  {len(order.placements)} placements built:")
    for p in order.placements:
        print(f"    • {p.name}")
    sheet = render_booking_worksheet(build_addons(plan))
    if "nothing to book" not in sheet:
        print("\n" + sheet)
    if args.live:
        from .integrations.freewheel import FreeWheelClient
        res = FreeWheelClient().create_order(order, dry_run=False)
        io = ((res.get("insertion_order") or {}).get("data") or {}).get("insertion_order") or {}
        print(f"\nCreated FreeWheel draft IO {io.get('id')}")
    else:
        print("\n(dry-run — pass --live to create the FreeWheel draft)", file=sys.stderr)
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    """Build + create every case in ONE CSV (one row per Salesforce case). Dry-run by
    default; --live creates the NOT_BOOKED drafts. Idempotent — re-running reuses IOs."""
    from .batch import (load_batch_csv, process_batch, render_batch_summary,
                        write_results_csv)
    if args.sheet:
        from .integrations.gsheets import read_cases_tab
        rows = read_cases_tab(args.sheet, tab=args.tab)
        source = f"sheet {args.sheet} (tab {args.tab!r})"
    elif args.cases_csv:
        rows = load_batch_csv(args.cases_csv)
        source = args.cases_csv
    else:
        print("Provide a CSV path or --sheet <id>.", file=sys.stderr)
        return 1
    if not rows:
        print(f"No case rows found in {source}", file=sys.stderr)
        return 1
    # dry-run still builds each order's planned calls (no network); --live authenticates
    # and creates. Same pattern as `push`.
    from .integrations.freewheel import FreeWheelClient
    fw = FreeWheelClient()
    results = process_batch(rows, fw=fw, create=args.live)
    print(render_batch_summary(results, create=args.live))
    if args.out:
        write_results_csv(results, args.out)
        print(f"\nResults written to {args.out}", file=sys.stderr)
    if not args.live:
        print("\n(dry-run — pass --live to create the FreeWheel drafts)", file=sys.stderr)
    # Non-zero exit if any row failed to build (needs-info / error), so a scheduled run
    # surfaces problems.
    return 0 if all(r.ok for r in results) else 2


def _cmd_booking_sheet(args: argparse.Namespace) -> int:
    """Print the Operative/GAM booking worksheet for a plan's VD + takeover."""
    from .addons import build_addons, render_booking_worksheet
    print(render_booking_worksheet(build_addons(load_plan(args.plan))))
    return 0


def _cmd_gam_check(args: argparse.Namespace) -> int:
    """Preflight the GAM connection (run once GAM API access lands)."""
    from .integrations.gam import GoogleAdManagerClient
    try:
        info = GoogleAdManagerClient().preflight()
    except Exception as exc:
        print(f"⚠️  Could not connect to GAM: {exc}", file=sys.stderr)
        print("Check .env (GAM_NETWORK_CODE, GAM_SERVICE_ACCOUNT_JSON) and API access.",
              file=sys.stderr)
        return 2
    print(f"✅ GAM connected — network {info['network_code']} ({info['display_name']}).")
    return 0


def _cmd_salesforce_check(args: argparse.Namespace) -> int:
    """Preflight the Salesforce connection + Case schema (run once creds land)."""
    from .integrations.salesforce import SalesforceClient
    try:
        report = SalesforceClient().preflight()
    except Exception as exc:
        print(f"⚠️  Could not connect to Salesforce: {exc}", file=sys.stderr)
        print("Check .env (SALESFORCE_* vars); set SALESFORCE_DOMAIN=test for a sandbox.",
              file=sys.stderr)
        return 2
    print(report.render())
    return 0 if report.ok else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    """One-shot health check: confirm the data files are present and every credential
    actually logs in, BEFORE a live push — so a missing file or bad cred surfaces here
    instead of mid-push. Prints a ✅/❌ line per check and exits non-zero on any failure."""
    from .config import REPO_ROOT
    checks: list[tuple[bool, str]] = []

    def _rows(rel: str) -> int:
        p = REPO_ROOT / rel
        if not p.exists():
            return -1
        with p.open() as fh:
            return max(0, sum(1 for _ in fh) - 1)  # minus header

    # 1) Data snapshots the engine reads (empty/missing => Tier 1 / brands silently blank).
    seg = _rows("data/audience_segments/synced_audience_items.csv")
    checks.append((seg > 0,
                   f"Audience-segment data: {seg} rows" if seg > 0 else
                   "Audience-segment data MISSING/empty "
                   "(data/audience_segments/synced_audience_items.csv) — Tier 1 won't populate. "
                   "Run: promo-ops sync-audience-items, or re-pull the repo."))
    brands = _rows("data/brands/synced_brands.csv")
    checks.append((brands > 0,
                   f"Brand data: {brands} rows" if brands > 0 else
                   "Brand data MISSING/empty (data/brands/synced_brands.csv) — known brands "
                   "won't resolve. Re-pull the repo or run the brand sync."))

    # 2) FreeWheel login (username/password) — the core push connection.
    try:
        from .integrations.freewheel import FreeWheelClient
        FreeWheelClient().authenticate()
        checks.append((True, "FreeWheel login: OK"))
    except Exception as exc:
        checks.append((False, f"FreeWheel login FAILED: {exc}. "
                              "Check FREEWHEEL_USERNAME / FREEWHEEL_PASSWORD / "
                              "FREEWHEEL_NETWORK_ID in .env."))

    # 3) MRM login (client-credentials) — needed to auto-create/map the IO Brand on push.
    from .config import env
    if not (env("FREEWHEEL_MRM_CLIENT_ID") and env("FREEWHEEL_MRM_CLIENT_SECRET")):
        checks.append((False, "MRM creds not set — the IO Brand won't be auto-created on push "
                              "(you'd set it by hand). Add FREEWHEEL_MRM_CLIENT_ID / "
                              "FREEWHEEL_MRM_CLIENT_SECRET to .env."))
    else:
        try:
            from .integrations.freewheel_mrm import FreeWheelMRMClient
            FreeWheelMRMClient()._authenticate()
            checks.append((True, "MRM login: OK (IO Brand will auto-create/map on push)"))
        except Exception as exc:
            checks.append((False, f"MRM login FAILED: {exc}. Re-check the MRM client id/secret "
                                  "in .env — paste only the value, no 'Client ID:' label, no quotes."))

    for ok, msg in checks:
        print(f"{'✅' if ok else '❌'} {msg}")
    all_ok = all(ok for ok, _ in checks)
    print("\n" + ("✅ All checks passed — you're clear to push." if all_ok
                  else "❌ Fix the ❌ items above before pushing."), file=sys.stderr)
    return 0 if all_ok else 1


def _cmd_from_case(args: argparse.Namespace) -> int:
    """Process one Case: validate -> build -> create draft (--live) -> comment back."""
    from .casework import process_case
    from .integrations.salesforce import SalesforceClient
    from .integrations.freewheel import FreeWheelClient
    result = process_case(args.case_id, sf=SalesforceClient(), fw=FreeWheelClient(),
                          create=args.live)
    print(result.comment_body())
    return 0 if result.ok else 1


def _cmd_poll_cases(args: argparse.Namespace) -> int:
    """Process Cases flagged Ready for Ad Ops. One-shot by default; --watch loops on
    --interval (idempotent, so repeated cycles never duplicate IOs)."""
    from .casework import poll_loop, run_poll_cycle
    from .integrations.salesforce import SalesforceClient
    from .integrations.freewheel import FreeWheelClient
    sf, fw = SalesforceClient(), FreeWheelClient()

    def _log(pc):
        print(pc.render(), file=sys.stderr)
        for r in pc.results:
            print(f"  [{'OK' if r.ok else 'SKIP'}] {r.case_id}: "
                  f"{r.io_link or (r.validation or r.error)}")

    if args.watch:
        poll_loop(sf=sf, fw=fw, interval=args.interval, create=args.live,
                  max_cycles=args.max_cycles, on_cycle=_log, log_path=args.log_file)
    else:
        pc = run_poll_cycle(sf=sf, fw=fw, create=args.live)
        _log(pc)
        if args.log_file:
            from .casework import append_run_log
            append_run_log(args.log_file, pc)
    if not args.live:
        print("\n(dry-run — pass --live to create drafts)", file=sys.stderr)
    return 0


def _cmd_daily_digest(args: argparse.Namespace) -> int:
    """Render a shareable daily digest from the poll run log."""
    from .casework import read_run_records, daily_digest, render_digest
    day = args.day
    if day is None and not args.all:
        from datetime import datetime
        day = datetime.now().strftime("%Y-%m-%d")
    d = daily_digest(read_run_records(args.log_file), day=day)
    print(render_digest(d))
    return 0


def _cmd_poll_status(args: argparse.Namespace) -> int:
    """Summarize the poll run log (audit trail)."""
    from .casework import read_run_log
    s = read_run_log(args.log_file)
    if not s["cycles"]:
        print(f"No run log at {args.log_file} yet.")
        return 0
    print(f"Run log: {args.log_file}")
    print(f"  cycles run : {s['cycles']}  (last: {s['last_ts']})")
    print(f"  submitted  : {s['submitted']}")
    print(f"  needs-info : {s['needs_info']}")
    print(f"  cycle errors: {s['errors']}")
    last = s["last"] or {}
    if last.get("cases"):
        print("  last cycle:")
        for c in last["cases"]:
            mark = "OK" if c.get("ok") else "SKIP"
            print(f"    [{mark}] {c.get('case_id')}: {c.get('io_link') or c.get('needs_info') or c.get('error')}")
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


def _cmd_sync_audience_items(args: argparse.Namespace) -> int:
    from .integrations.freewheel import FreeWheelClient
    path = FreeWheelClient().sync_audience_items()
    print(f"Synced audience items -> {path}")
    return 0


def _cmd_sync_series(args: argparse.Namespace) -> int:
    from .integrations.freewheel import FreeWheelClient
    print("Syncing the full Video Series index (~229k) — this takes a few minutes…")
    path = FreeWheelClient().sync_series()
    print(f"Synced series -> {path}")
    return 0


def _cmd_sync_all(args: argparse.Namespace) -> int:
    """Refresh every local FreeWheel data snapshot the form + engine rely on (series,
    audience items, standard attributes, audience segments). Run once after install and
    whenever FreeWheel adds new series/segments."""
    from .integrations.freewheel import FreeWheelClient
    fw = FreeWheelClient()
    print("Refreshing all FreeWheel data snapshots…")
    print("  1/3 series (~229k, a few minutes)…"); fw.sync_series()
    print("  2/3 audience items…");                fw.sync_audience_items()
    print("  3/3 standard attributes…");           fw.sync_standard_attributes()
    print("Done. (Segments sync separately via `promo-ops sync-segments` if you use a sheet.)")
    print("Tip: rebuild the form to match — python scripts/build_targeting_options.py && "
          "python -c \"from scripts.build_plan_form import build; build()\"")
    return 0


def _cmd_refresh_form(args: argparse.Namespace) -> int:
    """Weekly one-shot: refresh EVERY FreeWheel data snapshot the picker depends on, then
    rebuild the option lists + the plan form — so the team's dropdowns show the latest
    series / site groups / audiences / attributes. Upload the printed HTML to Drive after."""
    import subprocess
    from .config import REPO_ROOT
    from .integrations.freewheel import FreeWheelClient
    fw = FreeWheelClient()
    print("Refreshing FreeWheel data snapshots (a few minutes — series is the slow one)…")
    # Each step is isolated: one source failing (e.g. a transient API hiccup) still lets
    # the rest refresh and the form rebuild from whatever is freshest.
    steps = [
        ("series (~229k)",        fw.sync_series),
        ("audience items",        fw.sync_audience_items),
        ("standard attributes",   fw.sync_standard_attributes),
        ("Pluto site groups",     fw.sync_site_groups),
        ("genre Video Groups",    fw.sync_genre_video_groups),
        ("brand Video Groups",    fw.sync_brand_video_groups),
    ]
    ok = 0
    for i, (label, fn) in enumerate(steps, 1):
        print(f"  [{i}/{len(steps)}] {label}…")
        try:
            fn(); ok += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"      ⚠️  skipped {label}: {exc}", file=sys.stderr)
    # Optional: audience-segment sheet (needs Google creds); never blocks the refresh.
    try:
        from .integrations.gsheets import sync_audience_segments
        sync_audience_segments()
        print("  [+] audience segments (sheet)…")
    except Exception:
        pass
    # Refresh the affinity historicals corpus so newly-launched titles get picked up.
    try:
        from .history import build_corpus
        ids = [c for c in (fw.resolve_campaign_id(n) for n in DEFAULT_HISTORY_CAMPAIGNS) if c]
        if ids:
            build_corpus(fw, ids, REPO_ROOT / "data" / "history" / "corpus.jsonl", max_ios_per_campaign=25)
            print("  [+] historicals corpus…")
    except Exception as exc:  # noqa: BLE001
        print(f"      ⚠️  skipped historicals: {exc}", file=sys.stderr)
    print("Rebuilding option lists + form…")
    for script in ("build_targeting_options.py", "build_plan_form.py"):
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script)], check=True)
    form = REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html"
    print(f"\n✅ Done ({ok}/{len(steps)} sources refreshed). Upload this to Drive as a NEW "
          f"VERSION (keeps the team's link):\n   {form}")
    return 0 if ok else 1


def _cmd_from_brief(args: argparse.Namespace) -> int:
    """Parse a promo brief (.docx or .txt — labeled lists OR a prose marketing brief),
    resolve its key affinities (shows, genres, DMAs) against the catalogs, print a
    matched/review/not-found report, and write a DRAFT plan.json of the confirmed terms."""
    from .brief import read_brief, parse_brief, resolve_brief, to_plan_dict, report_text
    text = read_brief(args.brief)
    draft = parse_brief(text)
    resolved = resolve_brief(draft, region=args.region)
    print(report_text(draft, resolved))
    plan = to_plan_dict(draft, resolved, region=args.region, campaign_name=args.campaign)
    if args.durations:
        plan["durations"] = [int(d) for d in args.durations.split(",") if d.strip()]
    out = Path(args.out) if args.out else Path(args.brief).with_suffix(".plan.json")
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote draft plan → {out}")
    print("Review it, add durations/campaign, then: promo-ops preview " + str(out))
    return 0


def _cmd_suggest(args: argparse.Namespace) -> int:
    """Cold-start affinity suggester for a THIN brief: from a title + description, propose
    targeting grounded in our real inventory (AI engine), and/or by analogy to past plans
    (--history DIR). Writes a draft plan.json of the confirmed picks."""
    from .suggest import suggest_ai, suggest_history, load_past_plans, suggestion_to_fields
    desc = args.description or (Path(args.desc_file).read_text(encoding="utf-8") if args.desc_file else "")
    fields: dict[str, list] = {}
    if args.genres:
        fields["genres"] = [g.strip() for g in args.genres.split(",") if g.strip()]
    if not args.history_only:
        try:
            sug = suggest_ai(args.title, desc, region=args.region)
        except Exception as exc:  # noqa: BLE001 - no key/SDK is a common, expected case
            print(f"AI suggester unavailable ({exc}).\nSet ANTHROPIC_API_KEY and `pip install "
                  "anthropic`, or use --history DIR for the past-plans engine.", file=sys.stderr)
            return 2
        for f, fp in sug.fields.items():
            print(f"{f}: ✅ {', '.join(fp.matched)}"
                  + (f"  | ❌ dropped: {', '.join(fp.missed)}" if fp.missed else ""))
        fields = suggestion_to_fields(sug)
    # Historicals: explicit --history path/dir, else the default harvested corpus.
    from .history import load_corpus
    from .config import REPO_ROOT
    hist_src = args.history or (REPO_ROOT / "data" / "history" / "corpus.jsonl")
    corpus = load_corpus(hist_src)
    if corpus:
        hist = suggest_history(args.title, fields.get("genres", []), corpus, region=args.region)
        print("\n[history] " + (hist.notes[0] if hist.notes else ""))
        for f, fp in hist.fields.items():
            if fp.matched:
                fields.setdefault(f, [])
                fields[f] += [v for v in fp.matched if v not in fields[f]]
    plan = {"promoted_title": args.title, "region": args.region,
            "campaign": {"name": args.campaign or ""},
            "genres": fields.get("genres", []), "showlist": fields.get("showlist", [])}
    pluto = {k2: fields[k1] for k1, k2 in
             (("pluto_categories", "categories"), ("pluto_channels", "channels")) if fields.get(k1)}
    if pluto:
        plan["pluto"] = pluto
    if args.durations:
        plan["durations"] = [int(d) for d in args.durations.split(",") if d.strip()]
    out = Path(args.out) if args.out else Path(f"{args.title}.plan.json".replace("/", "-"))
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote draft plan → {out}  (review, then: promo-ops preview {out})")
    return 0


# Seed campaigns to learn historicals from (per Ad Ops) — broad genre buckets that reflect
# what actually ran. Re-run periodically so newly-launched titles get picked up.
DEFAULT_HISTORY_CAMPAIGNS = ["CBS Network - USA", "Paramount + - USA", "Pluto TV - USA"]


def _cmd_sync_history(args: argparse.Namespace) -> int:
    """Harvest past FreeWheel IOs from the given campaigns into a historicals corpus the
    affinity suggester learns from (title + genres + showlist + Pluto channels, per region).
    Re-run on a cadence to stay current with recently-launched titles."""
    from .integrations.freewheel import FreeWheelClient
    from .history import build_corpus
    from .config import REPO_ROOT, brands_config
    fw = FreeWheelClient()
    if getattr(args, "all", False):
        # Every promo campaign across all regions (from brands.yaml) — localized history per
        # region, so a UK promo learns from UK, USA from USA, etc.
        names = sorted({b["campaign_name"] for b in brands_config().get("brands", {}).values()
                        if b.get("campaign_name")})
    else:
        names = [n.strip() for n in (args.campaigns.split(";") if args.campaigns else DEFAULT_HISTORY_CAMPAIGNS) if n.strip()]
    print(f"Resolving {len(names)} campaign(s)…")
    ids = []
    for n in names:
        cid = fw.resolve_campaign_id(n)
        print(f"  {n} -> {cid or 'NOT FOUND'}")
        if cid:
            ids.append(cid)
    if not ids:
        print("No campaigns resolved — nothing to harvest.", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else REPO_ROOT / "data" / "history" / "corpus.jsonl"
    print(f"Harvesting up to {args.max_ios} IOs per campaign (reads each placement's targeting)…")
    print("Wrote " + build_corpus(fw, ids, out, max_ios_per_campaign=args.max_ios,
                                  progress=lambda m: print(m, flush=True)))
    return 0


def _cmd_dda_requests(args: argparse.Namespace) -> int:
    """Flag the plan's affinity shows that don't have a DDA segment yet (per region), so a CM
    knows which to request via the audience form. Prints the list + writes a CSV (show,
    region). The campaign form shows the same flag live under the Showlist field."""
    import csv as _csv
    from .audience_segments import AudienceSegmentResolver
    if args.plan:
        plan = load_plan(args.plan)
        shows, region = plan.showlist, plan.region
    else:
        shows = [s.strip() for s in (args.shows or "").split(";") if s.strip()]
        region = args.region
    have, need = AudienceSegmentResolver().load().missing_dda(shows, region)
    print(f"Region {region} — {len(have)} show(s) already have a DDA segment; "
          f"{len(need)} need one generated.\n")
    if need:
        print("NEED A DDA SEGMENT GENERATED (request via the audience form):")
        for n in need:
            print(f"  • {n['show']}")
    out = Path(args.out) if args.out else (Path(args.plan).with_suffix(".dda-needed.csv")
                                           if args.plan else Path("dda-needed.csv"))
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh); w.writerow(["show", "region"])
        for n in need:
            w.writerow([n["show"], region])
    print(f"\nWrote {out} ({len(need)} shows needing a segment)")
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

    p_mirror = sub.add_parser("mirror",
                              help="Mirror a plan to other markets (same title, swap country)")
    p_mirror.add_argument("plan")
    p_mirror.add_argument("--to", required=True, action="append", metavar="REGION",
                          help="Target region(s); repeat or comma-separate (e.g. --to GSA,IT)")
    p_mirror.add_argument("--out-dir", help="Where to write the mirrored plan files")
    p_mirror.set_defaults(func=_cmd_mirror)

    p_push = sub.add_parser("push", help="Push to an external system")
    p_push.add_argument("plan")
    p_push.add_argument("--target", required=True, choices=["freewheel", "gam"])
    p_push.add_argument("--live", action="store_true", help="Actually create (default dry-run)")
    p_push.set_defaults(func=_cmd_push)

    p_addon = sub.add_parser("addons", help="Build Video Domination + Takeover add-ons from a plan")
    p_addon.add_argument("plan")
    p_addon.add_argument("--live", action="store_true",
                         help="Push the Pluto VD placement to FreeWheel (default dry-run)")
    p_addon.set_defaults(func=_cmd_addons)

    p_cf = sub.add_parser("from-case-file",
                          help="Run the Case→order pipeline from a local Case JSON (no SF)")
    p_cf.add_argument("case_file")
    p_cf.add_argument("--targeting", help="Optional Targeting CSV to merge")
    p_cf.add_argument("--live", action="store_true", help="Create the FreeWheel draft")
    p_cf.set_defaults(func=_cmd_from_case_file)

    p_book = sub.add_parser("booking-sheet",
                            help="Print the Operative/GAM booking worksheet for a plan")
    p_book.add_argument("plan")
    p_book.set_defaults(func=_cmd_booking_sheet)

    p_gamck = sub.add_parser("gam-check", help="Preflight the GAM connection")
    p_gamck.set_defaults(func=_cmd_gam_check)

    p_sfck = sub.add_parser("salesforce-check",
                            help="Preflight: verify SF login + Case fields/picklists")
    p_sfck.set_defaults(func=_cmd_salesforce_check)

    p_doc = sub.add_parser("doctor",
                           help="Health check: data files + FreeWheel/MRM logins before a push")
    p_doc.set_defaults(func=_cmd_doctor)

    p_case = sub.add_parser("from-case", help="Validate+build+create from a Salesforce Case")
    p_case.add_argument("case_id")
    p_case.add_argument("--live", action="store_true", help="Create the draft (default dry-run)")
    p_case.set_defaults(func=_cmd_from_case)

    p_poll = sub.add_parser("poll-cases", help="Process Cases flagged Ready for Ad Ops")
    p_poll.add_argument("--live", action="store_true", help="Create drafts (default dry-run)")
    p_poll.add_argument("--watch", action="store_true", help="Loop on --interval instead of one-shot")
    p_poll.add_argument("--interval", type=float, default=300.0,
                        help="Seconds between cycles when --watch (default 300)")
    p_poll.add_argument("--max-cycles", type=int, default=None,
                        help="Stop after N cycles when --watch (default: run forever)")
    p_poll.add_argument("--log-file", help="Append a JSONL run-log record per cycle")
    p_poll.set_defaults(func=_cmd_poll_cases)

    p_pstat = sub.add_parser("poll-status", help="Summarize the poll run log")
    p_pstat.add_argument("--log-file", default="logs/poll-runs.jsonl")
    p_pstat.set_defaults(func=_cmd_poll_status)

    p_dig = sub.add_parser("daily-digest", help="Render a shareable daily digest from the run log")
    p_dig.add_argument("--log-file", default="logs/poll-runs.jsonl")
    p_dig.add_argument("--day", help="YYYY-MM-DD (default: today)")
    p_dig.add_argument("--all", action="store_true", help="All days, not just today")
    p_dig.set_defaults(func=_cmd_daily_digest)

    p_sheet = sub.add_parser("build-from-sheet", help="Build from a campaign-plan Google Sheet")
    p_sheet.add_argument("sheet_id")
    p_sheet.add_argument("--out")
    p_sheet.set_defaults(func=_cmd_build_from_sheet)

    p_sync = sub.add_parser("sync-segments", help="Refresh audience-segment CSVs from the sheet")
    p_sync.add_argument("--sheet-id")
    p_sync.set_defaults(func=_cmd_sync_segments)

    p_attr = sub.add_parser("sync-attributes", help="Refresh Standard Attribute CSVs from FreeWheel")
    p_attr.set_defaults(func=_cmd_sync_attributes)

    p_ai = sub.add_parser("sync-audience-items", help="Sync FreeWheel audience items (Tier 1 DDA)")
    p_ai.set_defaults(func=_cmd_sync_audience_items)

    p_sser = sub.add_parser("sync-series", help="Sync the full Video Series index from FreeWheel (~229k)")
    p_sser.set_defaults(func=_cmd_sync_series)

    p_sall = sub.add_parser("sync-all",
                            help="Refresh ALL FreeWheel data snapshots (series + audience + attributes)")
    p_sall.set_defaults(func=_cmd_sync_all)

    p_brief = sub.add_parser("from-brief",
                             help="Draft a plan from a promo brief (.docx/.txt) by resolving its affinities")
    p_brief.add_argument("brief", help="Path to the brief (.docx or .txt)")
    p_brief.add_argument("--region", default="USA", help="Target region (default USA)")
    p_brief.add_argument("--campaign", help="Destination campaign name")
    p_brief.add_argument("--durations", help="Comma-separated creative lengths, e.g. 15,30")
    p_brief.add_argument("--out", help="Where to write the draft plan.json")
    p_brief.set_defaults(func=_cmd_from_brief)

    p_srv = sub.add_parser("serve-suggest",
                           help="Run the local helper that powers the form's ✨ Suggest targeting button")
    p_srv.set_defaults(func=lambda a: __import__("promo_ops.suggest_server", fromlist=["main"]).main())

    p_sug = sub.add_parser("suggest",
                           help="Cold-start affinities from a title + description (AI and/or past plans)")
    p_sug.add_argument("title")
    p_sug.add_argument("--description", help="Show description / logline")
    p_sug.add_argument("--desc-file", help="Read the description from a file")
    p_sug.add_argument("--region", default="USA")
    p_sug.add_argument("--genres", help="Comma-separated genres (seeds the history engine)")
    p_sug.add_argument("--campaign", help="Destination campaign name")
    p_sug.add_argument("--durations", help="Comma-separated creative lengths, e.g. 15,30")
    p_sug.add_argument("--history", help="Folder of past *.plan.json to also learn from")
    p_sug.add_argument("--history-only", action="store_true", help="Skip the AI engine; use past plans only")
    p_sug.add_argument("--out", help="Where to write the draft plan.json")
    p_sug.set_defaults(func=_cmd_suggest)

    p_hist = sub.add_parser("sync-history",
                            help="Harvest past IOs into the affinity historicals corpus (per region)")
    p_hist.add_argument("--campaigns", help="';'-separated campaign names (default: CBS Network / P+ / Pluto TV - USA)")
    p_hist.add_argument("--all", action="store_true",
                        help="Harvest EVERY promo campaign across all regions (from brands.yaml)")
    p_hist.add_argument("--max-ios", type=int, default=40, help="Max IOs per campaign to harvest")
    p_hist.add_argument("--out", help="Corpus output path (default data/history/corpus.jsonl)")
    p_hist.set_defaults(func=_cmd_sync_history)

    p_dda = sub.add_parser("dda-requests",
                           help="List DDA segments to request for a plan's shows that lack one")
    p_dda.add_argument("plan", nargs="?", help="Plan .json (uses its showlist + region)")
    p_dda.add_argument("--shows", help="';'-separated show names (instead of a plan)")
    p_dda.add_argument("--region", default="USA")
    p_dda.add_argument("--out", help="CSV output path")
    p_dda.set_defaults(func=_cmd_dda_requests)

    p_refresh = sub.add_parser("refresh-form",
                               help="Weekly: sync every FreeWheel snapshot + rebuild the plan form")
    p_refresh.set_defaults(func=_cmd_refresh_form)

    p_batch = sub.add_parser("batch",
                             help="Build+create many cases from ONE sheet (one row per Salesforce case)")
    p_batch.add_argument("cases_csv", nargs="?",
                         help="CSV with one row per case (Salesforce Case column + plan fields)")
    p_batch.add_argument("--sheet", help="Google Sheet ID to read case rows from (live, instead of a CSV)")
    p_batch.add_argument("--tab", default="Cases",
                         help="Sheet tab with the case rows (default: Cases; falls back to the first tab)")
    p_batch.add_argument("--live", action="store_true", help="Create the drafts (default dry-run)")
    p_batch.add_argument("--out", help="Write the per-case results CSV here (Case # → IO link/status)")
    p_batch.set_defaults(func=_cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
