"""Video Dominations + Operative Takeovers — the GAM / Operative add-on layer.

These ride ON TOP of the tiered remnant/guaranteed order and are selected per campaign
via the plan's `video_domination` / `takeover` fields.

Two execution engines:
  * FreeWheel (Pluto VD): built directly as a guaranteed HIGHEST placement — a
    ready create-placement body, mirroring the live "… - Pluto Video Domination - …"
    IO (ad units House Pre/Mid, 1/day+1/stream+1/asset caps, a "Categories" set of the
    plan's Pluto category SGs). Push it with the FreeWheel client like any placement.
  * Operative (Standard / AU 10 Streaming / UK My5 VDs + HPTO/FITO/Arena/3-Peat
    takeovers): booked in Operative then pushed to GAM (advertiser "CBS Interactive").
    No API to drive that, so we emit a precise BOOKING SPEC — which Operative order to
    copy, the new name, the product lines, and the push rules — for the CM to execute
    (see docs/OPERATIVE_TAKEOVERS.md).

`build_addons(plan)` returns whatever the plan selected (either/both/neither).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .config import (ad_units_config, operative_takeovers_config, pluto_config,
                     regions_config, video_dominations_config)
from .models import SupportPlan


@dataclass
class VideoDominationSpec:
    option: str
    engine: str
    label: str
    # engine == "freewheel" (Pluto): a ready FreeWheel create-placement body.
    freewheel_placement: Optional[dict[str, Any]] = None
    unresolved_categories: list[str] = field(default_factory=list)
    # engine == "operative": the order to copy + how.
    operative_order_id: Optional[str] = None
    operative_order_name: Optional[str] = None
    note: Optional[str] = None


@dataclass
class TakeoverSpec:
    type: str
    label: str
    line_kind: str
    operative_order_name: str
    product_lines: list[str] = field(default_factory=list)
    booking_rules: dict[str, Any] = field(default_factory=dict)
    gam_push_advertiser: Optional[str] = None
    io_package_name: Optional[str] = None


class AddonBuilder:
    """Builds the VD / takeover specs, reusing an OrderBuilder for its resolvers."""

    def __init__(self, order_builder=None):
        if order_builder is None:
            from .order_builder import OrderBuilder
            order_builder = OrderBuilder()
        self.ob = order_builder
        self._vd = video_dominations_config()
        self._tk = operative_takeovers_config()

    # --- Video Domination ------------------------------------------------ #

    def build_video_domination(self, plan: SupportPlan) -> Optional[VideoDominationSpec]:
        if not plan.video_domination:
            return None
        opt = self._vd.get("options", {}).get(plan.video_domination)
        if not opt:
            return None
        if opt.get("engine") == "freewheel":
            return self._pluto_vd(plan, opt)
        return VideoDominationSpec(
            option=plan.video_domination, engine="operative", label=opt.get("label", ""),
            operative_order_id=opt.get("operative_order_id"),
            operative_order_name=opt.get("operative_order_name"), note=opt.get("note"))

    def _pluto_category_sgs(self, plan: SupportPlan) -> tuple[list[str], list[str]]:
        """Resolve the plan's Pluto VD categories -> SG IDs (region-aware). Returns
        (ids, unresolved_keywords)."""
        naming = pluto_config().get("naming", {})
        is_domestic = bool(regions_config().get("regions", {})
                           .get(plan.region, {}).get("domestic", False))
        pattern = naming["category_domestic"] if is_domestic else naming["category_international"]
        code = self.ob.engine._region_code(plan.region)
        prefix, _, suffix = pattern.format(region_code=code, name="\x00").partition("\x00")
        ids: list[str] = []
        unresolved: list[str] = []
        for kw in plan.video_domination_targeting:
            m = self.ob.engine.site_group_resolver.select_all(kw, prefix=prefix, suffix=suffix)
            if m.matched:
                ids.extend(sg["id"] for sg in m.site_groups)
            else:
                unresolved.append(kw)
        return sorted(set(ids)), unresolved

    def _pluto_vd(self, plan: SupportPlan, opt: dict) -> VideoDominationSpec:
        # Ad units (House Pre/Mid) + geo, resolved like a normal placement.
        group = opt.get("format") and None  # format template not required; use ad_units group
        au_names = list(ad_units_config().get("ad_units", {}).get("pluto_video_domination", []))
        au_ids = self.ob.ad_unit_resolver.ids_for(au_names)
        geo_names = self.ob._geo_country_names(plan.region)
        geo_ids = self.ob._geo_country_ids(geo_names)
        region_cfg = regions_config().get("regions", {}).get(plan.region, {})
        geo_region = region_cfg.get("geo_region")
        cat_ids, unresolved = self._pluto_category_sgs(plan)

        title = plan.promoted_title
        msg = plan.season_or_messaging
        name = " - ".join(x for x in [title, msg, "Pluto Video Domination", plan.region] if x)

        body: dict[str, Any] = {
            "name": name,
            "placement_type": "PROMO",
            "price": {"price_model": "ACTUAL_ECPM"},
            "budget": {"budget_model": "ALL_IMPRESSION"},
            "override": {"precedence_level": "HIGHEST"},
            "delivery": {
                "priority": "GUARANTEED", "pacing": "FAST_AS",
                "frequency_cap": list(self._vd.get("frequency_caps", [])),
            },
        }
        if geo_region:
            body["geography_targeting"] = {"include": {"region": [str(geo_region)]}}
        elif geo_ids:
            body["geography_targeting"] = {"include": {"country": geo_ids}}
        if au_ids:
            body["ad_product"] = {"link_method": "NOT_LINKED", "ad_unit_node": [
                {"ad_unit_id": a, "status": "ACTIVE", "price": "0.01", "budget_exempt": "false"}
                for a in au_ids]}
            body["_ad_unit_names"] = au_names
        # Targeting: a single "Categories" relationship set of the Pluto category SGs.
        if cat_ids:
            body["relationship_targeting"] = {"set": [{
                "set_name": "Categories",
                "content_targeting": {"network_items": {"include": {"site_group": cat_ids}}},
            }]}
        return VideoDominationSpec(
            option=plan.video_domination, engine="freewheel", label=opt.get("label", ""),
            freewheel_placement=body, unresolved_categories=unresolved)

    # --- Operative Takeovers --------------------------------------------- #

    def build_takeover(self, plan: SupportPlan) -> Optional[TakeoverSpec]:
        if not plan.takeover:
            return None
        t = self._tk.get("types", {}).get(plan.takeover)
        if not t:
            return None
        line_kind = t.get("line_kind", "sponsorship")
        rules = self._tk.get("booking_rules", {}).get(line_kind, {})
        return TakeoverSpec(
            type=plan.takeover, label=t.get("label", ""), line_kind=line_kind,
            operative_order_name=self._takeover_order_name(plan, t),
            product_lines=list(t.get("products", [])), booking_rules=rules,
            gam_push_advertiser=self._tk.get("gam_push_advertiser"),
            io_package_name=self._tk.get("io_package_name"))

    def _takeover_order_name(self, plan: SupportPlan, t: dict) -> str:
        naming = self._tk.get("naming", {})
        brand = self.ob._resolve_brand(plan) or ""
        dates = ""
        if plan.flight and plan.flight.start and plan.flight.end:
            dates = f"{plan.flight.start} - {plan.flight.end}"
        show = plan.promoted_title
        type_label = t.get("label", "")
        if str(brand).startswith("paramount_plus"):
            abbr = plan.takeover.upper().replace("_", " ")
            return naming.get("paramount_plus", "{show} - {type} {dates}").format(
                show=show, type=type_label, type_abbr=abbr, dates=dates).strip()
        return naming.get("default", "{show} - {type} {dates}").format(
            show=show, type=type_label, dates=dates).strip()


def build_addons(plan: SupportPlan, order_builder=None) -> dict[str, Any]:
    b = AddonBuilder(order_builder)
    return {"video_domination": b.build_video_domination(plan),
            "takeover": b.build_takeover(plan)}
