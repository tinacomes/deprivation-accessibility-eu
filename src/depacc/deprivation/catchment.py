"""Two-step floating catchment (2SFCA) congestion factor for the everyday regime.

Step 1 (supply-to-demand ratio per facility j):

    R_j = S_j / sum_i P_i * K(t_ij)

with supply S_j, cell populations P_i and a decreasing catchment kernel K
(gaussian or binary, bandwidth per mode from config). NOTE: the decreasing
kernel lives ONLY here, inside the competition weighting — the deprivation
measure itself remains the increasing convex g(t) applied downstream.

Step 2 is replaced by the congestion INFLATION of travel time: instead of
summing accessibility scores, each facility's crowding inflates the travel
time experienced towards it,

    c_j = (R_ref / R_j) ** gamma        (clipped to config factor_clip)
    effective time towards j:  t_ij * c_j

so a facility with half the reference supply-per-demand behaves as if it were
(2**gamma)x further away. R_ref is the demand-weighted median (or mean) ratio
in the city; gamma = 0 disables congestion. With uniform supply and demand all
R_j are equal and every c_j = 1 (tested).
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def kernel_weight(times, kernel: Mapping) -> np.ndarray:
    """Catchment kernel K(t) on travel times (minutes). NaN -> 0 (pair not in
    catchment)."""
    t = np.asarray(times, dtype=float)
    ktype = kernel.get("type", "gaussian")
    bandwidth = float(kernel["bandwidth"])
    if bandwidth <= 0:
        raise ValueError("kernel bandwidth must be > 0")
    if ktype == "gaussian":
        w = np.exp(-(t**2) / (2.0 * bandwidth**2))
        # Cut the tail so far-away demand does not leak into the catchment.
        w = np.where(t > 3.0 * bandwidth, 0.0, w)
    elif ktype == "binary":
        w = np.where(t <= bandwidth, 1.0, 0.0)
    else:
        raise ValueError(f"Unknown kernel type '{ktype}'")
    return np.where(np.isnan(t), 0.0, w)


def facility_weighted_demand(
    od: pd.DataFrame,
    population: pd.Series,
    supply: pd.Series,
    kernel: Mapping,
    origin_col: str = "origin",
    dest_col: str = "dest",
    time_col: str = "time",
) -> pd.Series:
    """Kernel-weighted demand ``sum_i P_i K(t_ij)`` per facility j (the
    denominator of the 2SFCA ratio). Reindexed to ``supply.index``; facilities
    with no demand in reach are 0. This is also the natural weight for the
    reference ratio in :func:`congestion_factor` — it weights each facility by
    how much demand actually competes for it."""
    w = kernel_weight(od[time_col].to_numpy(), kernel)
    demand = pd.Series(w * population.reindex(od[origin_col]).to_numpy(), index=od[dest_col])
    weighted_demand = demand.groupby(level=0).sum().reindex(supply.index).fillna(0.0)
    weighted_demand.name = "weighted_demand"
    return weighted_demand


def supply_demand_ratio(
    od: pd.DataFrame,
    population: pd.Series,
    supply: pd.Series,
    kernel: Mapping,
    origin_col: str = "origin",
    dest_col: str = "dest",
    time_col: str = "time",
) -> pd.Series:
    """2SFCA step 1: R_j per facility on a long-format OD table.

    ``population`` is indexed by origin (cell) id, ``supply`` by facility id.
    Facilities with zero weighted demand in reach get R_j = NaN (no one
    competes for them; congestion factor falls back to the clip ceiling's
    *lower* bound of burden, i.e. treated as uncongested — see
    :func:`congestion_factor`).
    """
    weighted_demand = facility_weighted_demand(
        od, population, supply, kernel,
        origin_col=origin_col, dest_col=dest_col, time_col=time_col,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        r = supply / weighted_demand.replace(0.0, np.nan)
    r.name = "supply_demand_ratio"
    return r


def congestion_factor(
    ratio: pd.Series,
    gamma: float,
    reference: str = "weighted_median",
    reference_weights: pd.Series | None = None,
    factor_clip: tuple[float, float] = (0.5, 4.0),
) -> pd.Series:
    """2SFCA step 2 as a travel-time inflation factor c_j = (R_ref / R_j)**gamma.

    ``reference_weights`` (e.g. each facility's weighted demand) weight the
    reference median; unweighted median/mean otherwise. Facilities with NaN
    ratio (zero demand in reach) are uncongested: c_j = 1.
    """
    if gamma < 0:
        raise ValueError("gamma must be >= 0")
    lo, hi = factor_clip
    if not (0 < lo <= 1 <= hi):
        raise ValueError("factor_clip must satisfy 0 < lo <= 1 <= hi")
    valid = ratio.dropna()
    if gamma == 0 or valid.empty:
        return pd.Series(1.0, index=ratio.index, name="congestion_factor")
    if reference == "mean":
        ref = float(valid.mean())
    elif reference == "weighted_median":
        if reference_weights is not None:
            w = reference_weights.reindex(valid.index).fillna(0.0).to_numpy()
            ref = _weighted_median(valid.to_numpy(), w)
        else:
            ref = float(valid.median())
    else:
        raise ValueError(f"Unknown reference '{reference}'")
    if ref <= 0 or np.isnan(ref):
        return pd.Series(1.0, index=ratio.index, name="congestion_factor")
    c = (ref / ratio) ** gamma
    c = c.clip(lower=lo, upper=hi).fillna(1.0)
    c.name = "congestion_factor"
    return c


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    if weights.sum() <= 0:
        return float(np.median(values))
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, 0.5 * cum[-1])])
