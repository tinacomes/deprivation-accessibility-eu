"""Country-clustered inference for the cross-city claims.

Cities nest in countries and the macro-region is a COUNTRY-level variable
(every Polish city is CEE by construction), so tests that treat 67 cities as
independent overstate the evidence — the effective sample for a regional
contrast is the ~24 countries, not the 67 cities. This module re-tests the
headline claims at the level the design actually supports:

* ``regional_tests`` — for each outcome: the (anti-conservative) city-level
  ANOVA for reference, the country-aggregated ANOVA, an EXACT permutation
  test that reassigns whole countries to regions (the right null when region
  is a deterministic grouping of countries), and a mixed model with a country
  random intercept as triangulation.
* ``scaling_clustered`` — the log-log scaling regressions with
  country-clustered standard errors plus a wild cluster bootstrap p-value
  (Rademacher weights on country blocks; with ~24 clusters the asymptotic
  cluster-robust p alone is borderline).
* ``equivalence_tost`` — the "emergency access does not scale" claim as a
  POSITIVE claim: two one-sided tests that the emergency elasticity lies
  within +/- ``bound``, on the country-clustered SE. A non-significant slope
  is absence of evidence; TOST is evidence of absence.

All estimation is cross-sectional space-for-time, like the rest of the
cityvector stage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REGIONAL_OUTCOMES = (
    "spearman_rho", "gini_everyday", "gini_emergency",
    "divergence_gap", "compounding_pop_share_50", "compounding_intensity",
)
SCALING_OUTCOMES = ("mean_everyday", "mean_emergency", "gini_everyday",
                    "gini_emergency")
N_PERMUTATIONS = 10_000
N_BOOTSTRAP = 4_999
SEED = 20260803          # the study seed (config city_definition.region_strata)


def _anova_f(values: pd.Series, groups: pd.Series) -> tuple[float, float, float]:
    """One-way ANOVA F, p and Cohen f (descriptive) on the given grouping."""
    from scipy import stats

    arrays = [v.dropna().values for _, v in values.groupby(groups)]
    arrays = [a for a in arrays if len(a)]
    if len(arrays) < 2:
        return np.nan, np.nan, np.nan
    F, p = stats.f_oneway(*arrays)
    gm = np.concatenate(arrays).mean()
    ssb = sum(len(a) * (a.mean() - gm) ** 2 for a in arrays)
    ssw = sum(((a - a.mean()) ** 2).sum() for a in arrays)
    f = np.sqrt(ssb / ssw) if ssw > 0 else np.nan
    return float(F), float(p), float(f)


def _permutation_p(country_means: pd.Series, country_region: pd.Series,
                   rng: np.random.Generator,
                   n_perm: int = N_PERMUTATIONS) -> float:
    """Exact-style permutation p for a regional contrast, permuting WHOLE
    COUNTRIES across regions (region sizes held fixed). The unit of exchange
    is the country because region varies only at the country level."""
    obs_F, _, _ = _anova_f(country_means, country_region)
    if not np.isfinite(obs_F):
        return np.nan
    # Plain object ndarray: rng.shuffle on a pandas Arrow-backed array is not
    # guaranteed correct (and warns once per permutation).
    labels = np.asarray(country_region.astype(str).values, dtype=object).copy()
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(labels)
        F, _, _ = _anova_f(country_means, pd.Series(labels,
                                                    index=country_means.index))
        if F >= obs_F:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def _mixed_model_p(df: pd.DataFrame, outcome: str) -> float:
    """Wald p for the region terms in outcome ~ region + (1 | country).
    Triangulation only — with few countries the permutation test is the
    primary country-level evidence. NaN when the fit fails to converge."""
    import statsmodels.formula.api as smf

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = smf.mixedlm(f"{outcome} ~ C(region)", df,
                              groups=df["country"]).fit(reml=False)
        terms = [t for t in fit.params.index if t.startswith("C(region)")]
        if not terms:
            return np.nan
        return float(fit.wald_test(terms, scalar=True).pvalue)
    except Exception:
        return np.nan


def regional_tests(vectors: pd.DataFrame, region_of: dict[str, str],
                   outcomes=REGIONAL_OUTCOMES, seed: int = SEED,
                   n_perm: int = N_PERMUTATIONS) -> pd.DataFrame:
    df = vectors.copy()
    df["region"] = df["country"].map(region_of)
    df = df.dropna(subset=["region"])
    rng = np.random.default_rng(seed)
    rows = []
    for outcome in outcomes:
        if outcome not in df.columns:
            continue
        sub = df.dropna(subset=[outcome])
        F_city, p_city, cohen_f = _anova_f(sub[outcome], sub["region"])
        cm = sub.groupby("country")[outcome].mean()
        cr = sub.groupby("country")["region"].first()
        F_ctry, p_ctry, _ = _anova_f(cm, cr)
        p_perm = _permutation_p(cm, cr, rng, n_perm)
        rows.append({
            "outcome": outcome,
            "n_cities": len(sub), "n_countries": len(cm),
            "cohen_f_city": cohen_f,
            "F_city": F_city, "p_city_anova_anticonservative": p_city,
            "F_country_means": F_ctry, "p_country_anova": p_ctry,
            "p_permutation_countries": p_perm,
            "p_mixed_model": _mixed_model_p(sub, outcome),
            "inference": "region is country-level; permutation over "
                         "countries is the primary test",
        })
    return pd.DataFrame(rows)


def _wild_cluster_p(y: np.ndarray, x: np.ndarray, clusters: np.ndarray,
                    rng: np.random.Generator,
                    n_boot: int = N_BOOTSTRAP) -> float:
    """Wild cluster bootstrap p for the slope of y ~ x (null: slope 0),
    Rademacher weights per cluster, restricted residuals (Cameron-Gelbach-
    Miller). Two-sided."""
    import statsmodels.api as sm

    X = sm.add_constant(x)
    fit = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": clusters})
    t_obs = fit.tvalues[1]
    # Restricted model (slope = 0): intercept-only residuals.
    resid0 = y - y.mean()
    uniq = np.unique(clusters)
    hits = 0
    for _ in range(n_boot):
        w = rng.choice([-1.0, 1.0], size=len(uniq))
        wmap = dict(zip(uniq, w))
        y_star = y.mean() + resid0 * np.vectorize(wmap.get)(clusters)
        f = sm.OLS(y_star, X).fit(cov_type="cluster",
                                  cov_kwds={"groups": clusters})
        if abs(f.tvalues[1]) >= abs(t_obs):
            hits += 1
    return (hits + 1) / (n_boot + 1)


def scaling_clustered(vectors: pd.DataFrame, outcomes=SCALING_OUTCOMES,
                      seed: int = SEED,
                      n_boot: int = N_BOOTSTRAP) -> pd.DataFrame:
    """Log-log scaling with country-clustered SEs + wild cluster bootstrap."""
    import statsmodels.api as sm

    rng = np.random.default_rng(seed)
    rows = []
    for outcome in outcomes:
        if outcome not in vectors.columns:
            continue
        df = vectors.dropna(subset=[outcome, "population", "country"])
        df = df[(df["population"] > 0) & (df[outcome] > 0)]
        if len(df) < 8 or df["country"].nunique() < 5:
            continue
        y = np.log(df[outcome].values)
        x = np.log(df["population"].values)
        cl = df["country"].values
        X = sm.add_constant(x)
        fit = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": cl})
        rows.append({
            "outcome": outcome,
            "elasticity": float(fit.params[1]),
            "se_cluster_country": float(fit.bse[1]),
            "p_cluster_country": float(fit.pvalues[1]),
            "p_wild_cluster_bootstrap": _wild_cluster_p(y, x, cl, rng, n_boot),
            "n_cities": len(df), "n_countries": df["country"].nunique(),
            "inference": "country-clustered; cross-sectional space-for-time",
        })
    return pd.DataFrame(rows)


def equivalence_tost(vectors: pd.DataFrame, outcome: str = "mean_emergency",
                     bound: float = 0.10) -> pd.DataFrame:
    """TOST: is the ``outcome`` elasticity within +/- bound? Country-clustered
    SE; p_tost = max of the two one-sided p's. Significant p_tost = the slope
    is POSITIVELY shown to be practically flat, not merely non-significant."""
    import statsmodels.api as sm
    from scipy import stats

    df = vectors.dropna(subset=[outcome, "population", "country"])
    df = df[(df["population"] > 0) & (df[outcome] > 0)]
    y = np.log(df[outcome].values)
    X = sm.add_constant(np.log(df["population"].values))
    fit = sm.OLS(y, X).fit(cov_type="cluster",
                           cov_kwds={"groups": df["country"].values})
    b, se = float(fit.params[1]), float(fit.bse[1])
    dof = df["country"].nunique() - 1     # conservative cluster dof
    p_lower = float(stats.t.sf((b + bound) / se, dof))   # H0: b <= -bound
    p_upper = float(stats.t.sf((bound - b) / se, dof))   # H0: b >= +bound
    # The smallest symmetric bound at which equivalence WOULD be shown at
    # alpha = 0.05 — reported so the reader can judge the achieved precision
    # instead of us shopping for a passing bound.
    t05 = float(stats.t.ppf(0.95, dof))
    smallest = abs(b) + t05 * se
    return pd.DataFrame([{
        "outcome": outcome, "elasticity": b, "se_cluster_country": se,
        "equivalence_bound": bound, "p_tost": max(p_lower, p_upper),
        "smallest_passing_bound": smallest,
        "dof_countries": dof, "n_cities": len(df),
        "conclusion": ("practically flat (within bound)"
                       if max(p_lower, p_upper) < 0.05
                       else "equivalence not shown at this bound"),
    }])


def run_inference(vectors: pd.DataFrame, region_of: dict[str, str],
                  derived) -> None:
    """Compute and write the three tables; called from the cross stage."""
    reg = regional_tests(vectors, region_of)
    if not reg.empty:
        reg.to_csv(derived / "inference_regional.csv", index=False)
        print("regional contrasts at COUNTRY level "
              "(permutation over countries is primary):")
        for _, r in reg.iterrows():
            print(f"  {r.outcome:26s} f={r.cohen_f_city:.2f} "
                  f"p_city={r.p_city_anova_anticonservative:.4f} -> "
                  f"p_perm={r.p_permutation_countries:.4f} "
                  f"(p_country_anova={r.p_country_anova:.4f}, "
                  f"p_mixed={r.p_mixed_model:.4f})")
    sc = scaling_clustered(vectors)
    if not sc.empty:
        sc.to_csv(derived / "inference_scaling_clustered.csv", index=False)
        print("scaling with country-clustered SEs (+ wild cluster bootstrap):")
        for _, r in sc.iterrows():
            print(f"  {r.outcome:16s} b={r.elasticity:+.3f} "
                  f"se={r.se_cluster_country:.3f} "
                  f"p_cluster={r.p_cluster_country:.4g} "
                  f"p_wild={r.p_wild_cluster_bootstrap:.4f}")
    tost = equivalence_tost(vectors)
    if not tost.empty:
        tost.to_csv(derived / "inference_equivalence.csv", index=False)
        r = tost.iloc[0]
        print(f"TOST {r.outcome}: b={r.elasticity:+.3f} within "
              f"+/-{r.equivalence_bound}? p_tost={r.p_tost:.4f} -> "
              f"{r.conclusion}")
