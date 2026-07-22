"""Deprivation-function-free travel-time Gini on the city row: computed over
reachable cells only, so the plane can be drawn without any DLF/DCF."""

import numpy as np
import pandas as pd

from depacc.divergence.cityplane import travel_time_ginis
from depacc.equity.indices import weighted_gini


def test_travel_time_ginis_reachable_only():
    n = 100
    t = np.full(n, 10.0)
    unreach = np.zeros(n, bool)
    # 20 unreachable cells capped at the cutoff (cap_at_max_time placeholder).
    t[:20] = 120.0
    unreach[:20] = True
    surf = pd.DataFrame({
        "population": np.ones(n),
        "t_regime_everyday": t,
        "unreachable_everyday": unreach,
        "t_regime_emergency": np.linspace(5, 25, n),
        "unreachable_emergency": np.zeros(n, bool),
    })
    out = travel_time_ginis(surf)
    # All reachable everyday times are equal -> Gini 0; the 120-min cap must not
    # leak in (which would push it above 0).
    assert out["gini_t_everyday"] == 0.0
    # Emergency matches a direct weighted Gini over all (reachable) cells.
    assert out["gini_t_emergency"] == weighted_gini(
        surf["t_regime_emergency"].to_numpy(float), surf["population"].to_numpy(float))


def test_travel_time_ginis_missing_columns_are_nan():
    surf = pd.DataFrame({"population": [1.0, 2.0]})
    out = travel_time_ginis(surf)
    assert np.isnan(out["gini_t_everyday"]) and np.isnan(out["gini_t_emergency"])
