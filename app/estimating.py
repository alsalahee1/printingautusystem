"""Offset-printing estimation engine.

Pure functions with no database or web dependencies, so the costing logic can
be unit-tested in isolation and reused by both the quotation screens and the
live `/api/estimate` preview.

The model follows how an offset job is actually costed:

  1. Imposition  — how many finished pieces fit on one parent (press) sheet,
     trying both orientations and allowing for bleed and a gripper margin.
  2. Sheets      — net sheets to make the quantity, plus spoilage (wastage %).
  3. Plates      — one CTP plate per colour, per side.
  4. Make-ready  — fixed setup charge per press run (one run per printed side).
  5. Press time  — running impressions / press speed + make-ready minutes,
     costed at the machine's hourly rate.
  6. Paper / ink — sheets x sheet cost; ink by colour-impressions.
  7. Finishing   — each operation priced per piece / sheet / job / m2.
  8. Margin      — overhead %, then markup %, giving the selling price.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class FinishingSpec:
    name: str
    pricing_method: str          # per_piece | per_sheet | per_job | per_sqm
    unit_rate: float = 0.0
    setup_cost: float = 0.0


@dataclass
class EstimateInput:
    quantity: int = 0
    finished_width_mm: float = 0.0
    finished_height_mm: float = 0.0
    parent_width_mm: float = 0.0
    parent_height_mm: float = 0.0
    paper_cost_per_sheet: float = 0.0
    colors_front: int = 0
    colors_back: int = 0
    run_rate_per_hour: int = 0
    hourly_rate: float = 0.0
    makeready_cost: float = 0.0
    makeready_minutes: int = 0
    plate_cost: float = 0.0
    ink_cost_per_1000: float = 0.0
    wastage_pct: float = 0.0
    setup_spoilage_sheets: int = 0
    markup_pct: float = 0.0
    overhead_pct: float = 0.0
    bleed_mm: float = 0.0         # extra margin around each piece
    gripper_mm: float = 0.0       # non-printable gripper edge on the parent sheet
    finishings: list[FinishingSpec] = field(default_factory=list)


@dataclass
class FinishingLine:
    name: str
    method: str
    amount: float


@dataclass
class EstimateResult:
    ups: int = 0
    net_sheets: int = 0
    spoilage_sheets: int = 0
    total_sheets: int = 0
    num_runs: int = 0
    impressions: int = 0
    num_plates: int = 0

    paper_cost: float = 0.0
    ink_cost: float = 0.0
    plate_cost: float = 0.0
    makeready_cost: float = 0.0
    press_cost: float = 0.0
    finishing_cost: float = 0.0
    finishing_lines: list[FinishingLine] = field(default_factory=list)

    material_cost: float = 0.0
    production_cost: float = 0.0
    base_cost: float = 0.0
    overhead_amount: float = 0.0
    cost_subtotal: float = 0.0
    markup_amount: float = 0.0
    selling_price: float = 0.0
    unit_price: float = 0.0

    warnings: list[str] = field(default_factory=list)


def compute_ups(parent_w: float, parent_h: float, piece_w: float, piece_h: float) -> int:
    """Pieces per parent sheet, picking the better of the two orientations."""
    if piece_w <= 0 or piece_h <= 0 or parent_w <= 0 or parent_h <= 0:
        return 0
    portrait = math.floor(parent_w / piece_w) * math.floor(parent_h / piece_h)
    landscape = math.floor(parent_w / piece_h) * math.floor(parent_h / piece_w)
    return max(portrait, landscape)


def _round(value: float) -> float:
    return round(value + 1e-9, 2)


def estimate(inp: EstimateInput) -> EstimateResult:
    r = EstimateResult()

    piece_w = inp.finished_width_mm + 2 * inp.bleed_mm
    piece_h = inp.finished_height_mm + 2 * inp.bleed_mm
    usable_h = max(inp.parent_height_mm - inp.gripper_mm, 0)

    r.ups = compute_ups(inp.parent_width_mm, usable_h, piece_w, piece_h)

    if inp.quantity <= 0:
        r.warnings.append("Quantity is zero.")
        return r
    if r.ups <= 0:
        r.warnings.append("Finished piece does not fit on the selected sheet — check sizes.")
        return r

    # 2. Sheets needed.
    r.net_sheets = math.ceil(inp.quantity / r.ups)
    r.spoilage_sheets = math.ceil(r.net_sheets * inp.wastage_pct / 100) + inp.setup_spoilage_sheets
    r.total_sheets = r.net_sheets + r.spoilage_sheets

    # 3 & 4. Runs, plates, make-ready (one run per printed side).
    r.num_runs = 1 + (1 if inp.colors_back > 0 else 0)
    r.num_plates = inp.colors_front + inp.colors_back
    r.impressions = r.total_sheets * r.num_runs
    r.makeready_cost = _round(inp.makeready_cost * r.num_runs)
    r.plate_cost = _round(r.num_plates * inp.plate_cost)

    # 5. Press time cost.
    run_hours = (r.impressions / inp.run_rate_per_hour) if inp.run_rate_per_hour > 0 else 0
    makeready_hours = (inp.makeready_minutes / 60) * r.num_runs
    r.press_cost = _round((run_hours + makeready_hours) * inp.hourly_rate)
    if inp.run_rate_per_hour <= 0 and inp.hourly_rate > 0:
        r.warnings.append("Machine run rate is zero — press running time not costed.")

    # 6. Paper & ink.
    r.paper_cost = _round(r.total_sheets * inp.paper_cost_per_sheet)
    color_impressions = r.total_sheets * (inp.colors_front + inp.colors_back)
    r.ink_cost = _round(color_impressions / 1000 * inp.ink_cost_per_1000)

    # 7. Finishing.
    parent_area_m2 = (inp.parent_width_mm * inp.parent_height_mm) / 1_000_000
    for f in inp.finishings:
        if f.pricing_method == "per_piece":
            base = inp.quantity * f.unit_rate
        elif f.pricing_method == "per_sheet":
            base = r.net_sheets * f.unit_rate
        elif f.pricing_method == "per_sqm":
            base = parent_area_m2 * r.net_sheets * f.unit_rate
        else:  # per_job
            base = 0.0
        amount = _round(base + f.setup_cost)
        r.finishing_lines.append(FinishingLine(f.name, f.pricing_method, amount))
        r.finishing_cost += amount
    r.finishing_cost = _round(r.finishing_cost)

    # 8. Totals & margin.
    r.material_cost = _round(r.paper_cost + r.ink_cost + r.plate_cost)
    r.production_cost = _round(r.makeready_cost + r.press_cost + r.finishing_cost)
    r.base_cost = _round(r.material_cost + r.production_cost)
    r.overhead_amount = _round(r.base_cost * inp.overhead_pct / 100)
    r.cost_subtotal = _round(r.base_cost + r.overhead_amount)
    r.markup_amount = _round(r.cost_subtotal * inp.markup_pct / 100)
    r.selling_price = _round(r.cost_subtotal + r.markup_amount)
    r.unit_price = _round(r.selling_price / inp.quantity) if inp.quantity else 0.0
    return r
