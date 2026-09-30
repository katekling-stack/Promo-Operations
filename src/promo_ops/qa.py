"""Pre-launch QA auditor.

Fetch a LIVE Insertion Order (and its placements) from FreeWheel and check every placement
against the tool's own rules — the brand / region / format / tier invariants the builder would
have produced — flagging mistakes before the order is set live. It is rules-based: it needs
only the IO id (no original plan), because "correct" for a given brand/region/format/tier is
fully determined by config.

What it checks (per placement, unless noted):
  * ad units          — pre-roll present on short creatives and DROPPED at :30+; bumper/units
                        match the brand+format ad-unit group; never empty.
  * creative duration — the duration the placement is named for is a real number and (when the
                        payload exposes assigned-creative durations) a creative of that length
                        is attached.
  * time zone         — placement (and IO) schedule time zone matches the market (regions.yaml).
  * targeting         — main site groups match the brand (no Pluto 929392 in no-Pluto regions);
                        Samsung excluded for Pluto TV brands; Recommended Show only on the P+ /
                        Pluto TV campaigns; AU Tier 4 carries the UFC guarantee set.
  * frequency caps    — IO order-level cap matches the region rule; placement cap matches tier.
  * priority          — remnant override value / guaranteed precedence match the tier.
  * naming            — matches the "(Tier N)" + region convention.
  * geo               — country targeting present and matches the region.

Findings have a level: error (will mis-deliver / rejected), warn (likely wrong, verify), info
(couldn't determine from the payload — check by hand), ok (verified). The report ranks
error-first. Read-payload field access is defensive: an unreadable field yields an INFO finding,
never a false error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import brands_config, regions_config
from .order_builder import OrderBuilder
from .integrations.freewheel import FreeWheelClient

LEVELS = ("error", "warn", "info", "ok")
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
_ICON = {"error": "❌", "warn": "⚠️", "info": "ℹ️", "ok": "✅"}

# Region codes, longest-first so "Paramount + - En Espanol - USA" still resolves to USA and the
# multi-token markets match before their substrings.
_REGION_CODES = ["LATAM", "USA", "GSA", "UK", "IE", "AU", "BR", "FR", "IT", "FI", "DK",
                 "NO", "SE", "ES", "CA"]
PLUTO_SG = "929392"


@dataclass
class Finding:
    level: str            # error / warn / info / ok
    category: str         # ad_units / creative_duration / timezone / targeting / freq_cap / ...
    placement: str        # placement name, or "(order)" for IO-level
    message: str
    expected: Any = None
    actual: Any = None

    def line(self) -> str:
        extra = ""
        if self.expected is not None or self.actual is not None:
            extra = f"  (expected {self.expected!r}, got {self.actual!r})"
        return f"{_ICON.get(self.level, '?')} [{self.category}] {self.message}{extra}"


@dataclass
class QAReport:
    io_id: str
    io_name: str = ""
    brand: Optional[str] = None
    region: Optional[str] = None
    findings: list[Finding] = field(default_factory=list)
    placement_count: int = 0
    error: Optional[str] = None      # set when the IO itself couldn't be audited

    def by_level(self, level: str) -> list[Finding]:
        return [f for f in self.findings if f.level == level]

    def ok(self) -> bool:
        return not self.error and not self.by_level("error")

    def text(self) -> str:
        """Human-readable terminal report, grouped by placement, error-first."""
        out: list[str] = []
        head = f"QA — IO {self.io_id}"
        if self.io_name:
            head += f"  “{self.io_name}”"
        out.append(head)
        bits = []
        if self.brand:
            bits.append(f"brand={self.brand}")
        if self.region:
            bits.append(f"region={self.region}")
        bits.append(f"{self.placement_count} placement(s)")
        out.append("  " + " · ".join(bits))
        if self.error:
            out.append(f"\n❌ {self.error}")
            return "\n".join(out)
        n_err, n_warn = len(self.by_level("error")), len(self.by_level("warn"))
        out.append(f"  {n_err} error(s), {n_warn} warning(s)\n")
        # group by placement, preserving first-seen order, placements with errors first
        groups: dict[str, list[Finding]] = {}
        for f in self.findings:
            groups.setdefault(f.placement, []).append(f)

        def worst(fs: list[Finding]) -> int:
            return min((_LEVEL_RANK[f.level] for f in fs), default=len(LEVELS))
        for name in sorted(groups, key=lambda n: (worst(groups[n]), n)):
            fs = sorted(groups[name], key=lambda f: _LEVEL_RANK[f.level])
            # hide all-ok placements unless they are the only thing to show
            shown = [f for f in fs if f.level != "ok"] or fs
            out.append(f"• {name}")
            for f in shown:
                out.append(f"    {f.line()}")
        return "\n".join(out)

    def markdown(self) -> str:
        lines = [f"# QA report — IO {self.io_id}"]
        if self.io_name:
            lines.append(f"**{self.io_name}**")
        meta = [x for x in (f"Brand: `{self.brand}`" if self.brand else None,
                            f"Region: `{self.region}`" if self.region else None,
                            f"Placements: {self.placement_count}") if x]
        lines.append(" · ".join(meta))
        if self.error:
            lines.append(f"\n> ❌ {self.error}")
            return "\n".join(lines)
        lines.append(f"\n**{len(self.by_level('error'))} error(s), "
                     f"{len(self.by_level('warn'))} warning(s)**\n")
        lines.append("| Level | Placement | Check | Detail |")
        lines.append("|---|---|---|---|")
        order = sorted(self.findings, key=lambda f: (_LEVEL_RANK[f.level], f.placement))
        for f in order:
            if f.level == "ok":
                continue
            detail = f.message
            if f.expected is not None or f.actual is not None:
                detail += f" (expected `{f.expected}`, got `{f.actual}`)"
            detail = detail.replace("|", "\\|")
            lines.append(f"| {_ICON[f.level]} {f.level} | {f.placement} | {f.category} | "
                         f"{detail} |")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  A tolerant reader over a live placement / IO body (mirrors the write shape)
# --------------------------------------------------------------------------- #
class PlacementView:
    """Defensive accessors over a raw FreeWheel placement dict. Unknown/missing fields return
    None or [] rather than raising, so a check can emit INFO ("couldn't read X") not a crash."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.raw.get("placement_name") or "").strip()

    @property
    def guaranteed(self) -> bool:
        return str((self.raw.get("delivery") or {}).get("priority", "")).upper() == "GUARANTEED"

    def frequency_cap_strs(self) -> Optional[list[str]]:
        """['1 per 15 min', ...] from delivery.frequency_cap, or None if absent/unreadable."""
        fc = (self.raw.get("delivery") or {}).get("frequency_cap")
        if fc is None:
            return None
        items = fc if isinstance(fc, list) else [fc]
        out: list[str] = []
        for it in items:
            if not isinstance(it, dict):
                return None
            val = it.get("value")
            per = it.get("period")
            if val is None or per is None:
                return None
            out.append(_human_cap(str(val), str(per)))
        return out

    def override_value(self) -> Optional[int]:
        ov = self.raw.get("override") or {}
        v = ov.get("value")
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def precedence_level(self) -> Optional[str]:
        return (self.raw.get("override") or {}).get("precedence_level")

    def ad_unit_ids(self) -> Optional[list[str]]:
        ap = self.raw.get("ad_product") or {}
        nodes = ap.get("ad_unit_node")
        if nodes is None:
            return None
        return [str(n.get("ad_unit_id")) for n in nodes if isinstance(n, dict) and n.get("ad_unit_id")]

    def schedule_timezone(self) -> Optional[str]:
        return (self.raw.get("schedule") or {}).get("time_zone")

    def sets(self) -> list[dict[str, Any]]:
        rt = self.raw.get("relationship_targeting") or {}
        s = rt.get("set")
        return [x for x in s if isinstance(x, dict)] if isinstance(s, list) else []

    def all_site_groups(self, which: str) -> set[str]:
        """Every site_group id under include/exclude ('include'|'exclude') across all sets and
        the placement-level content_targeting (set-less flat lines)."""
        return self._collect("site_group", which)

    def all_video_groups(self, which: str) -> set[str]:
        return self._collect("video_group", which)

    def _collect(self, key: str, which: str) -> set[str]:
        found: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == key and isinstance(v, list):
                        found.update(str(x) for x in v)
                    else:
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        # relationship set include/exclude
        for s in self.sets():
            ni = (s.get("content_targeting") or {}).get("network_items") or {}
            walk(ni.get(which))
        # placement-level content_targeting (set-less flat lines)
        ni = (self.raw.get("content_targeting") or {}).get("network_items") or {}
        walk(ni.get(which))
        return found

    def set_names(self) -> list[str]:
        return [str(s.get("set_name")) for s in self.sets() if s.get("set_name")]

    def geo_country_ids(self) -> Optional[list[str]]:
        # The builder writes geography_targeting.include.{country|region}; tolerate a couple of
        # shapes so a differently-expanded read payload still resolves.
        roots = [self.raw.get("geography_targeting"),
                 (self.raw.get("content_targeting") or {}).get("geo_targeting"),
                 self.raw.get("geo_targeting")]
        for root in roots:
            if not isinstance(root, dict):
                continue
            inc = root.get("include") or {}
            for key in ("country", "region"):
                node = inc.get(key)
                if isinstance(node, list) and node:
                    return [str(x) for x in node]
        return None

    def frequency_cap_keys(self) -> Optional[set[tuple[str, str]]]:
        """{(value, minutes)} from delivery.frequency_cap — normalized for comparison; None if
        absent/unreadable."""
        fc = (self.raw.get("delivery") or {}).get("frequency_cap")
        if fc is None:
            return None
        items = fc if isinstance(fc, list) else [fc]
        out: set[tuple[str, str]] = set()
        for it in items:
            if not isinstance(it, dict) or it.get("value") is None or it.get("period") is None:
                return None
            out.add((str(it["value"]), str(it["period"])))
        return out

    def creative_durations(self) -> Optional[list[int]]:
        """Best-effort assigned-creative durations (seconds). Read shape varies by expand flags;
        try the common keys. None -> not present in this payload (audit by hand)."""
        out: list[int] = []
        for key in ("creatives", "creative", "ad_product"):
            node = self.raw.get(key)
            for d in _find_durations(node):
                out.append(d)
        return sorted(set(out)) or None


def _find_durations(node: Any) -> list[int]:
    found: list[int] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("duration", "creative_duration", "length") and isinstance(v, (int, float, str)):
                try:
                    found.append(int(float(v)))
                except (TypeError, ValueError):
                    pass
            else:
                found.extend(_find_durations(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_find_durations(v))
    return found


def _human_cap(value: str, period_minutes: str) -> str:
    """Inverse of the builder's encoding: value + minutes -> '1 per 30 min' / '20 per month'."""
    try:
        m = int(period_minutes)
    except (TypeError, ValueError):
        return f"{value} per {period_minutes}"
    if m == 43200:
        return f"{value} per month"
    if m == 1440:
        return f"{value} per day"
    if m == 60:
        return f"{value} per hr"
    return f"{value} per {m} min"


# --------------------------------------------------------------------------- #
#  The auditor
# --------------------------------------------------------------------------- #
class QAAuditor:
    def __init__(self, client: Optional[FreeWheelClient] = None,
                 order_builder: Optional[OrderBuilder] = None):
        self.client = client or FreeWheelClient()
        self.ob = order_builder or OrderBuilder()
        self.brands = brands_config().get("brands", {})
        self.regions = regions_config().get("regions", {})

    # -- public ----------------------------------------------------------- #
    def audit_io(self, io_id: str) -> QAReport:
        report = QAReport(io_id=str(io_id))
        try:
            io = _unwrap(self.client.get_insertion_order(io_id), "insertion_order")
        except Exception as exc:  # noqa: BLE001
            report.error = f"couldn't fetch IO {io_id}: {exc}"
            return report
        report.io_name = str(io.get("name") or "")
        brand_key = self._brand_from_io(io)
        report.brand = brand_key
        region = self._region_for(brand_key, io)
        report.region = region
        try:
            placements = self.client.list_placements(io_id)
        except Exception as exc:  # noqa: BLE001
            report.error = f"couldn't list placements for IO {io_id}: {exc}"
            return report
        report.placement_count = len(placements)
        if brand_key is None:
            report.findings.append(Finding(
                "warn", "brand", "(order)",
                "couldn't map this IO to a known brand — brand-specific checks skipped "
                "(add the campaign's template_campaign_id to config/brands.yaml)."))
        report.findings += self._check_io(io, brand_key, region)
        for raw in placements:
            report.findings += self._check_placement(PlacementView(raw), brand_key, region)
        return report

    # -- resolution ------------------------------------------------------- #
    def _brand_from_io(self, io: dict[str, Any]) -> Optional[str]:
        cid = str(io.get("campaign_id") or (io.get("campaign") or {}).get("id") or "").strip()
        if cid:
            for key, cfg in self.brands.items():
                if str(cfg.get("template_campaign_id") or "") == cid:
                    return key
        # fall back to a campaign-name match if the IO carries one
        cname = str((io.get("campaign") or {}).get("name") or io.get("campaign_name") or "").strip().lower()
        if cname:
            for key, cfg in self.brands.items():
                if str(cfg.get("campaign_name") or "").strip().lower() == cname:
                    return key
        return None

    def _region_for(self, brand_key: Optional[str], io: dict[str, Any]) -> Optional[str]:
        cfg = self.brands.get(brand_key or "", {})
        cname = str(cfg.get("campaign_name") or (io.get("campaign") or {}).get("name")
                    or io.get("name") or "")
        for code in _REGION_CODES:
            if re.search(rf"(?:^|[-\s]){re.escape(code)}$", cname):
                return code
        return None

    def _brand_cfg(self, brand_key: Optional[str]) -> dict[str, Any]:
        return self.brands.get(brand_key or "", {})

    def _region_has_pluto(self, region: Optional[str]) -> bool:
        return bool(self.regions.get(region or "", {}).get("has_pluto", True))

    def _is_kids(self, brand_key: Optional[str]) -> bool:
        return bool(self._brand_cfg(brand_key).get("kids"))

    # -- IO-level checks -------------------------------------------------- #
    def _check_io(self, io: dict[str, Any], brand_key, region) -> list[Finding]:
        out: list[Finding] = []
        # Order-level frequency cap
        if region:
            expected = OrderBuilder._order_frequency_caps(region, self._is_kids(brand_key))
            exp_key = {(FreeWheelClient._fc_value(e), FreeWheelClient._fc_period_minutes(e))
                       for e in expected}
            actual = _io_freq_cap_keys(io)
            if actual is None:
                out.append(Finding("info", "freq_cap", "(order)",
                                   "couldn't read the order-level frequency cap from the IO — "
                                   f"expected {expected}."))
            elif actual != exp_key:
                out.append(Finding("error", "freq_cap", "(order)",
                                   "order-level frequency cap doesn't match the region rule.",
                                   _keys_human(exp_key), _keys_human(actual)))
            else:
                out.append(Finding("ok", "freq_cap", "(order)",
                                   f"order-level frequency cap {_keys_human(actual)} matches "
                                   "the region rule."))
            # IO schedule time zone (informational; placement tz is authoritative)
            tz = (io.get("schedule") or {}).get("time_zone")
            exp_tz = FreeWheelClient._region_timezone(region)
            if tz and exp_tz and tz != exp_tz:
                out.append(Finding("warn", "timezone", "(order)",
                                   "IO schedule time zone doesn't match the market.", exp_tz, tz))
        return out

    # -- placement-level checks ------------------------------------------ #
    def _check_placement(self, pv: PlacementView, brand_key, region) -> list[Finding]:
        name = pv.name or "(unnamed placement)"
        out: list[Finding] = []
        cfg = self._brand_cfg(brand_key)
        tier = _parse_tier(name)
        duration = _parse_duration(name)
        fmt = self._infer_format(pv, cfg, tier)

        out += self._check_naming(pv, name, region, tier)
        out += self._check_timezone(pv, name, region)
        out += self._check_ad_units(pv, name, cfg, fmt, duration)
        out += self._check_creative_duration(pv, name, duration)
        out += self._check_freq_cap(pv, name, fmt, tier, cfg)
        out += self._check_priority(pv, name, tier, duration, cfg)
        out += self._check_targeting(pv, name, brand_key, cfg, region, tier)
        out += self._check_geo(pv, name, region)
        return out

    def _check_naming(self, pv, name, region, tier) -> list[Finding]:
        if region and not re.search(rf"(?:-|\s){re.escape(region)}\b", name):
            return [Finding("warn", "naming", name,
                            f"name doesn't end with the region '- {region}'.")]
        return [Finding("ok", "naming", name, "name matches the convention.")]

    def _check_timezone(self, pv, name, region) -> list[Finding]:
        if not region:
            return []
        tz = pv.schedule_timezone()
        exp = FreeWheelClient._region_timezone(region)
        if tz is None:
            return [Finding("info", "timezone", name,
                            f"no placement schedule time zone found — expected {exp!r}.")]
        if exp and tz != exp:
            return [Finding("error", "timezone", name,
                            "placement time zone doesn't match the market.", exp, tz)]
        return [Finding("ok", "timezone", name, f"time zone {tz} matches the market.")]

    def _check_ad_units(self, pv, name, cfg, fmt, duration) -> list[Finding]:
        out: list[Finding] = []
        actual = pv.ad_unit_ids()
        if actual is None:
            return [Finding("info", "ad_units", name, "no ad units found on the placement.")]
        if not actual:
            return [Finding("error", "ad_units", name, "placement has NO ad units attached.")]
        if not (cfg and fmt):
            return [Finding("info", "ad_units", name,
                            "couldn't determine the expected ad-unit group (brand/format "
                            "unknown) — verify ad units by hand.")]
        try:
            exp_names, exp_ids = self.ob._ad_units_for_duration(
                cfg, fmt, self._tmpl(fmt, cfg), duration)
        except Exception:  # noqa: BLE001
            return [Finding("info", "ad_units", name, "couldn't compute expected ad units.")]
        exp_set, act_set = set(exp_ids), set(actual)
        if exp_set and exp_set != act_set:
            missing = exp_set - act_set
            extra = act_set - exp_set
            msg = "ad units don't match the brand+format group."
            detail_exp = sorted(exp_set)
            detail_act = sorted(act_set)
            out.append(Finding("warn", "ad_units", name, msg, detail_exp, detail_act))
            if missing:
                out.append(Finding("warn", "ad_units", name,
                                   f"missing expected ad unit id(s): {sorted(missing)}"))
            if extra:
                out.append(Finding("warn", "ad_units", name,
                                   f"unexpected ad unit id(s): {sorted(extra)}"))
        else:
            out.append(Finding("ok", "ad_units", name, "ad units match the brand+format group."))
        return out

    def _check_creative_duration(self, pv, name, duration) -> list[Finding]:
        if duration is None:
            return []   # non-duration line (bumper token, sponsorship) — nothing to match
        durs = pv.creative_durations()
        if durs is None:
            return [Finding("info", "creative_duration", name,
                            f"named for :{duration} — couldn't read assigned-creative durations "
                            "from the payload; confirm a :%d creative is attached." % duration)]
        if duration not in durs:
            return [Finding("error", "creative_duration", name,
                            f"named for :{duration} but no matching creative length is attached.",
                            duration, durs)]
        return [Finding("ok", "creative_duration", name,
                        f":{duration} creative attached as named.")]

    def _check_freq_cap(self, pv, name, fmt, tier, cfg) -> list[Finding]:
        actual = pv.frequency_cap_keys()
        if actual is None:
            return [Finding("info", "freq_cap", name,
                            "no placement frequency cap found — verify by hand.")]
        if not fmt:
            return [Finding("info", "freq_cap", name,
                            "placement cap present; couldn't compute the expected tier cap.")]
        # Guaranteed lines use the template's own cap (else the format default); remnant uses
        # the tier cap. Normalize both sides to (value, minutes) so "2 hrs" == "120 min".
        try:
            if pv.guaranteed:
                exp_str = self._tmpl(fmt, cfg).get("frequency_cap") or self.ob._freq_cap(None, fmt)
            else:
                exp_str = self.ob._freq_cap(tier, fmt)
        except Exception:  # noqa: BLE001
            return [Finding("info", "freq_cap", name, "couldn't compute the expected cap.")]
        if not exp_str:
            return [Finding("info", "freq_cap", name, "no expected cap to compare.")]
        exp_key = {(FreeWheelClient._fc_value(exp_str),
                    FreeWheelClient._fc_period_minutes(exp_str))}
        if actual != exp_key:
            return [Finding("warn", "freq_cap", name,
                            "placement frequency cap doesn't match the tier/format rule.",
                            _keys_human(exp_key), _keys_human(actual))]
        return [Finding("ok", "freq_cap", name, f"frequency cap {_keys_human(actual)} matches.")]

    def _check_priority(self, pv, name, tier, duration, cfg) -> list[Finding]:
        if pv.guaranteed:
            prec = pv.precedence_level()
            if prec is None:
                return [Finding("info", "priority", name,
                                "guaranteed line has no precedence level — verify by hand.")]
            return [Finding("ok", "priority", name, f"guaranteed precedence {prec}.")]
        if tier is None:
            return []
        val = pv.override_value()
        if val is None:
            return [Finding("info", "priority", name,
                            "no remnant priority (override.value) found — verify by hand.")]
        pluto = bool(cfg.get("pluto_brand")) and bool(cfg.get("hot_tier4", True))
        try:
            exp = self.ob._priority(tier, duration, pluto=pluto)
        except Exception:  # noqa: BLE001
            return []
        if -val != exp:
            return [Finding("warn", "priority", name,
                            f"Tier {tier} priority doesn't match the expected value.",
                            -exp, val)]
        return [Finding("ok", "priority", name, f"Tier {tier} priority {val} matches.")]

    def _check_targeting(self, pv, name, brand_key, cfg, region, tier) -> list[Finding]:
        out: list[Finding] = []
        inc_sgs = pv.all_site_groups("include")
        # no-Pluto regions must never target the Pluto platform SG
        if region and not self._region_has_pluto(region) and PLUTO_SG in inc_sgs:
            out.append(Finding("error", "targeting", name,
                               f"targets the Pluto SG {PLUTO_SG} in a no-Pluto region ({region})."))
        # brand main site groups should appear somewhere in the includes (skip flat/no-set lines)
        expected_main = self._expected_main_sgs(cfg, region)
        if expected_main and pv.sets():
            if not (set(expected_main) & inc_sgs):
                out.append(Finding("warn", "targeting", name,
                                   "none of the brand's main site groups are targeted.",
                                   sorted(expected_main), sorted(inc_sgs)))
        # Samsung exclude for the real Pluto TV brands
        if self._is_pluto_tv_brand(cfg, region):
            samsung = self._samsung_sgs(region)
            exc = pv.all_site_groups("exclude")
            if samsung and not (set(samsung) & exc):
                out.append(Finding("warn", "targeting", name,
                                   "Pluto TV brand placement is missing the Samsung TV Plus "
                                   "exclude.", sorted(samsung), sorted(exc)))
        # Recommended Show must appear ONLY on the P+ / Pluto TV campaigns
        has_rec = "Recommended Show" in pv.set_names()
        allowed_rec = self._is_pplus_brand(brand_key) or self._is_pluto_tv_brand(cfg, region)
        if has_rec and not allowed_rec:
            out.append(Finding("error", "targeting", name,
                               "carries a Recommended Show set but this campaign isn't a "
                               "Paramount+ / Pluto TV campaign."))
        # AU-style Tier 4 guarantee sets (e.g. UFC) must be present on P+ Tier 4 lines
        extras = cfg.get("tier4_extra_sets") or []
        if extras and tier == 4 and self._serves_pplus_line(pv):
            present = set(pv.set_names())
            for sd in extras:
                sn = sd.get("set_name")
                if sn and sn not in present:
                    out.append(Finding("error", "targeting", name,
                                       f"Tier 4 is missing the required '{sn}' guarantee set."))
        if not out:
            out.append(Finding("ok", "targeting", name, "targeting matches the brand rules."))
        return out

    def _check_geo(self, pv, name, region) -> list[Finding]:
        if not region:
            return []
        ids = pv.geo_country_ids()
        if ids is None:
            return [Finding("info", "geo", name, "couldn't read geo targeting — verify by hand.")]
        if not ids:
            return [Finding("warn", "geo", name, "no country geo targeting found.")]
        return [Finding("ok", "geo", name, f"geo targets country id(s) {ids}.")]

    # -- expected-value helpers ------------------------------------------ #
    def _tmpl(self, fmt: Optional[str], cfg: Optional[dict] = None) -> dict[str, Any]:
        base = (self.ob._templates.get("formats", {}) or {}).get(fmt or "", {})
        overrides = ((cfg or {}).get("format_overrides", {}) or {}).get(fmt or "", {})
        return {**base, **overrides} if overrides else dict(base)

    def _expected_main_sgs(self, cfg, region) -> list[str]:
        main = list(cfg.get("main_site_groups", []) or [])
        if region and not self._region_has_pluto(region):
            main = [sg for sg in main if sg != PLUTO_SG]
        return main

    def _is_pluto_tv_brand(self, cfg, region) -> bool:
        return (bool(cfg.get("pluto_brand"))
                and str(cfg.get("campaign_name", "")).startswith("Pluto TV"))

    def _is_pplus_brand(self, brand_key: Optional[str]) -> bool:
        cfg = self._brand_cfg(brand_key)
        return str(cfg.get("campaign_name", "")).startswith("Paramount +") \
            or str(brand_key or "").startswith("paramount_plus")

    def _serves_pplus_line(self, pv: PlacementView) -> bool:
        # The UFC-style sets target P+ inventory; they ride only P+ lines, not Network 10 / My5.
        n = pv.name
        return not any(tag in n for tag in ("(My5)", "(10 Streaming)", "Network 10"))

    def _samsung_sgs(self, region) -> list[str]:
        from .config import relationship_targeting_config
        s = relationship_targeting_config().get("samsung_tv_plus", {})
        return list(s.get("domestic" if region == "USA" else "international", []))

    def _infer_format(self, pv: PlacementView, cfg, tier) -> Optional[str]:
        """Best-effort map a live placement to one of the brand's formats, by name markers and
        guaranteed/remnant shape. Used to look up the expected ad-unit group + caps."""
        name = pv.name
        all_formats = list(cfg.get("formats", []) or []) + list(cfg.get("optional_formats", []) or [])
        if pv.guaranteed:
            low = name.lower()
            if "pre-roll" in low or "preroll" in low:
                for f in all_formats:
                    if "preroll" in f or "pre_roll" in f:
                        return f
            if "bumper" in low:
                for f in all_formats:
                    if "bumper" in f:
                        return f
            return next((f for f in all_formats if self._tmpl(f).get("guaranteed")), None)
        # remnant — disambiguate the UK/AU/kids variants by the name infix
        if "(Pluto)" in name:
            return next((f for f in all_formats if f.endswith("remnant_pluto")), None) \
                or "pplus_uk_remnant_pluto"
        if "(My5)" in name:
            return "my5_remnant" if "my5_remnant" in all_formats else None
        if "(10 Streaming)" in name or "Network 10" in name:
            return next((f for f in all_formats if "network_10" in f), None)
        # the brand's primary remnant format (first non-guaranteed, non-variant)
        for f in all_formats:
            t = self._tmpl(f)
            if not t.get("guaranteed") and t.get("format_code") == "RVID":
                return f
        return all_formats[0] if all_formats else None


# --------------------------------------------------------------------------- #
#  small helpers
# --------------------------------------------------------------------------- #
def _unwrap(payload: Any, singular: str) -> dict[str, Any]:
    """Pull the object out of a V3 {data:{<singular>:{...}}} envelope (or return as-is)."""
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        obj = data.get(singular)
        if isinstance(obj, dict):
            return obj
        # some payloads nest one level deeper: data.<singular>.<singular>
        if isinstance(obj, dict) is False and isinstance(data.get(singular, None), dict):
            return data[singular]
        if singular not in data and len(data) == 1:
            only = next(iter(data.values()))
            if isinstance(only, dict):
                return only
    return payload.get(singular) if isinstance(payload.get(singular), dict) else payload


def _io_freq_cap_keys(io: dict[str, Any]) -> Optional[set[tuple[str, str]]]:
    fc = (io.get("delivery") or {}).get("frequency_cap")
    if fc is None:
        return None
    items = fc if isinstance(fc, list) else [fc]
    out: set[tuple[str, str]] = set()
    for it in items:
        if not isinstance(it, dict) or it.get("value") is None or it.get("period") is None:
            return None
        out.add((str(it["value"]), str(it["period"])))
    return out


def _keys_human(keys: set[tuple[str, str]]) -> list[str]:
    """Render a set of (value, minutes) caps as sorted human strings for the report."""
    return sorted(_human_cap(v, m) for v, m in keys)


def _parse_tier(name: str) -> Optional[int]:
    m = re.search(r"\(Tier\s+(\d)\)", name or "")
    return int(m.group(1)) if m else None


def _parse_duration(name: str) -> Optional[int]:
    """The creative length a placement is named for. The duration sits right before a tier/infix
    parenthesis, e.g. '… - 30 (Tier 1) - AU' or '… 15 (P+/Pluto)'. Match the number before such a
    paren (NOT a number in the title like 'UFC 300'). None for bumper/sponsorship lines."""
    for m in re.finditer(r"(\d{1,3})\s*\(([^)]*)\)", name or ""):
        if re.search(r"Tier|Pluto|My5|10|P\+|Net|Streaming", m.group(2), re.I):
            v = int(m.group(1))
            if 5 <= v <= 240:
                return v
    # fallback: an isolated duration token between dashes ("… - 30 - Region")
    m = re.search(r"(?:^|-\s)(\d{1,3})\s*-", name or "")
    if m:
        v = int(m.group(1))
        if 5 <= v <= 240:
            return v
    return None
