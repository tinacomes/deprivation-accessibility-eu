"""Per-infrastructure accessibility indicator tables (deprivation-free)."""

import numpy as np
import pandas as pd
import pytest

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
    for col in ("pop_median_time_min", "pop_p90_time_min_reachable",
                "unreachable_pop_share"):
        assert col in per_service.columns
    # everyday services carry the 15-min threshold column; emergency the 30-min.
    assert "pop_share_beyond_15min" in per_service.columns
    assert "pop_share_beyond_30min" in per_service.columns
    assert set(per_regime.regime) == {"everyday", "emergency"}


def test_shares_are_fractions_and_ordering(tmp_path):
    per_service, _ = accessibility_indicators(_surfaces(), _cfg(), tmp_path)
    s = per_service.set_index("service")
    # p90 >= median for every service.
    assert (s["pop_p90_time_min_reachable"] >= s["pop_median_time_min"]).all()
    # threshold-beyond shares are valid fractions.
    for col in [c for c in s.columns if c.startswith("pop_share_beyond")]:
        vals = s[col].dropna()
        assert ((vals >= 0) & (vals <= 1)).all()


def test_reachable_quantiles_ignore_cap_and_report_unreachable_share(tmp_path):
    """Under cap_at_max_time, unreachable cells are pinned at the cutoff. The
    reachable-only p90 must ignore that cap, while unreachable_pop_share still
    accounts for the capped population and beyond-threshold counts it."""
    cfg = {
        "everyday_services": {"gp": {}},
        "emergency_services": {},
        "cityvector": {"access_thresholds_min": {"everyday": [30]}},
    }
    n = 100
    t = np.full(n, 10.0)          # reachable cells all at 10 min
    unreach = np.zeros(n, bool)
    t[:20] = 120.0                # 20 cells capped at the cutoff
    unreach[:20] = True
    surf = pd.DataFrame({
        "population": np.ones(n),
        "t_regime_gp": t,
        "unreachable_gp": unreach,
        "deprivation_gp": np.ones(n),
    })
    per_service, _ = accessibility_indicators(surf, cfg, tmp_path)
    row = per_service.set_index("service").loc["gp"]
    # Reachable p90 must be the reachable value (10), not the 120-min cap.
    assert row["pop_p90_time_min_reachable"] == 10.0
    assert row["pop_median_time_min"] == 10.0
    # 20/100 of the population is unreachable.
    assert row["unreachable_pop_share"] == pytest.approx(0.20)
    # Unreachable cells count as beyond the 30-min threshold.
    assert row["pop_share_beyond_30min"] == pytest.approx(0.20)
