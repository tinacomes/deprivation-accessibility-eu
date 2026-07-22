"""Per-infrastructure accessibility indicators — the intermediary evidence
layer that sits UNDER the deprivation surfaces.

Everything here is on TRAVEL TIME (minutes), not on the deprivation-function
scale, so it is directly interpretable and comparable across services and
cities without any DLF/DCF calibration. For each service it reports the
population-weighted mean / median / p90 of the regime-representative travel
time (effective 2SFCA time for everyday services, nearest-facility time for
emergency services), the population share beyond each policy threshold, and
the unreachable share. The per-regime composite rows summarise the same at
the regime level.

These are written by the deprivation stage to:
    accessibility_by_service.csv   (one row per service)
    accessibility_by_regime.csv    (one row per regime)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _wq(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Population-weighted quantile (finite, positive-weight cells only)."""
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    m = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if m.sum() == 0:
        return float("nan")
    v, w = v[m], w[m]
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w) / w.sum()
    return float(np.interp(q, cw, v))


def _wmean(values: np.ndarray, weights: np.ndarray) -> float:
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    m = np.isfinite(v) & np.isfinite(w) & (w > 0)
    return float(np.average(v[m], weights=w[m])) if m.any() else float("nan")


def _service_regime_map(cfg: dict) -> dict[str, str]:
    out = {}
    for s in cfg.get("everyday_services", {}) or {}:
        out[s] = "everyday"
    for s in cfg.get("emergency_services", {}) or {}:
        out[s] = "emergency"
    return out


def _facility_count(out: Path, service: str) -> float:
    p = out / f"facilities_{service}.parquet"
    if p.exists():
        try:
            return float(len(pd.read_parquet(p, columns=["x"])))
        except Exception:  # pragma: no cover - defensive
            return float("nan")
    return float("nan")


def accessibility_indicators(surfaces: pd.DataFrame, cfg: dict,
                             out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per_service, per_regime) accessibility indicator tables.

    ``surfaces`` is the deprivation-stage frame; it already carries, per
    service ``s``: ``t_regime_<s>`` (effective/nearest time), ``t_nearest_<s>``,
    ``unreachable_<s>`` and ``deprivation_<s>``, plus per-regime composites.
    """
    pop = surfaces["population"].to_numpy(float)
    thr_cfg = cfg.get("cityvector", {}).get("access_thresholds_min", {}) or {}
    srv_regime = _service_regime_map(cfg)

    def _row(label: str, regime: str, t: np.ndarray, unreach: np.ndarray | None,
             dep: np.ndarray | None, n_fac: float) -> dict:
        m = np.isfinite(t) & (pop > 0)
        denom = float(pop[m].sum())
        row = {
            "level": label if label in ("everyday", "emergency") else "service",
            "regime": regime,
            "service": label,
            "n_facilities": n_fac,
            "pop_mean_time_min": _wmean(t, pop),
            "pop_median_time_min": _wq(t, pop, 0.50),
            "pop_p90_time_min": _wq(t, pop, 0.90),
        }
        for thr_min in thr_cfg.get(regime, []) or []:
            beyond = m & (t > float(thr_min))
            row[f"pop_share_beyond_{int(thr_min)}min"] = (
                float(pop[beyond].sum()) / denom if denom > 0 else np.nan)
        if unreach is not None:
            um = unreach.astype(bool) & (pop > 0)
            row["unreachable_pop_share"] = (
                float(pop[um].sum()) / float(pop[pop > 0].sum())
                if float(pop[pop > 0].sum()) > 0 else np.nan)
        if dep is not None:
            row["mean_deprivation"] = _wmean(dep, pop)
        return row

    service_rows = []
    for service, regime in srv_regime.items():
        col = f"t_regime_{service}"
        if col not in surfaces.columns:
            continue
        service_rows.append(_row(
            service, regime,
            surfaces[col].to_numpy(float),
            surfaces[f"unreachable_{service}"].to_numpy()
            if f"unreachable_{service}" in surfaces else None,
            surfaces[f"deprivation_{service}"].to_numpy(float)
            if f"deprivation_{service}" in surfaces else None,
            _facility_count(out, service),
        ))
    per_service = pd.DataFrame(service_rows)

    regime_rows = []
    for regime in ("everyday", "emergency"):
        col = f"t_regime_{regime}"
        if col not in surfaces.columns:
            continue
        regime_rows.append(_row(
            regime, regime,
            surfaces[col].to_numpy(float),
            surfaces[f"unreachable_{regime}"].to_numpy()
            if f"unreachable_{regime}" in surfaces else None,
            surfaces[f"deprivation_{regime}"].to_numpy(float)
            if f"deprivation_{regime}" in surfaces else None,
            float("nan"),
        ))
    per_regime = pd.DataFrame(regime_rows)
    return per_service, per_regime


def write_accessibility_summary(surfaces: pd.DataFrame, cfg: dict,
                                out: Path) -> None:
    per_service, per_regime = accessibility_indicators(surfaces, cfg, out)
    per_service.to_csv(out / "accessibility_by_service.csv", index=False)
    per_regime.to_csv(out / "accessibility_by_regime.csv", index=False)
    cols = ["service", "regime", "n_facilities", "pop_median_time_min",
            "pop_p90_time_min", "unreachable_pop_share"]
    have = [c for c in cols if c in per_service.columns]
    print("accessibility by service (regime-representative travel time):")
    print(per_service[have].to_string(index=False))
