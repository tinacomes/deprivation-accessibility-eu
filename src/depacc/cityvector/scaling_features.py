"""Cross-city feature standardisation as an enforced contract.

Clustering must never see raw cross-city magnitudes. ``scale_features``
returns a ``ScaledFeatures`` token carrying the standardised matrix and the
fitted center/scale; the clustering functions accept ONLY that token, so an
unscaled DataFrame cannot reach them through the type signature.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ScaledFeatures:
    """Standardised cross-city feature matrix + the scaler that produced it.
    Only object clustering will accept."""

    matrix: np.ndarray            # (n_cities, n_features), standardised
    cities: list[str]
    feature_names: list[str]
    method: str                   # "robust" | "zscore"
    center: np.ndarray
    scale: np.ndarray
    # (n_cities, n_features) boolean: where a city had no value and was imputed
    # at the scaled centre. Carried on the token so a consumer can weight, mask
    # or report it rather than having to re-derive it from the source frame.
    imputed: np.ndarray | None = None


DEFAULT_MAX_MISSING_SHARE = 0.25


def scale_features(vectors: pd.DataFrame, feature_cols: list[str],
                   method: str = "robust", city_col: str = "city",
                   max_missing_share: float = DEFAULT_MAX_MISSING_SHARE
                   ) -> ScaledFeatures:
    """Standardise selected feature columns ACROSS cities. Robust = median/IQR
    (default; small, outlier-prone sample); zscore = mean/SD. Emits center/scale
    per feature.

    A feature is DROPPED when it is absent, carries fewer than two cities, has no
    spread, or is missing for more than ``max_missing_share`` of the sample. A
    feature that survives but is missing for a few cities is imputed at the scaled
    centre, and every such (city, feature) is named in the log.

    The bound and the reporting both exist because the imputation is otherwise
    invisible and actively misleading. A city missing a feature lands at the
    sample MEDIAN of it — made to look exactly typical on a variable never
    measured for it, and then clustered on that. `slope_ses_*` is the live case:
    activity status is voluntary under Reg. 2018/1799 and DE and FR are the two
    countries that do not report it, so every German and French city carries NaN
    there by design. With a pilot drawn from `stratified_countries: [DE, NL, FR]`
    that is most of the sample being told it is average on a dimension it has no
    data for. Above the bound the honest move is to drop the dimension; below it,
    to impute but say so.
    """
    cols = [c for c in feature_cols if c in vectors.columns]
    dropped = {c: "absent" for c in feature_cols if c not in vectors.columns}
    sub = vectors[cols].apply(pd.to_numeric, errors="coerce")
    n_cities = len(sub)
    usable = []
    for c in cols:
        col = sub[c].to_numpy(dtype=float)
        n_ok = int(np.isfinite(col).sum())
        if n_ok < 2:
            dropped[c] = f"only {n_ok} city/ies carry it"
            continue
        missing_share = 1.0 - n_ok / n_cities if n_cities else 1.0
        if missing_share > max_missing_share:
            dropped[c] = (f"missing for {missing_share:.0%} of cities "
                          f"(> max_missing_share {max_missing_share:.0%})")
            continue
        spread = (np.nanpercentile(col, 75) - np.nanpercentile(col, 25)
                  if method == "robust" else np.nanstd(col))
        if not np.isfinite(spread) or spread == 0:
            dropped[c] = "no spread across cities"
            continue
        usable.append(c)
    if dropped:
        print("cross-city scaler: dropping " + ", ".join(
            f"{c} ({why})" for c, why in sorted(dropped.items())))
    X = sub[usable].to_numpy(dtype=float)
    if method == "robust":
        center = np.nanmedian(X, axis=0)
        scale = np.nanpercentile(X, 75, axis=0) - np.nanpercentile(X, 25, axis=0)
    elif method == "zscore":
        center = np.nanmean(X, axis=0)
        scale = np.nanstd(X, axis=0)
    else:
        raise ValueError(f"unknown scaler method {method!r}")
    scale = np.where(scale > 0, scale, 1.0)
    Z = (X - center) / scale
    # Impute the residual NaN (a city missing a retained feature) at the scaled
    # centre — and NAME it, so no city is silently declared average.
    gaps = ~np.isfinite(Z)
    if gaps.any():
        city_ids = list(vectors[city_col].astype(str))
        for i, j in zip(*np.nonzero(gaps)):
            print(f"  cross-city scaler: {city_ids[i]} has no {usable[j]} — "
                  f"imputed at the sample centre for clustering")
    Z = np.where(gaps, 0.0, Z)
    print(f"cross-city scaler={method}: {len(usable)} features, "
          f"center={np.round(center, 3).tolist()}, scale={np.round(scale, 3).tolist()}")
    return ScaledFeatures(
        matrix=Z, cities=list(vectors[city_col].astype(str)),
        feature_names=usable, method=method, center=center, scale=scale,
        imputed=gaps,
    )
