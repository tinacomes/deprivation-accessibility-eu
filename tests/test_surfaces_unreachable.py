"""Everyday + emergency surfaces: end-to-end on synthetic data, and
unreachable-cell handling under both policies."""

import numpy as np
import pandas as pd
import pytest

from depacc.deprivation.functions import DeprivationFunction
from depacc.deprivation.surfaces import emergency_surface, everyday_surface

DLF = DeprivationFunction(form="exponential", params={"beta": 0.05, "scale": 1.0})
DCF = DeprivationFunction(form="box_cox", params={"lam": 1.5, "scale": 2.0, "shift": 1.0})
KERNEL = {"type": "gaussian", "bandwidth": 15.0}


def _setup():
    # Cells: 0 near everything, 1 mid, 2 far, 3 unreachable (no OD rows).
    cells = pd.DataFrame({"population": [100.0, 50.0, 10.0, 5.0]}, index=[0, 1, 2, 3])
    od = pd.DataFrame(
        [
            {"origin": 0, "dest": "a", "time": 5.0},
            {"origin": 0, "dest": "b", "time": 7.0},
            {"origin": 1, "dest": "a", "time": 20.0},
            {"origin": 1, "dest": "b", "time": 25.0},
            {"origin": 2, "dest": "b", "time": 60.0},
        ]
    )
    supply = pd.Series(1.0, index=["a", "b"])
    return cells, od, supply


def test_emergency_uses_nearest_only():
    cells, od, _ = _setup()
    surf = emergency_surface(od, cells, DCF, policy="exclude")
    assert surf.loc[0, "t_nearest"] == 5.0
    assert surf.loc[1, "t_nearest"] == 20.0
    assert surf.loc[0, "deprivation"] == pytest.approx(DCF(5.0))
    # Convexity bites: doubling nearest time more than doubles deprivation.
    assert surf.loc[2, "deprivation"] > 2 * surf.loc[1, "deprivation"]


def test_everyday_effective_time_and_baseline():
    cells, od, supply = _setup()
    surf = everyday_surface(
        od, cells, supply, DLF, kappa=0.5, kernel=KERNEL, gamma=0.0,
        policy="exclude",
    )
    # gamma=0: no congestion, so t_eff is the pure softmin <= nearest time.
    assert surf.loc[0, "t_eff"] <= surf.loc[0, "t_nearest"]
    # Substitutability bonus: cell 0 has two close options.
    assert surf.loc[0, "t_eff"] < 5.0
    # Baseline column always the plain nearest time.
    assert surf.loc[1, "t_nearest"] == 20.0
    assert surf.loc[0, "deprivation"] == pytest.approx(float(DLF(surf.loc[0, "t_eff"])))


def test_congestion_raises_deprivation_at_crowded_facilities():
    # Two isolated neighbourhoods, both within catchment of their facility:
    # cell 0 only reaches "a", cell 1 only reaches "b", equal times.
    cells = pd.DataFrame({"population": [100.0, 10000.0]}, index=[0, 1])
    od = pd.DataFrame(
        [
            {"origin": 0, "dest": "a", "time": 10.0},
            {"origin": 1, "dest": "b", "time": 10.0},
        ]
    )
    supply = pd.Series(1.0, index=["a", "b"])
    base = everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                            gamma=0.0, policy="exclude")
    cong = everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                            gamma=1.0, factor_clip=(0.5, 4.0), policy="exclude")
    # Without congestion the two cells are identical...
    assert base.loc[0, "deprivation"] == pytest.approx(base.loc[1, "deprivation"])
    # ...with congestion, the 100x-crowded facility "b" inflates cell 1's
    # effective time and deprivation, while uncrowded "a" deflates cell 0's.
    assert cong.loc[1, "t_eff"] > base.loc[1, "t_eff"]
    assert cong.loc[1, "deprivation"] > base.loc[1, "deprivation"]
    assert cong.loc[1, "deprivation"] > cong.loc[0, "deprivation"]
    # The plain nearest-time baseline is untouched by congestion.
    assert cong.loc[1, "t_nearest"] == 10.0


def test_unreachable_flagged_and_excluded():
    cells, od, supply = _setup()
    for surf in (
        emergency_surface(od, cells, DCF, policy="exclude"),
        everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                         gamma=0.5, policy="exclude"),
    ):
        assert bool(surf.loc[3, "unreachable"]) is True
        assert not surf.loc[[0, 1, 2], "unreachable"].any()
        assert np.isnan(surf.loc[3, "deprivation"])
        # Reachable cells must never be NaN-poisoned by unreachable ones.
        assert surf.loc[[0, 1, 2], "deprivation"].notna().all()


def test_unreachable_capped_at_max_time():
    cells, od, supply = _setup()
    surf = emergency_surface(od, cells, DCF, policy="cap_at_max_time", max_time_min=120.0)
    assert bool(surf.loc[3, "unreachable"]) is True
    assert surf.loc[3, "t_nearest"] == 120.0
    assert surf.loc[3, "deprivation"] == pytest.approx(float(DCF(120.0)))
    # Capped deprivation dominates every genuinely reachable cell here.
    assert surf.loc[3, "deprivation"] > surf.loc[[0, 1, 2], "deprivation"].max()


def test_effective_time_floored_at_zero():
    """Many facilities seconds away must not drive t_eff (softmin) negative."""
    cells = pd.DataFrame({"population": [10.0]}, index=[0])
    od = pd.DataFrame(
        [{"origin": 0, "dest": f"f{j}", "time": 0.2} for j in range(30)]
    )
    supply = pd.Series(1.0, index=[f"f{j}" for j in range(30)])
    surf = everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                            gamma=0.0, policy="exclude")
    assert surf.loc[0, "t_eff"] == 0.0
    assert surf.loc[0, "deprivation"] == pytest.approx(0.0)


def test_unknown_policy_rejected():
    cells, od, supply = _setup()
    with pytest.raises(ValueError):
        emergency_surface(od, cells, DCF, policy="pretend_fine")


# -- Phase 1: the two meanings of "unreachable" (shared routability mask) ------

def test_reachable_but_service_deprived_stays_on_map():
    """A routable cell with no facility of THIS service in reach is badly
    deprived, NOT unreachable: finite-filled to high deprivation, kept on map."""
    cells, od, supply = _setup()
    # Cell 3 has no OD row for this service but IS routable (reaches something
    # else in the city).
    routable = pd.Series(True, index=cells.index)
    em = emergency_surface(od, cells, DCF, policy="exclude",
                           routable=routable, finite_fill_min=120.0)
    ev = everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                          gamma=0.5, policy="exclude",
                          routable=routable, finite_fill_min=120.0)
    for surf, fn, col in ((em, DCF, "t_nearest"), (ev, DLF, "t_eff")):
        assert bool(surf.loc[3, "unreachable"]) is False          # not masked
        assert surf.loc[3, col] == 120.0                          # finite fill
        assert surf.loc[3, "deprivation"] == pytest.approx(float(fn(120.0)))
        assert surf.loc[[0, 1, 2], "deprivation"].notna().all()


def test_no_network_path_is_masked():
    """A genuinely unroutable cell (~routable) is the only masked case."""
    cells, od, supply = _setup()
    routable = pd.Series([True, True, True, False], index=cells.index)
    for surf in (
        emergency_surface(od, cells, DCF, policy="exclude",
                          routable=routable, finite_fill_min=120.0),
        everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                         gamma=0.5, policy="exclude",
                         routable=routable, finite_fill_min=120.0),
    ):
        assert bool(surf.loc[3, "unreachable"]) is True
        assert np.isnan(surf.loc[3, "deprivation"])
        assert not surf.loc[[0, 1, 2], "unreachable"].any()


def test_shared_routable_gives_equal_unreachable_sets():
    """Same routability mask -> identical unreachable sets across the two
    regimes (the Phase 1 cross-regime invariant, at the surface level)."""
    cells, od, supply = _setup()
    routable = pd.Series([True, True, False, False], index=cells.index)
    em = emergency_surface(od, cells, DCF, policy="exclude",
                           routable=routable, finite_fill_min=120.0)
    ev = everyday_surface(od, cells, supply, DLF, kappa=0.5, kernel=KERNEL,
                          gamma=0.5, policy="exclude",
                          routable=routable, finite_fill_min=120.0)
    assert (em["unreachable"].to_numpy() == ev["unreachable"].to_numpy()).all()
    assert (em["unreachable"].to_numpy() == (~routable).to_numpy()).all()
