"""Per-cell potential-deprivation surfaces.

Everyday regime (chosen, repeated, substitutable services):
    t_eff(i)  = softmin_j( t_ij * c_j )      c_j = 2SFCA congestion factor
    D_ev(i)   = g_DLF( t_eff(i) )
Emergency regime (non-substitutable, time-critical):
    D_em(i)   = g_DCF( min_j t_ij )
Both regimes also report the plain nearest-facility travel time t_nearest as
a baseline for comparison.

Input travel times are long-format OD tables (origin cell id, facility id,
time in minutes) with NaN/absent rows meaning no facility of THIS service is
reachable within the cutoff.

Two distinct meanings of "unreachable" are kept apart (methods.md §2):

* **no network path** — the cell is genuinely unroutable (disconnected from
  the network). This is a property of the *cell*, not the service: it is
  supplied by the caller as a shared, service- and mode-independent
  ``routable`` mask, so the everyday and emergency masks coincide. Only these
  cells are flagged ``unreachable=True`` and masked/greyed.
* **reachable but service-deprived** — the cell IS routable but no facility of
  this particular service lies within the cutoff (or its catchment supply is
  vanishing). This is NOT unreachability: it is a badly deprived cell. It is
  assigned a large-but-finite effective time (``finite_fill_min``) so the DLF
  saturates near ``Lmax`` (high deprivation) and the cell stays on the map.

When ``routable`` is not supplied the legacy semantics apply (a cell with no
OD row is treated as unreachable and handled by the configured policy —
"exclude" | "cap_at_max_time"); this path is used by the low-level unit tests.
Cells are always counted, never silently dropped.
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
    *,
    routable: pd.Series | None = None,
    finite_fill_min: float | None = None,
) -> pd.DataFrame:
    """Resolve the two meanings of "unreachable" and apply the DLF/DCF.

    ``routable`` (bool, indexed by cell id) is the shared, service-independent
    "has a network path" mask. When given, cells that lack a time for THIS
    service split into:

    * ``no_path`` (``~routable``) — genuinely unroutable, flagged
      ``unreachable=True`` and handled by ``policy``;
    * ``service_far`` (routable but no facility in reach) — filled with
      ``finite_fill_min`` (large-but-finite → DLF ≈ Lmax) and kept on the map,
      NOT flagged unreachable.

    When ``routable`` is None the legacy semantics apply (missing == no_path).
    """
    surface = surface.copy()
    service_missing = surface[dep_time_col].isna()
    if routable is None:
        no_path = service_missing
        service_far = pd.Series(False, index=surface.index)
    else:
        r = routable.reindex(surface.index).fillna(False).astype(bool)
        no_path = ~r
        service_far = service_missing & r
    surface["unreachable"] = no_path
    # Reachable-but-service-deprived cells: large-but-finite effective time so
    # the deprivation function saturates high; they stay on the map.
    if finite_fill_min is not None and service_far.any():
        for col in time_cols:
            surface.loc[service_far, col] = surface.loc[service_far, col].fillna(
                finite_fill_min
            )
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
    routable: pd.Series | None = None,
    finite_fill_min: float | None = None,
) -> pd.DataFrame:
    """Nearest-facility deprivation surface (emergency regime).

    ``cells`` is indexed by cell id with at least a ``population`` column; the
    result covers ALL cells in it, including those absent from ``od``.
    ``routable``/``finite_fill_min`` split genuinely unroutable cells from
    reachable-but-service-deprived ones (see :func:`_apply_unreachable_policy`).
    """
    nearest = od.groupby(origin_col)[time_col].min()
    surface = cells.copy()
    surface["t_nearest"] = nearest.reindex(surface.index)
    surface = _apply_unreachable_policy(
        surface, ["t_nearest"], dep_fn, "t_nearest", policy, max_time_min,
        routable=routable, finite_fill_min=finite_fill_min,
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
    routable: pd.Series | None = None,
    finite_fill_min: float | None = None,
) -> pd.DataFrame:
    """Potential/gravity deprivation surface (everyday regime).

    Computes the 2SFCA congestion factor per facility, inflates travel times,
    reduces per cell with the soft-minimum and applies the DLF. Also reports
    the un-inflated nearest-facility baseline ``t_nearest`` and the effective
    time ``t_eff``. ``routable``/``finite_fill_min`` split genuinely unroutable
    cells from reachable-but-service-deprived ones (see
    :func:`_apply_unreachable_policy`).
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
        surface, ["t_nearest", "t_eff"], dep_fn, "t_eff", policy, max_time_min,
        routable=routable, finite_fill_min=finite_fill_min,
    )
    surface["congestion_ratio_median"] = float(ratio.dropna().median()) if not ratio.dropna().empty else np.nan
    return surface
