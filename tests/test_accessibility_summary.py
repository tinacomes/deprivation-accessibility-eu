"""Per-infrastructure accessibility indicator tables (deprivation-free)."""

import numpy as np
import pandas as pd

from depacc.access.summary import accessibility_indicators


def _cfg():
    return {
        "everyday_services": {"gp": {}, "pharmacy": {}},
        "emergency_services": {"hospital": {}},
        "cityvector": {"access_thresholds_min": {"everyday": [15], "emergency": [30]}},
    }


def _surfaces():
    n = 100
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "t_regime_gp": rng.uniform(0, 40, n),
        "unreachable_gp": np.zeros(n, bool),
        "deprivation_gp": rng.uniform(0, 1, n),
        "t_regime_pharmacy": rng.uniform(0, 40, n),
        "unreachable_pharmacy": np.zeros(n, bool),
        "deprivation_pharmacy": rng.uniform(0, 1, n),
        "t_regime_hospital": rng.uniform(0, 60, n),
        "unreachable_hospital": np.zeros(n, bool),
        "deprivation_hospital": rng.uniform(0, 100, n),
        "t_regime_everyday": rng.uniform(0, 40, n),
        "unreachable_everyday": np.zeros(n, bool),
        "deprivation_everyday": rng.uniform(0, 1, n),
        "t_regime_emergency": rng.uniform(0, 60, n),
        "unreachable_emergency": np.zeros(n, bool),
        "deprivation_emergency": rng.uniform(0, 100, n),
    })
    return df


def test_per_service_table_shape_and_columns(tmp_path):
    per_service, per_regime = accessibility_indicators(_surfaces(), _cfg(), tmp_path)
    assert set(per_service.service) == {"gp", "pharmacy", "hospital"}
    for col in ("pop_median_time_min", "pop_p90_time_min", "unreachable_pop_share"):
        assert col in per_service.columns
    # everyday services carry the 15-min threshold column; emergency the 30-min.
    assert "pop_share_beyond_15min" in per_service.columns
    assert "pop_share_beyond_30min" in per_service.columns
    assert set(per_regime.regime) == {"everyday", "emergency"}


def test_shares_are_fractions_and_ordering(tmp_path):
    per_service, _ = accessibility_indicators(_surfaces(), _cfg(), tmp_path)
    s = per_service.set_index("service")
    # p90 >= median for every service.
    assert (s["pop_p90_time_min"] >= s["pop_median_time_min"]).all()
    # threshold-beyond shares are valid fractions.
    for col in [c for c in s.columns if c.startswith("pop_share_beyond")]:
        vals = s[col].dropna()
        assert ((vals >= 0) & (vals <= 1)).all()
