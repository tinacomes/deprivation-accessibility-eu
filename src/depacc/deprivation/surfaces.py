"""Per-cell potential-deprivation surfaces.

Everyday regime (chosen, repeated, substitutable services):
    t_eff(i)  = softmin_j( t_ij * c_j )      c_j = 2SFCA congestion factor
    D_ev(i)   = g_DLF( t_eff(i) )
Emergency regime (non-substitutable, time-critical):
    D_em(i)   = g_DCF( min_j t_ij )
Both regimes also report the plain nearest-facility travel time t_nearest as
a baseline for comparison.

Input travel times are long-format OD tables (origin cell id, facility id,
time in minutes) with NaN/absent rows meaning unreachable within the cutoff.
Cells with no reachable facility are flagged ``unreachable=True`` and handled
by the configured policy ("exclude" | "cap_at_max_time"); they are always
counted, never silently dropped.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from depacc.deprivation.catchment import (
    congestion_factor,
    facility_weighted_demand,
)
from depacc.deprivation.functions import DeprivationFunction
from depacc.deprivation.softmin import grouped_softmin


def _apply_unreachable_policy(
    surface: pd.DataFrame,
    time_cols: list[str],
    dep_fn: DeprivationFunction,
    dep_time_col: str,
    policy: str,
    max_time_min: float,
) -> pd.DataFrame:
    surface = surface.copy()
    surface["unreachable"] = surface[dep_time_col].isna()
    if policy == "cap_at_max_time":
        for col in time_cols:
            surface[col] = surface[col].fillna(max_time_min)
        surface["deprivation"] = dep_fn(surface[dep_time_col].to_numpy())
    elif policy == "exclude":
        surface["deprivation"] = np.where(
            surface["unreachable"], np.nan, dep_fn(surface[dep_time_col].fillna(0).to_numpy())
        )
    else:
        raise ValueError(f"Unknown unreachable policy '{policy}'")
    return surface


def emergency_surface(
    od: pd.DataFrame,
    cells: pd.DataFrame,
    dep_fn: DeprivationFunction,
    *,
    policy: str = "cap_at_max_time",
    max_time_min: float = 120.0,
    origin_col: str = "origin",
    time_col: str = "time",
) -> pd.DataFrame:
    """Nearest-facility deprivation surface (emergency regime).

    ``cells`` is indexed by cell id with at least a ``population`` column; the
    result covers ALL cells in it, including those absent from ``od``.
    """
    nearest = od.groupby(origin_col)[time_col].min()
    surface = cells.copy()
    surface["t_nearest"] = nearest.reindex(surface.index)
    surface = _apply_unreachable_policy(
        surface, ["t_nearest"], dep_fn, "t_nearest", policy, max_time_min
    )
    return surface


def everyday_surface(
    od: pd.DataFrame,
    cells: pd.DataFrame,
    supply: pd.Series,
    dep_fn: DeprivationFunction,
    *,
    kappa: float,
    kernel: Mapping,
    gamma: float,
    reference: str = "weighted_median",
    factor_clip: tuple[float, float] = (0.5, 4.0),
    policy: str = "cap_at_max_time",
    max_time_min: float = 120.0,
    origin_col: str = "origin",
    dest_col: str = "dest",
    time_col: str = "time",
) -> pd.DataFrame:
    """Potential/gravity deprivation surface (everyday regime).

    Computes the 2SFCA congestion factor per facility, inflates travel times,
    reduces per cell with the soft-minimum and applies the DLF. Also reports
    the un-inflated nearest-facility baseline ``t_nearest`` and the effective
    time ``t_eff``.
    """
    population = cells["population"]
    # Kernel-weighted demand per facility (2SFCA denominator); computed once
    # and reused as the reference-median weights so the reference ratio is
    # weighted by the demand actually competing for each facility.
    demand = facility_weighted_demand(
        od, population, supply, kernel,
        origin_col=origin_col, dest_col=dest_col, time_col=time_col,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = supply / demand.replace(0.0, np.nan)
    ratio.name = "supply_demand_ratio"
    factor = congestion_factor(
        ratio, gamma, reference=reference, reference_weights=demand,
        factor_clip=factor_clip,
    )
    inflated = od[[origin_col, dest_col]].copy()
    inflated["time"] = (
        od[time_col].to_numpy() * factor.reindex(od[dest_col]).to_numpy()
    )
    t_eff = grouped_softmin(inflated, kappa, group_col=origin_col, time_col="time")
    # The substitutability bonus (softmin < min by up to ln(n)/kappa) can dip
    # below zero when several facilities are a fraction of a minute away;
    # effective time is physically floored at zero.
    t_eff = t_eff.clip(lower=0.0)
    nearest = od.groupby(origin_col)[time_col].min()

    surface = cells.copy()
    surface["t_nearest"] = nearest.reindex(surface.index)
    surface["t_eff"] = t_eff.reindex(surface.index)
    surface = _apply_unreachable_policy(
        surface, ["t_nearest", "t_eff"], dep_fn, "t_eff", policy, max_time_min
    )
    surface["congestion_ratio_median"] = float(ratio.dropna().median()) if not ratio.dropna().empty else np.nan
    return surface
