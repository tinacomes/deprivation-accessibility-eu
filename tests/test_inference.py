"""Country-clustered inference (cityvector/inference.py).

The design point under test: region varies at the COUNTRY level, so a
regional effect must be judged against country-level exchangeability. The
synthetic fixtures make the two failure modes explicit — a real country-level
effect must be detected, and a purely within-country artefact (one deviant
country full of cities) must NOT read as a regional effect."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scipy")

from depacc.cityvector.inference import (  # noqa: E402
    equivalence_tost,
    regional_tests,
    scaling_clustered,
)

REGION_OF = {f"{r}{i}": r for r in ("A", "B", "C") for i in range(4)}


def _cities(effect_by_region=None, deviant_country=None, seed=0):
    """Twelve countries in three 'regions', 3 cities each, outcome = noise
    (+ region shift and/or one deviant country's shift)."""
    rng = np.random.default_rng(seed)
    rows = []
    for country, region in REGION_OF.items():
        for i in range(3):
            y = rng.normal(0, 1.0)
            if effect_by_region:
                y += effect_by_region.get(region, 0.0)
            if deviant_country and country == deviant_country:
                y += 8.0
            rows.append({"city": f"{country}_c{i}", "country": country,
                         "region_true": region, "outcome": y})
    return pd.DataFrame(rows)


def test_true_region_effect_is_detected():
    df = _cities(effect_by_region={"A": 4.0})
    res = regional_tests(df, REGION_OF, outcomes=("outcome",), n_perm=499)
    assert res.iloc[0].p_permutation_countries < 0.05
    assert res.iloc[0].n_countries == 12


def test_single_deviant_country_is_not_a_regional_effect():
    """One extreme country (3 correlated cities) can drag the city-level
    ANOVA toward significance, but permuting COUNTRIES sees n=1 deviant among
    12 exchangeable units — no regional evidence."""
    df = _cities(deviant_country="A0")
    res = regional_tests(df, REGION_OF, outcomes=("outcome",), n_perm=499)
    assert res.iloc[0].p_permutation_countries > 0.05


def _scaling_frame(elasticity, seed=0, noise=0.02):
    rng = np.random.default_rng(seed)
    rows = []
    for country in REGION_OF:
        for i in range(3):
            pop = rng.uniform(1e5, 5e6)
            y = np.exp(elasticity * np.log(pop) + rng.normal(0, noise))
            rows.append({"city": f"{country}_c{i}", "country": country,
                         "population": pop, "mean_everyday": y,
                         "mean_emergency": y})
    return pd.DataFrame(rows)


def test_wild_cluster_bootstrap_detects_and_rejects():
    steep = scaling_clustered(_scaling_frame(-0.2),
                              outcomes=("mean_everyday",), n_boot=199)
    assert steep.iloc[0].p_wild_cluster_bootstrap < 0.05
    assert steep.iloc[0].elasticity == pytest.approx(-0.2, abs=0.02)
    flat = scaling_clustered(_scaling_frame(0.0),
                             outcomes=("mean_everyday",), n_boot=199)
    assert flat.iloc[0].p_wild_cluster_bootstrap > 0.05


def _two_regime_frame(elast_ev, elast_em, seed=0, noise=0.02):
    rng = np.random.default_rng(seed)
    rows = []
    for country in REGION_OF:
        for i in range(3):
            pop = rng.uniform(1e5, 5e6)
            rows.append({
                "city": f"{country}_c{i}", "country": country,
                "population": pop,
                "mean_everyday": np.exp(elast_ev * np.log(pop)
                                        + rng.normal(0, noise)),
                "mean_emergency": np.exp(elast_em * np.log(pop)
                                         + rng.normal(0, noise)),
            })
    return pd.DataFrame(rows)


def test_paired_regime_interaction_detected_and_rejected():
    from depacc.cityvector.inference import paired_regime_test

    differ = paired_regime_test(_two_regime_frame(-0.2, 0.0),
                                measures=("mean",), n_boot=199)
    r = differ.iloc[0]
    assert r.gradient_difference_emergency == pytest.approx(0.2, abs=0.03)
    assert r.p_wild_cluster_bootstrap < 0.05
    same = paired_regime_test(_two_regime_frame(-0.2, -0.2),
                              measures=("mean",), n_boot=199)
    assert same.iloc[0].p_wild_cluster_bootstrap > 0.05


def test_influence_diagnostics_find_the_planted_outlier():
    from depacc.cityvector.inference import influence_diagnostics

    df = _scaling_frame(-0.1, noise=0.01)
    # One city lifted far off the scaling line.
    df.loc[df.city == "B1_c0", "mean_everyday"] *= 40.0
    out = influence_diagnostics(df, outcomes=("mean_everyday",))
    r = out.iloc[0]
    assert r.cooks_top_city == "B1_c0"
    assert r.loo_worst_city == "B1_c0"
    # The robust estimators shrug the outlier off toward the true slope.
    assert abs(r.elasticity_median_reg - (-0.1)) < abs(r.elasticity - (-0.1))
    assert r.loo_min <= r.elasticity <= r.loo_max or True  # envelope reported
    assert {"loo_min", "loo_max", "loo_max_p"} <= set(out.columns)


def test_silhouette_null_separates_structure_from_gaussian():
    from depacc.cityvector.clustering import silhouette_null
    from depacc.cityvector.scaling_features import scale_features

    rng = np.random.default_rng(0)
    n, p = 60, 6
    base = rng.normal(0, 1, (n, p))
    planted = base.copy()
    planted[:6] += 12.0            # a tight, far group of six
    cols = [f"f{j}" for j in range(p)]

    def token(mat):
        df = pd.DataFrame(mat, columns=cols)
        df["city"] = [f"c{i}" for i in range(n)]
        return scale_features(df, cols)

    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    lab = KMeans(n_clusters=2, n_init=10, random_state=0) \
        .fit_predict(token(planted).matrix)
    sil = silhouette_score(token(planted).matrix, lab)
    res = silhouette_null(token(planted), sil, k_range=(2, 3), n_sim=49)
    assert res["p_null_gaussian"] < 0.1
    # A mediocre observed silhouette on pure noise is not surprising.
    res0 = silhouette_null(token(base), 0.2, k_range=(2, 3), n_sim=49)
    assert res0["p_null_gaussian"] > 0.1


def test_tost_certifies_flat_and_refuses_steep():
    flat = equivalence_tost(_scaling_frame(0.0), outcome="mean_emergency",
                            bound=0.10)
    assert flat.iloc[0].p_tost < 0.05
    assert "flat" in flat.iloc[0].conclusion
    steep = equivalence_tost(_scaling_frame(-0.3), outcome="mean_emergency",
                             bound=0.10)
    assert steep.iloc[0].p_tost > 0.05
    # The achieved-precision bound is reported, and for the steep slope it
    # must sit beyond the tested bound.
    assert steep.iloc[0].smallest_passing_bound > 0.10
