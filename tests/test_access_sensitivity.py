"""Layer-3 accessibility sensitivity (the cheap, from-cached-OD variants).

Covers variant expansion, the from-cache recomputation reproducing the pipeline
baseline exactly, the fact that these knobs DO move the rank-based targets
(unlike the rank-preserving Layers 1/2), flip-cells, the acceptance table, and
the CLI dispatch — all on the synthetic demo fixture (no network, no routing).
"""

import shutil

import numpy as np
import pandas as pd
import pytest

from depacc.config import load_config
from depacc.sensitivity.access import (
    _combined_od_subset,
    acceptance_table,
    available_od_modes,
    baseline_params,
    everyday_regime,
    expand_access_variants,
)

pytest.importorskip("pyarrow", reason="parquet engine required for cached inputs")

BASE_GRID = {
    "kappa": [0.1, 0.25, 0.5, 1.0, 2.0],
    "gamma": [0.0, 0.25, 0.5, 1.0],
    "bandwidth_min": [10, 15, 20],
    "k_nearest": [10, 30],
    "nearest_only": True,
    # Numbers are finite-fill minutes (the knob that sets the deprivation of
    # reachable-but-service-deprived cells); strings are unroutable-cell policies.
    "unreachable": [90, "exclude"],
    "everyday_modes": [["walk"], ["walk", "car"]],
}


# --------------------------------------------------------------------------- #
# Variant expansion (no cache needed)                                         #
# --------------------------------------------------------------------------- #
def test_expand_access_variants_one_knob_at_a_time():
    cfg = load_config("demo")
    variants = expand_access_variants(cfg, BASE_GRID)
    names = [v.name for v in variants]
    assert names[0] == "baseline"
    # Baseline no-ops (kappa 0.5, gamma 0.5, bw 15, k 30, walk) are skipped.
    assert "kappa_0.5" not in names and "gamma_0.5" not in names
    assert "bandwidth_15" not in names and "k_nearest_30" not in names
    assert "everyday_modes_walk" not in names
    # Off-baseline knobs are present.
    for expected in ("kappa_0.1", "gamma_0.0", "bandwidth_10", "k_nearest_10",
                     "nearest_only", "unreachable_exclude",
                     "everyday_modes_walk+car"):
        assert expected in names, expected
    # Each non-baseline variant changes exactly one axis from baseline.
    base = baseline_params(cfg)
    for v in variants[1:]:
        differing = [k for k in ("kappa", "gamma", "bandwidth", "k", "policy",
                                 "cap_min", "finite_fill", "modes",
                                 "nearest_only")
                     if v.params[k] != base[k]]
        assert len(differing) == 1, (v.name, differing)


def test_expand_access_variants_skips_unavailable_modes():
    cfg = load_config("demo")
    # Only walk is routed/saved -> the walk+car variant must be dropped.
    variants = expand_access_variants(cfg, BASE_GRID, available_modes={"walk"})
    assert all("car" not in v.name for v in variants)
    variants2 = expand_access_variants(cfg, BASE_GRID,
                                       available_modes={"walk", "car"})
    assert any(v.name == "everyday_modes_walk+car" for v in variants2)


def test_unreachable_axis_sweeps_the_finite_fill_not_the_policy():
    """The knob that matters after the reachability split. `policy` governs only
    genuinely-unroutable cells, of which a well-connected FUA has none — sweeping
    it produced two identical rows and a range of 0.0. The finite fill is what
    sets the deprivation of every reachable-but-service-deprived cell."""
    cfg = load_config("demo")
    variants = expand_access_variants(cfg, {**BASE_GRID, "unreachable": [90]})
    fill_var = [v for v in variants if v.knob == "unreachable"]
    assert len(fill_var) == 1
    assert fill_var[0].name == "unreachable_fill_90"
    assert fill_var[0].params["finite_fill"] == 90.0
    # ...and the cap/policy are untouched by it.
    base = baseline_params(cfg)
    assert fill_var[0].params["cap_min"] == base["cap_min"]
    assert fill_var[0].params["policy"] == base["policy"]
    # A string entry still expands to a policy variant.
    pol = [v for v in expand_access_variants(cfg, {**BASE_GRID,
                                                  "unreachable": ["exclude"]})
           if v.knob == "unreachable"]
    assert pol and pol[0].params["policy"] == "exclude"


# --------------------------------------------------------------------------- #
# From-cache recomputation on the demo fixture                                #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def demo_cache(tmp_path_factory):
    from depacc.cli import main

    root = tmp_path_factory.mktemp("access_sens_demo")
    for stage in ("ingest", "access", "deprivation", "divergence"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(root)]) == 0
    cfg = load_config("demo")
    yield cfg, root
    shutil.rmtree(root, ignore_errors=True)


def test_baseline_recompute_matches_pipeline(demo_cache):
    """The sweep must be anchored on the REAL baseline, not an approximation of
    it. Both the deprivation composite and the deprivation-free composite time
    reproduce the pipeline's saved columns to machine precision.

    The deprivation half is the one that regressed: the sweep used to composite
    travel times and apply g once, i.e. g(mean t_s) instead of the pipeline's
    mean of g(t_s). g is a logistic, so the Jensen gap put the sweep's "baseline"
    at gini_everyday 0.705 against Hamburg's actual 0.657 — every Layer-3 range
    was measured from a point the model never occupied.
    """
    cfg, root = demo_cache
    from depacc.ingest.pipeline import derived_dir

    out = derived_dir(cfg, "demo", root)
    cells = pd.read_parquet(out / "cells.parquet").set_index("cell_id")
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    dep, t, _zero = everyday_regime(cfg, out, cells, baseline_params(cfg))
    assert np.allclose(dep, surfaces["deprivation_everyday"].to_numpy(float),
                       equal_nan=True, atol=1e-9)
    assert np.allclose(t, surfaces["t_regime_everyday"].to_numpy(float),
                       equal_nan=True, atol=1e-9)


def test_k_subset_bounds_destinations(demo_cache):
    cfg, root = demo_cache
    from depacc.ingest.pipeline import derived_dir

    out = derived_dir(cfg, "demo", root)
    od10 = _combined_od_subset(out, "gp", ["walk"], k=10)
    assert od10.groupby("origin").size().max() <= 10
    od30 = _combined_od_subset(out, "gp", ["walk"], k=30)
    assert len(od30) >= len(od10)


def test_available_od_modes(demo_cache):
    cfg, root = demo_cache
    from depacc.ingest.pipeline import derived_dir

    out = derived_dir(cfg, "demo", root)
    services = list(cfg.get("everyday_services", {}))
    modes = available_od_modes(out, services)
    assert "walk" in modes  # demo routes walk + car for everyday services


def test_nearest_only_removes_substitutability_bonus(demo_cache):
    """κ → ∞ (nearest-only) is the hard minimum of the inflated times, so its
    effective time is never below the soft-min baseline (softmin ≤ min)."""
    cfg, root = demo_cache
    from depacc.ingest.pipeline import derived_dir

    out = derived_dir(cfg, "demo", root)
    cells = pd.read_parquet(out / "cells.parquet").set_index("cell_id")
    base = baseline_params(cfg)
    t_base = everyday_regime(cfg, out, cells, base)[1]
    t_near = everyday_regime(cfg, out, cells, {**base, "nearest_only": True})[1]
    m = np.isfinite(t_base) & np.isfinite(t_near)
    assert np.all(t_near[m] >= t_base[m] - 1e-9)
    assert np.nanmax(t_near - t_base) > 1e-6  # the bonus is non-trivial somewhere


# --------------------------------------------------------------------------- #
# Targets move (unlike Layers 1/2) + full driver                              #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def demo_sweep(demo_cache):
    from depacc.sensitivity.access import city_access_sensitivity

    cfg, root = demo_cache
    table = city_access_sensitivity(cfg, "demo", root, BASE_GRID, threshold=0.5)
    return cfg, root, table


def test_layer3_moves_hh_share_and_rho(demo_sweep):
    """The whole point of Layer 3: these accessibility knobs reorder cells, so
    the HH share and the coupling ρ genuinely move across variants (contrast the
    rank-invariant curvature layer, whose HH-share range is ~0)."""
    _, _, table = demo_sweep
    var = table[~table.axis.isin(["threshold"])]
    assert var["share_HH"].max() - var["share_HH"].min() > 1e-3
    assert var["spearman_rho"].max() - var["spearman_rho"].min() > 1e-3
    # Baseline row carries a zero self-flip; other variants report a flip share.
    base = table[table.variant == "baseline"].iloc[0]
    assert base["flip_pop_share"] == 0.0
    assert table[table.axis == "everyday_mode"]["flip_pop_share"].iloc[0] > 0


def test_driver_writes_csv_and_flip_map(demo_sweep):
    cfg, root, table = demo_sweep
    sens = root / cfg["output"]["root"] / "sensitivity"
    assert (sens / "demo_access_sensitivity.csv").exists()
    # Every expected knob axis appears, plus the threshold comparison axis.
    axes = set(table.axis)
    assert {"baseline", "kappa", "gamma", "bandwidth", "k_nearest",
            "nearest_only", "everyday_mode", "threshold"} <= axes
    # The flip-cell map is written when matplotlib is available.
    pytest.importorskip("matplotlib")
    assert (sens / "demo_access_flip_cells.png").exists()


def test_threshold_axis_is_rho_invariant(demo_sweep):
    """ρ is a coupling of the two surfaces and does not depend on the typology
    split, so the threshold block reports one constant ρ."""
    _, _, table = demo_sweep
    thr = table[table.axis == "threshold"]
    assert thr["spearman_rho"].nunique() == 1
    # ...but the HH share does move with the threshold (monotone down).
    assert thr.sort_values("threshold")["share_HH"].is_monotonic_decreasing


def test_acceptance_table(demo_sweep):
    _, _, table = demo_sweep
    acc = acceptance_table(table)
    assert (acc.knob == "threshold_axis").any()
    thr_row = acc[acc.knob == "threshold_axis"].iloc[0]
    assert thr_row["rho_range"] == 0.0  # ρ threshold-range is 0 by construction
    # ρ carries no "exceeds" verdict: the threshold axis cannot move ρ at all
    # (it acts after the percentile transform), so such a test passes for any
    # knob with a nonzero range and says nothing.
    assert "rho_exceeds_threshold" not in acc.columns
    assert {"n_variants", "n_degenerate"} <= set(acc.columns)
    assert (acc["n_degenerate"] <= acc["n_variants"]).all()


def test_degenerate_variants_are_flagged_and_excluded(demo_sweep):
    """A variant whose everyday surface collapses into one >50 % tie block is
    reported but must not set an acceptance range. On Hamburg both κ = 0.1 (the
    softmin bonus ln(30)/0.1 ≈ 34 min floors the core at t_eff = 0) and walk+car
    over the 1 km friction car surface land there, and between them they produced
    the run's headline "kappa moves the HH share most"."""
    _, _, table = demo_sweep
    var = table[~table.axis.isin(["threshold"])]
    assert {"degenerate", "max_tie_everyday", "zero_floor_pop_share"} <= set(table.columns)
    # The flag is exactly the >50 %-tie-block criterion.
    assert (var["degenerate"].astype(bool)
            == (var["max_tie_everyday"] > 0.5)).all()
    # A synthetic degenerate row must not widen any acceptance range.
    forged = table.copy()
    row = forged[forged.axis == "kappa"].index[0]
    forged.loc[row, ["share_HH", "max_tie_everyday", "degenerate"]] = [0.99, 0.97, True]
    assert (acceptance_table(forged).set_index("knob").loc["kappa", "hh_share_range"]
            == pytest.approx(acceptance_table(table).set_index("knob")
                             .loc["kappa", "hh_share_range"]))
    assert acceptance_table(forged).set_index("knob").loc["kappa", "n_degenerate"] >= 1


def test_cli_layer_access_dispatch(demo_cache):
    from depacc.cli import main

    cfg, root = demo_cache
    assert main(["sensitivity", "--layer", "access", "--city", "demo",
                 "--project-root", str(root)]) == 0
    sens = root / cfg["output"]["root"] / "sensitivity"
    assert (sens / "demo_access_acceptance.csv").exists()
