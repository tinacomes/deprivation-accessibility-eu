"""2SFCA supply-demand ratio and congestion-inflation factor."""

import numpy as np
import pandas as pd
import pytest

from depacc.deprivation.catchment import (
    congestion_factor,
    facility_weighted_demand,
    kernel_weight,
    supply_demand_ratio,
)

GAUSS = {"type": "gaussian", "bandwidth": 15.0}
BINARY = {"type": "binary", "bandwidth": 15.0}


def _uniform_setup(n_cells=6, n_fac=3, time=10.0):
    od = pd.DataFrame(
        [
            {"origin": i, "dest": f"f{j}", "time": time}
            for i in range(n_cells)
            for j in range(n_fac)
        ]
    )
    population = pd.Series(100.0, index=range(n_cells))
    supply = pd.Series(1.0, index=[f"f{j}" for j in range(n_fac)])
    return od, population, supply


def test_kernel_shapes():
    t = np.array([0.0, 15.0, 44.0, 46.0, np.nan])
    g = kernel_weight(t, GAUSS)
    assert g[0] == pytest.approx(1.0)
    assert 0 < g[1] < 1
    assert g[2] > 0 and g[3] == 0.0  # 3x bandwidth cutoff
    assert g[4] == 0.0  # NaN pair not in catchment
    b = kernel_weight(t, BINARY)
    assert b[0] == 1.0 and b[1] == 1.0 and b[2] == 0.0 and b[4] == 0.0


def test_uniform_supply_demand_gives_unit_factor():
    """With uniform supply and demand every facility's ratio is equal, so the
    congestion factor must be exactly 1 everywhere (gamma-independent)."""
    od, population, supply = _uniform_setup()
    ratio = supply_demand_ratio(od, population, supply, GAUSS)
    assert ratio.notna().all()
    assert np.allclose(ratio.to_numpy(), ratio.iloc[0])
    for gamma in (0.0, 0.5, 1.0):
        c = congestion_factor(ratio, gamma)
        assert np.allclose(c.to_numpy(), 1.0)


def test_crowded_facility_inflated_underused_deflated():
    od, population, supply = _uniform_setup(n_cells=4, n_fac=3)
    # Facility f0 serves a doubled population share.
    population.loc[0] = 1000.0
    od = od[~((od.origin == 0) & (od.dest != "f0"))]  # cell 0 only reaches f0
    ratio = supply_demand_ratio(od, population, supply, BINARY)
    assert ratio["f0"] < ratio["f1"]
    c = congestion_factor(ratio, gamma=0.5)
    assert c["f0"] > 1.0  # crowded -> time inflated
    assert c["f1"] <= 1.0  # relatively underused


def test_gamma_zero_disables_congestion():
    od, population, supply = _uniform_setup()
    population.iloc[0] = 1e6
    ratio = supply_demand_ratio(od, population, supply, GAUSS)
    c = congestion_factor(ratio, gamma=0.0)
    assert np.allclose(c.to_numpy(), 1.0)


def test_factor_clipping():
    ratio = pd.Series([1e-6, 1.0, 1e6], index=["a", "b", "c"])
    c = congestion_factor(ratio, gamma=1.0, factor_clip=(0.5, 4.0))
    assert c["a"] == 4.0
    assert c["c"] == 0.5


def test_unreached_facility_gets_nan_ratio_and_unit_factor():
    od, population, supply = _uniform_setup()
    supply.loc["f_far"] = 1.0  # exists but no OD rows reach it
    ratio = supply_demand_ratio(od, population, supply, GAUSS)
    assert np.isnan(ratio["f_far"])
    c = congestion_factor(ratio, gamma=0.5)
    assert c["f_far"] == 1.0


def test_weighted_demand_is_ratio_denominator():
    """facility_weighted_demand equals sum_i P_i K(t_ij) and reproduces the
    2SFCA ratio as supply / demand (the ratio's denominator)."""
    od, population, supply = _uniform_setup(n_cells=4, n_fac=3)
    population.loc[0] = 500.0
    demand = facility_weighted_demand(od, population, supply, BINARY)
    # Uniform reach at 10 min (<= bandwidth) -> every cell counts fully.
    expected = float(population.sum())  # each facility reached by all cells
    assert np.allclose(demand.to_numpy(), expected)
    ratio = supply_demand_ratio(od, population, supply, BINARY)
    assert np.allclose(ratio.to_numpy(), (supply / demand).to_numpy())


def test_reference_weights_shift_the_reference_median():
    """Weighting the reference median by facility demand moves it toward the
    high-demand facilities, changing the resulting congestion factors."""
    ratio = pd.Series([1.0, 2.0, 4.0], index=["a", "b", "c"])
    # Nearly all demand sits on the low-ratio (crowded) facility 'a'.
    weights = pd.Series([100.0, 1.0, 1.0], index=["a", "b", "c"])
    c_unw = congestion_factor(ratio, gamma=1.0)  # unweighted median ref = 2.0
    c_w = congestion_factor(ratio, gamma=1.0, reference_weights=weights)
    # Weighted reference is pulled down to ~1.0 (facility 'a'), so every factor
    # shrinks relative to the unweighted case.
    assert (c_w <= c_unw + 1e-9).all()
    assert c_w["a"] < c_unw["a"]  # 1.0 vs 2.0


def test_invalid_inputs():
    ratio = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        congestion_factor(ratio, gamma=-0.1)
    with pytest.raises(ValueError):
        congestion_factor(ratio, gamma=1.0, factor_clip=(2.0, 4.0))
    with pytest.raises(ValueError):
        kernel_weight(np.array([1.0]), {"type": "gaussian", "bandwidth": 0.0})
