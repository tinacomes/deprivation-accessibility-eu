#!/usr/bin/env python3
"""Additional robustness of the scaling regressions (revision round 3).

Recomputes nothing about the indicators; re-estimates the four headline
log-log size regressions (mean and Gini, per regime) from the shipped
tables with:

1. Moran's I of the country-clustered OLS residuals over the city-centre
   coordinates (k = 5 nearest neighbours, row-standardised), permutation p;
2. the cross-equation residual correlation between the everyday and the
   emergency equation (with identical regressors, SUR equals OLS, so this
   correlation is the only quantity joint estimation adds);
3. the size elasticity with mapped GP density per 100k as a control
   (OSM completeness proxy), wild cluster bootstrap p;
4. non-linearity: a centred quadratic in ln population (wild p on the
   squared term) and a country-clustered Wald test of size-stratum dummies;
5. the minimum detectable elasticity at 80 % power from the clustered SE;
6. the cross-city correlation of the two Ginis.

Reads docs/paper-pack/data/ and paper/city_coords.csv; writes
scaling_robustness_extra.csv and scaling_crossequation.csv into the pack.

    cd paper && python3 analysis_scaling_robustness.py
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACK = ROOT / "docs/paper-pack/data"
sys.path.insert(0, str(ROOT / "src"))
from depacc.cityvector.inference import (  # noqa: E402
    _wild_cluster_p_general, N_BOOTSTRAP, SEED)

OUTCOMES = ["mean_everyday", "mean_emergency", "gini_everyday", "gini_emergency"]
K_NEIGHBOURS = 5
N_PERM_MORAN = 9_999


def load() -> pd.DataFrame:
    d = pd.read_csv(PACK / "cities_descriptives.csv")
    main = pd.read_csv(PACK / "cityvector_clustered.csv")
    peeled = pd.read_csv(PACK / "cityvector_clustered_peeled.csv")
    grade = pd.Series("covered", index=d["city"], dtype=object)
    small = peeled["cluster_kmeans"].value_counts().idxmin()
    grade[peeled.loc[peeled["cluster_kmeans"] == small, "city"]] = "partial desert"
    small = main["cluster_kmeans"].value_counts().idxmin()
    grade[main.loc[main["cluster_kmeans"] == small, "city"]] = "desert"
    d["coverage_grade"] = d["city"].map(grade)
    coords = pd.read_csv(pathlib.Path(__file__).resolve().parent / "city_coords.csv")
    acc = pd.read_csv(PACK / "accessibility_by_service_cities.csv")
    gp = acc[(acc.regime == "everyday") & (acc.service == "gp")][["city", "n_facilities"]]
    d = d.merge(coords, on="city").merge(gp, on="city")
    d["gp_per_100k"] = d["n_facilities"] / d["population"] * 1e5
    assert len(d) == 67 and (d["gp_per_100k"] > 0).all()
    d["ln_pop"] = np.log(d["population"])
    d["ln_pop_c"] = d["ln_pop"] - d["ln_pop"].mean()
    d["ln_gp"] = np.log(d["gp_per_100k"])
    return d


def knn_weights(lat: np.ndarray, lon: np.ndarray, k: int) -> np.ndarray:
    phi, lam = np.radians(lat), np.radians(lon)
    dphi = phi[:, None] - phi[None, :]
    dlam = lam[:, None] - lam[None, :]
    h = np.sin(dphi / 2) ** 2 + np.cos(phi[:, None]) * np.cos(phi[None, :]) * np.sin(dlam / 2) ** 2
    dist = 2 * 6371.0 * np.arcsin(np.sqrt(h))
    np.fill_diagonal(dist, np.inf)
    W = np.zeros_like(dist)
    for i in range(len(dist)):
        W[i, np.argsort(dist[i])[:k]] = 1.0
    return W / W.sum(axis=1, keepdims=True)


def morans_i(z: np.ndarray, W: np.ndarray) -> float:
    z = z - z.mean()
    return float(len(z) / W.sum() * (z @ W @ z) / (z @ z))


def moran_perm_p(z: np.ndarray, W: np.ndarray, rng: np.random.Generator) -> float:
    obs = morans_i(z, W)
    hits = 0
    for _ in range(N_PERM_MORAN):
        if abs(morans_i(rng.permutation(z), W)) >= abs(obs):
            hits += 1
    return (hits + 1) / (N_PERM_MORAN + 1)


def main() -> None:
    d = load()
    rng = np.random.default_rng(SEED)
    cl = d["country"].values
    W = knn_weights(d["lat"].values, d["lon"].values, K_NEIGHBOURS)
    strata = pd.get_dummies(d["size_stratum"], drop_first=True, dtype=float)
    grades = pd.get_dummies(d["coverage_grade"], drop_first=True, dtype=float)

    resid = {}
    rows = []
    for out in OUTCOMES:
        y = np.log(d[out].values)
        X1 = sm.add_constant(d["ln_pop"].values)
        fit = sm.OLS(y, X1).fit(cov_type="cluster", cov_kwds={"groups": cl})
        resid[out] = fit.resid
        row = {"outcome": out, "elasticity": float(fit.params[1]),
               "se_cluster_country": float(fit.bse[1]),
               "mde_80pct_power": float(2.80 * fit.bse[1])}
        # 1. Moran's I of residuals
        row["moran_I_resid"] = morans_i(fit.resid, W)
        row["moran_expected"] = -1.0 / (len(y) - 1)
        row["moran_p_perm"] = moran_perm_p(fit.resid, W, rng)
        # 3. GP-density control
        X2 = np.column_stack([np.ones(len(y)), d["ln_pop"].values, d["ln_gp"].values])
        f2 = sm.OLS(y, X2).fit(cov_type="cluster", cov_kwds={"groups": cl})
        row["elasticity_gp_control"] = float(f2.params[1])
        row["p_wild_gp_control"] = _wild_cluster_p_general(
            y, X2, X2[:, [0, 2]], 1, cl, rng, N_BOOTSTRAP)
        row["gp_density_coef"] = float(f2.params[2])
        row["gp_density_p_cluster"] = float(f2.pvalues[2])
        # 4a. quadratic
        X3 = np.column_stack([np.ones(len(y)), d["ln_pop_c"].values,
                              d["ln_pop_c"].values ** 2])
        f3 = sm.OLS(y, X3).fit(cov_type="cluster", cov_kwds={"groups": cl})
        row["quadratic_coef"] = float(f3.params[2])
        row["p_wild_quadratic"] = _wild_cluster_p_general(
            y, X3, X3[:, [0, 1]], 2, cl, rng, N_BOOTSTRAP)
        # 4a'. quadratic with coverage-grade dummies (Section 2.3 model)
        X3g = np.column_stack([X3, grades.values])
        f3g = sm.OLS(y, X3g).fit(cov_type="cluster", cov_kwds={"groups": cl})
        row["quadratic_coef_grade_ctrl"] = float(f3g.params[2])
        row["p_wild_quadratic_grade_ctrl"] = _wild_cluster_p_general(
            y, X3g, np.delete(X3g, 2, axis=1), 2, cl, rng, N_BOOTSTRAP)
        # 4b. stratum dummies (clustered Wald)
        X4 = sm.add_constant(strata.values)
        f4 = sm.OLS(y, X4).fit(cov_type="cluster", cov_kwds={"groups": cl})
        R = np.zeros((strata.shape[1], X4.shape[1])); R[:, 1:] = np.eye(strata.shape[1])
        row["p_strata_wald_cluster"] = float(f4.wald_test(R, scalar=True).pvalue)
        row["strata_means"] = "; ".join(
            f"{s}: {np.exp(y[d['size_stratum'] == s]).mean():.3f}"
            for s in d["size_stratum"].unique())
        rows.append(row)
    extra = pd.DataFrame(rows)
    extra.to_csv(PACK / "scaling_robustness_extra.csv", index=False)

    # 2. cross-equation residual correlation; 6. Gini correlation
    ce = []
    for a, b, lab in (("mean_everyday", "mean_emergency", "means"),
                      ("gini_everyday", "gini_emergency", "ginis")):
        r, p = stats.pearsonr(resid[a], resid[b])
        ce.append({"pair": f"residuals ({lab})", "pearson_r": r, "p": p,
                   "note": "identical regressors: SUR = OLS; this correlation "
                           "is what joint estimation adds"})
    r, p = stats.pearsonr(d["gini_everyday"], d["gini_emergency"])
    rs, ps = stats.spearmanr(d["gini_everyday"], d["gini_emergency"])
    ce.append({"pair": "gini_everyday vs gini_emergency (Pearson)",
               "pearson_r": r, "p": p, "note": "cross-city"})
    ce.append({"pair": "gini_everyday vs gini_emergency (Spearman)",
               "pearson_r": rs, "p": ps, "note": "cross-city"})
    ce = pd.DataFrame(ce)
    ce.to_csv(PACK / "scaling_crossequation.csv", index=False)

    pd.set_option("display.width", 220)
    print(extra.drop(columns=["strata_means"]).round(4).to_string(index=False))
    print(extra[["outcome", "strata_means"]].to_string(index=False))
    print(ce.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
