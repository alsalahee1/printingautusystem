"""Unit tests for the pure costing engine."""
from app.estimating import EstimateInput, FinishingSpec, compute_ups, estimate


def test_compute_ups_picks_best_orientation():
    # A4 (210x297) on a 686x1016 parent sheet -> 9-up (3x3 portrait beats landscape).
    assert compute_ups(686, 1016, 210, 297) == 9
    # Degenerate inputs are safe.
    assert compute_ups(0, 0, 210, 297) == 0
    assert compute_ups(686, 1016, 0, 0) == 0


def test_oversize_piece_warns_and_zero_ups():
    r = estimate(EstimateInput(quantity=100, finished_width_mm=2000,
                               finished_height_mm=2000, parent_width_mm=686,
                               parent_height_mm=1016))
    assert r.ups == 0
    assert any("does not fit" in w for w in r.warnings)


def test_full_estimate_costs_and_margin():
    r = estimate(EstimateInput(
        quantity=5000, finished_width_mm=210, finished_height_mm=297,
        parent_width_mm=686, parent_height_mm=1016, paper_cost_per_sheet=0.34,
        colors_front=4, colors_back=4, run_rate_per_hour=12000, hourly_rate=180,
        makeready_cost=120, makeready_minutes=30, plate_cost=12,
        ink_cost_per_1000=4.0, wastage_pct=8, markup_pct=30, overhead_pct=15,
        finishings=[FinishingSpec("Lamination Gloss", "per_sqm", 1.20, 15)],
    ))
    assert r.ups == 9
    assert r.net_sheets == 556                 # ceil(5000/9)
    assert r.num_plates == 8                    # 4 front + 4 back
    assert r.num_runs == 2                      # double-sided
    assert r.total_sheets == r.net_sheets + r.spoilage_sheets
    # Selling price = cost + overhead + markup, and exceeds bare cost.
    assert r.selling_price > r.base_cost > 0
    assert r.unit_price == round(r.selling_price / 5000, 2)


def test_single_sided_one_run():
    r = estimate(EstimateInput(
        quantity=1000, finished_width_mm=100, finished_height_mm=100,
        parent_width_mm=686, parent_height_mm=1016, colors_front=4, colors_back=0,
        run_rate_per_hour=10000, hourly_rate=100, plate_cost=12))
    assert r.num_runs == 1
    assert r.num_plates == 4
