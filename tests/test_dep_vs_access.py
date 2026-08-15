"""Deprivation-vs-access contrast: grade rule, desert table, grade scaling."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scipy")

from depacc.cityvector.dep_vs_access import (  # noqa: E402
    _size_stratum,
    access_indicators,
    city_descriptives,
    coverage_grades,
    desert_contrast,
    scaling_by_grade,
    size_elasticity_contrast,
)


def _vectors(n=24, seed=3):
    rng = np.random.default_rng(seed)
    pop = 10 ** rng.uniform(5.0, 6.8, n)
    df = pd.DataFrame({
        "city": [f"c{i}" for i in range(n)],
        "name": [f"City {i}" for i in range(n)],
        "country": [["DE", "FR", "NL", "PL", "SE", "IT"][i % 6]
                    for i in range(n)],
        "population": pop,
        "mean_everyday": 0.4 * (pop / 1e5) ** -0.2,
        "mean_emergency": 0.15 + rng.uniform(0, 0.01, n),
        "gini_everyday": rng.uniform(0.3, 0.6, n),
        "gini_emergency": rng.uniform(0.3, 0.6, n),
        # cluster 1 is the small (outlier) group -> "desert"
        "cluster_kmeans": [1 if i < 3 else 0 for i in range(n)],
    })
    # The deserts sit at a different LEVEL; every grade is size-flat with the
    # same multiplicative noise, so only the level separates the grades.
    df["mean_emergency"] = np.where(df.index < 3, 0.6, 0.15) \
        * np.exp(rng.normal(0, 0.12, n))
    df["gini_t_everyday"] = df["gini_everyday"] * 0.9 + 0.02
    df["gini_t_emergency"] = df["gini_emergency"] * 0.9 + 0.02
    return df


def _peeled(vectors, partial=("c3", "c4", "c5")):
    peeled = vectors[vectors.cluster_kmeans == 0].copy()
    peeled["cluster_kmeans"] = peeled.city.isin(partial).astype(int)
    return peeled


def test_coverage_grades_are_the_two_clustering_passes():
    v = _vectors()
    grade = coverage_grades(v, _peeled(v))
    assert set(grade[v.city.isin(["c0", "c1", "c2"])]) == {"desert"}
    assert set(grade[v.city.isin(["c3", "c4", "c5"])]) == {"partial desert"}
    assert (grade == "covered").sum() == len(v) - 6
    # No peeled pass: everything that is not the flagged group is covered.
    assert (coverage_grades(v, None) == "partial desert").sum() == 0


def test_access_indicators_read_the_per_city_regime_table(tmp_path):
    for city, med in (("a", 5.0), ("b", 9.0)):
        (tmp_path / city).mkdir()
        pd.DataFrame([
            {"level": "everyday", "regime": "everyday",
             "pop_mean_time_min": med + 1, "pop_median_time_min": med,
             "pop_p90_time_min_reachable": med * 3},
            {"level": "emergency", "regime": "emergency",
             "pop_mean_time_min": med + 2, "pop_median_time_min": med + 1,
             "pop_p90_time_min_reachable": med * 4},
        ]).to_csv(tmp_path / city / "accessibility_by_regime.csv", index=False)
    out = access_indicators(tmp_path, ["a", "b", "missing"])
    assert list(out.city) == ["a", "b"]
    assert out.loc[out.city == "b", "emergency_median_time"].iloc[0] == 10.0
    assert out.loc[out.city == "a", "everyday_p90_time"].iloc[0] == 15.0


def test_size_elasticity_contrast_pairs_deprivation_with_minutes():
    v = _vectors()
    v["everyday_median_time"] = 12 * (v.population / 1e5) ** -0.25
    v["everyday_mean_time"] = v.everyday_median_time * 1.3
    v["emergency_median_time"] = 10.0
    v["emergency_mean_time"] = 11.0
    v["emergency_p90_time"] = 20.0
    out = size_elasticity_contrast(v)
    ev = out[(out.block == "size_elasticity") & (out.regime == "everyday")]
    assert set(ev.kind) == {"deprivation", "access"}
    dep = ev[ev.kind == "deprivation"].elasticity.iloc[0]
    acc = ev[ev.outcome == "everyday_median_time"].elasticity.iloc[0]
    assert dep == pytest.approx(-0.2, abs=0.01)
    assert acc == pytest.approx(-0.25, abs=0.01)
    # Constant emergency minutes carry no gradient and no variance to explain.
    assert (out[out.outcome == "emergency_median_time"].elasticity.iloc[0]
            == pytest.approx(0.0, abs=1e-9))
    gini = out[out.block == "gini_correlation"]
    assert len(gini) == 2 and (gini.elasticity > 0.99).all()


def test_desert_contrast_is_the_flagged_group_against_the_sample():
    v = _vectors()
    v["emergency_median_time"] = 10.0
    v["emergency_p90_time"] = 20.0
    v.loc[v.index < 3, "emergency_median_time"] = 11.0
    v["coverage_grade"] = coverage_grades(v, _peeled(v)).values
    out = desert_contrast(v)
    assert list(out.city) == ["c0", "c1", "c2"]
    # The point of the table: an ordinary-looking access ratio next to a
    # large deprivation ratio.
    assert out.median_time_ratio_vs_sample.iloc[0] == pytest.approx(1.1)
    assert out.deprivation_ratio_vs_sample.iloc[0] > 3.0


def test_scaling_by_grade_reports_level_and_slope_tests():
    v = _vectors()
    v["coverage_grade"] = coverage_grades(v, _peeled(v)).values
    out = scaling_by_grade(v)
    assert list(out.grade[:3]) == list(("covered", "partial desert", "desert"))
    assert out.n_cities.iloc[0] == len(v) - 6
    level = out[out.grade.str.startswith("grade level")]
    inter = out[out.grade.str.startswith("interaction")]
    # Levels are set by grade (deserts at 0.6 vs 0.15), slopes are not:
    # the level contrast must be the sharper of the two.
    assert float(level.p.iloc[0]) < 0.01
    assert float(inter.p.iloc[0]) > float(level.p.iloc[0])


def test_size_stratum_labels_match_the_f2_bounds():
    bounds = [100000, 250000, 1000000, 5000000]
    assert _size_stratum(120_000, bounds) == "100-250k"
    assert _size_stratum(400_000, bounds) == "250k-1M"
    assert _size_stratum(2_000_000, bounds) == "1-5M"
    assert _size_stratum(9_000_000, bounds) == ">5M"


def test_city_descriptives_is_sorted_and_regioned():
    v = _vectors()
    out = city_descriptives(v, {"DE": "West", "FR": "West", "NL": "West",
                                "PL": "CEE", "SE": "North", "IT": "South"},
                            [100000, 250000, 1000000, 5000000])
    assert out.population.is_monotonic_decreasing
    assert out.region.notna().all()
    assert out.mean_everyday.round(4).equals(out.mean_everyday)
