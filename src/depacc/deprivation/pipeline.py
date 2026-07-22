"""Deprivation stage: per-service and composite everyday/emergency surfaces.

Reads the OD matrices and facility tables produced by access/, evaluates

    everyday  : D_s(i) = g_DLF( softmin_j( t_ij * c_j ) )   (2SFCA congestion)
    emergency : D_s(i) = g_DCF( min_j t_ij )

per service s, always alongside the plain nearest-time baseline, then
composes the per-regime surfaces (equal-weight mean by default) and writes
data/derived/<city>/surfaces.parquet.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from depacc.config import deprivation_spec
from depacc.deprivation.functions import DeprivationFunction
from depacc.deprivation.surfaces import emergency_surface, everyday_surface
from depacc.ingest.pipeline import derived_dir


def _combined_od(out: Path, service: str, modes: list[str]) -> pd.DataFrame | None:
    """Elementwise-minimum travel time across the regime's modes."""
    frames = []
    for mode in modes:
        p = out / f"od_{service}_{mode}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return None
    od = pd.concat(frames, ignore_index=True)
    return od.groupby(["origin", "dest"], as_index=False)["time"].min()


def run_deprivation(cfg: dict, city: str, root: Path,
                    alternative: str | None = None) -> None:
    out = derived_dir(cfg, city, root)
    if not (out / "cells.parquet").exists() or not list(out.glob("od_*.parquet")):
        raise RuntimeError(
            f"Missing ingest/access outputs in {out} — run stages 'ingest' "
            f"and 'access' before 'deprivation' (each GitHub run is a fresh "
            f"machine; the per-city data/derived cache carries them forward, "
            f"but re-dispatch stage 'all' for '{city}' if it was evicted)."
        )
    cells = pd.read_parquet(out / "cells.parquet").set_index("cell_id")
    surfaces = cells.copy()
    max_time = float(cfg["routing"]["max_time_min"])
    policy = cfg["unreachable"]["policy"]

    for regime, service_key in (("everyday", "everyday_services"),
                                ("emergency", "emergency_services")):
        spec = deprivation_spec(cfg, regime, alternative=alternative)
        g = DeprivationFunction.from_spec(spec, context=f"{regime} deprivation")
        rcfg = cfg["regimes"][regime]
        modes = rcfg["modes"]
        per_service = []
        for service in cfg.get(service_key, {}):
            od = _combined_od(out, service, modes)
            if od is None:
                print(f"WARNING: no OD matrix for '{service}' ({modes}); skipped")
                continue
            if regime == "everyday":
                facilities = pd.read_parquet(out / f"facilities_{service}.parquet")
                supply = facilities.set_index("dest_id")["capacity"]
                kernel = {
                    "type": cfg["catchment"]["kernel"]["type"],
                    "bandwidth": cfg["catchment"]["kernel"]["bandwidth_min"][modes[0]],
                }
                surf = everyday_surface(
                    od, cells, supply, g,
                    kappa=float(cfg["softmin"]["kappa"]),
                    kernel=kernel,
                    gamma=float(cfg["catchment"]["gamma"]),
                    reference=cfg["catchment"]["reference"],
                    factor_clip=tuple(cfg["catchment"]["factor_clip"]),
                    policy=policy, max_time_min=max_time,
                )
                surfaces[f"t_eff_{service}"] = surf["t_eff"]
            else:
                surf = emergency_surface(od, cells, g, policy=policy,
                                         max_time_min=max_time)
            surfaces[f"t_nearest_{service}"] = surf["t_nearest"]
            surfaces[f"deprivation_{service}"] = surf["deprivation"]
            surfaces[f"unreachable_{service}"] = surf["unreachable"]
            # regime-representative travel time per service: effective time
            # (everyday) or nearest time (emergency) — feeds the deprivation-
            # function-FREE level features in cityvector/.
            surfaces[f"t_regime_{service}"] = (
                surf["t_eff"] if regime == "everyday" else surf["t_nearest"])
            per_service.append(service)
            share = float(
                surf.loc[surf.unreachable, "population"].sum() / surf.population.sum()
            )
            print(f"{regime}[{service}]: pop-weighted unreachable share {share:.2%}")

        if not per_service:
            raise RuntimeError(f"No services computed for regime '{regime}'")
        dep_cols = [f"deprivation_{s}" for s in per_service]
        if rcfg.get("composite", "mean") != "mean":
            raise NotImplementedError("Only 'mean' composite implemented")
        weights = rcfg.get("composite_weights") or {}
        w = np.array([float(weights.get(s, 1.0)) for s in per_service])
        vals = surfaces[dep_cols].to_numpy(dtype=float)
        surfaces[f"deprivation_{regime}"] = _weighted_row_mean(vals, w)
        surfaces[f"unreachable_{regime}"] = surfaces[
            [f"unreachable_{s}" for s in per_service]
        ].any(axis=1)
        # composite regime travel time = weighted mean over services of the
        # regime-representative per-service times (deprivation-free level).
        t_cols = [f"t_regime_{s}" for s in per_service]
        surfaces[f"t_regime_{regime}"] = _weighted_row_mean(
            surfaces[t_cols].to_numpy(dtype=float), w)

    surfaces["deprivation_kind_everyday"] = deprivation_spec(cfg, "everyday").get("kind")
    surfaces["deprivation_kind_emergency"] = deprivation_spec(cfg, "emergency").get("kind")
    surfaces.to_parquet(out / "surfaces.parquet")
    print(f"surfaces.parquet: {len(surfaces)} cells, "
          f"{surfaces.population.sum() / 1e3:.1f}k people")

    # Intermediary, deprivation-function-FREE accessibility indicators per
    # infrastructure (travel-time based) — the evidence layer under the
    # deprivation surfaces, for justification and city-level reporting.
    from depacc.access.summary import write_accessibility_summary

    write_accessibility_summary(surfaces, cfg, out)


def _weighted_row_mean(vals: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Row mean over available (non-NaN) services with weights renormalised
    per row, so an excluded-unreachable service does not NaN the composite
    unless every service is missing."""
    mask = ~np.isnan(vals)
    wm = np.where(mask, w[None, :], 0.0)
    denom = wm.sum(axis=1)
    with np.errstate(invalid="ignore"):
        out = np.nansum(vals * wm, axis=1) / denom
    return np.where(denom > 0, out, np.nan)
