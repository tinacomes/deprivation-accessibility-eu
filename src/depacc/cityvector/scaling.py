"""PNAS-style cross-sectional scaling regressions across cities.

Modelled on the Musso et al. (PNAS 2026) reading of urban gradients: each
outcome is regressed on log city size across the cross-section of cities,
and the *trajectory* interpretation is space-for-time — stated on every
output row; nothing here is longitudinal.

Two products:

1. `scaling_table` — per-outcome gradients: ln(y) ~ a + b·ln(P) (log-log,
   reported as an elasticity) when the outcome is strictly positive,
   y ~ a + b·ln(P) (level-log) otherwise; HC1 errors; optional country
   fixed effects to read the within-country size gradient.

2. `regime_slope_difference` — the formal everyday-vs-emergency comparison:
   both regimes' outcomes stacked long, ln(y) ~ ln(P) × regime with
   city-clustered standard errors. The interaction coefficient is the
   difference between the emergency and everyday size gradients — the
   direct test of whether the two deprivation regimes co-evolve or diverge
   along the city-size gradient.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

INFERENCE = "cross-sectional space-for-time"

DEFAULT_OUTCOMES = (
    "mean_everyday", "mean_emergency",
    "gini_everyday", "gini_emergency",
    "compounding_pop_share_50",
    # threshold-free counterpart of the HH share (see divergence/colocation.py)
    "compounding_intensity",
)


def _design(vectors: pd.DataFrame, outcome: str, country_fe: bool):
    df = vectors[["population", outcome]
                 + (["country"] if country_fe else [])].dropna()
    df = df[df.population > 0]
    if (df[outcome] > 0).all():
        y, spec = np.log(df[outcome]), "log-log (elasticity)"
    else:
        y, spec = df[outcome], "level-log"
    x = pd.DataFrame({"ln_pop": np.log(df.population)}, index=df.index)
    if country_fe:
        dummies = pd.get_dummies(df.country, prefix="cty", drop_first=True, dtype=float)
        x = pd.concat([x, dummies], axis=1)
    return y, x, spec, df


def scaling_table(vectors: pd.DataFrame,
                  outcomes: tuple[str, ...] = DEFAULT_OUTCOMES,
                  country_fe: bool = False,
                  min_cities: int = 5) -> pd.DataFrame:
    """Size gradient of each outcome across cities (HC1 errors)."""
    import statsmodels.api as sm

    rows = []
    for outcome in outcomes:
        if outcome not in vectors.columns:
            continue
        y, x, spec, df = _design(vectors, outcome, country_fe)
        if len(df) < max(min_cities, x.shape[1] + 2):
            continue
        fit = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HC1")
        rows.append({
            "outcome": outcome,
            "spec": spec + (" + country FE" if country_fe else ""),
            "gradient_per_ln_pop": fit.params["ln_pop"],
            "se": fit.bse["ln_pop"],
            "p": fit.pvalues["ln_pop"],
            "n_cities": len(df),
            "r2": fit.rsquared,
            "inference": INFERENCE,
        })
    return pd.DataFrame(rows)


def regime_slope_difference(vectors: pd.DataFrame,
                            measure: str = "gini",
                            min_cities: int = 5) -> pd.DataFrame:
    """Test whether the emergency size gradient differs from the everyday one.

    ``measure`` selects the column pair ``<measure>_everyday`` /
    ``<measure>_emergency`` (e.g. gini, mean). Returns one row with the
    interaction (gradient difference), its city-clustered SE and p-value.
    """
    import statsmodels.api as sm

    cols = [f"{measure}_everyday", f"{measure}_emergency"]
    df = vectors[["city", "population", *cols]].dropna()
    df = df[(df.population > 0) & (df[cols] > 0).all(axis=1)]
    if len(df) < min_cities:
        return pd.DataFrame()
    long = df.melt(id_vars=["city", "population"], value_vars=cols,
                   var_name="regime", value_name="y")
    long["emergency"] = (long.regime == f"{measure}_emergency").astype(float)
    long["ln_pop"] = np.log(long.population)
    long["interaction"] = long.ln_pop * long.emergency
    X = sm.add_constant(long[["ln_pop", "emergency", "interaction"]])
    fit = sm.OLS(np.log(long.y), X).fit(
        cov_type="cluster", cov_kwds={"groups": long.city})
    return pd.DataFrame([{
        "measure": measure,
        "gradient_everyday": fit.params["ln_pop"],
        "gradient_difference_emergency": fit.params["interaction"],
        "se": fit.bse["interaction"],
        "p": fit.pvalues["interaction"],
        "n_cities": df.city.nunique(),
        "interpretation": ("emergency deprivation " +
                           ("steepens" if fit.params["interaction"] > 0 else "flattens")
                           + " relative to everyday along the size gradient"),
        "inference": INFERENCE,
    }])
