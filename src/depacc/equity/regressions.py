"""Tier-2 within-city equity gradient regressions.

Population-weighted least squares of cell deprivation on SES covariates
(income/rent proxy, age structure, household composition — whatever
`ses_*` columns the city's ingest joined). Reported per regime with robust
(HC1) standard errors. Cross-sectional, descriptive gradients — no causal
claims.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def gradient_regression(surfaces: pd.DataFrame, outcome: str,
                        ses_cols: list[str]) -> pd.DataFrame:
    """Population-weighted OLS of a WITHIN-CITY-STANDARDISED outcome on
    standardised SES covariates.

    Both the deprivation outcome and the covariates are z-scored within the
    city (population-weighted for the outcome), so the coefficients are fully
    standardised (SD-per-SD) — dimensionless, comparable across cities, and
    INVARIANT to the deprivation-function scale. Returns term, coef, se, t, p,
    n, r2.
    """
    import statsmodels.api as sm

    cols = [outcome, "population", *ses_cols]
    df = surfaces[cols].replace([np.inf, -np.inf], np.nan).dropna()
    df = df[df.population > 0]
    if len(df) < len(ses_cols) + 5:
        raise ValueError(
            f"Too few complete cells ({len(df)}) for regression on {ses_cols}"
        )
    # Population-weighted standardisation of the deprivation outcome -> the
    # slope is in outcome-SD units and scale-free.
    w = df["population"].to_numpy()
    y = df[outcome].to_numpy()
    mu = np.average(y, weights=w)
    sd = np.sqrt(np.average((y - mu) ** 2, weights=w))
    y_std = (y - mu) / sd if sd > 0 else np.zeros_like(y)
    # A covariate with no variance on its complete-case support standardises to
    # 0/0 = NaN for every row, and statsmodels then rejects the design matrix
    # with MissingDataError("exog contains inf or nans") — which is NOT a
    # ValueError, so it used to escape the caller's guard and kill the stage.
    # A constant regressor carries no gradient anyway: refuse it here, by name,
    # with an error the caller already handles.
    flat = [c for c in ses_cols if not np.isfinite(df[c].std(ddof=0))
            or df[c].std(ddof=0) == 0]
    if flat:
        raise ValueError(
            f"Covariate(s) {flat} have zero variance over the "
            f"{len(df)} complete cells (constant value "
            f"{[float(df[c].iloc[0]) for c in flat]}) — no gradient to estimate")
    X = df[ses_cols].apply(lambda c: (c - c.mean()) / c.std(ddof=0))
    X = sm.add_constant(X)
    if not np.isfinite(X.to_numpy(dtype=float)).all():
        # Belt and braces: never hand statsmodels a non-finite design matrix.
        raise ValueError(
            f"Non-finite values in the standardised design matrix for "
            f"{ses_cols} after dropping incomplete cells")
    model = sm.WLS(y_std, X, weights=w)
    fit = model.fit(cov_type="HC1")
    return pd.DataFrame({
        "term": fit.params.index,
        "coef": fit.params.to_numpy(),
        "se": fit.bse.to_numpy(),
        "t": fit.tvalues.to_numpy(),
        "p": fit.pvalues.to_numpy(),
        "n": len(df),
        "r2": fit.rsquared,
    })


def density_gradient(surfaces: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Deprivation-density slope: WLS of outcome on log10 population density
    (population per cell is density on a uniform 100 m grid)."""
    df = surfaces[[outcome, "population"]].dropna()
    df = df[df.population > 0]
    x = np.log10(df.population)
    return gradient_regression(
        df.assign(ses_log10_density=x), outcome, ["ses_log10_density"]
    )
