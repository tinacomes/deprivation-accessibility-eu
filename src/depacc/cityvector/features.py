"""Per-city feature vectors, comparable across cities by construction.

Four groups, none contaminated by the deprivation-function scale:

  LEVEL      pop_share_beyond_{regime}_{thr}: population share whose regime
             travel time exceeds a policy threshold (minutes). Uses travel
             time DIRECTLY — deprivation-function-free.
  EQUITY     gini_everyday, gini_emergency (scale-invariant) and the
             tail-robust p90_p50_ratio_emergency (the emergency Gini is
             tail-driven, so report both). gini_t_everyday, gini_t_emergency
             are the DEPRIVATION-FUNCTION-FREE counterparts: the Gini of the
             regime-representative TRAVEL TIME over reachable cells, so the
             plane can be drawn without any DLF/DCF calibration.
  COUPLING   spearman_rho, divergence_gap.
  GRADIENT   fully standardised (SD-per-SD) regression betas of deprivation
             on density and on an income/rent proxy — scale-free.

LEVEL/EQUITY/COUPLING are written per city into cityplane_row.csv (divergence
stage); GRADIENT betas come from equity_regressions.csv. ``build_city_vectors``
assembles them across cities from the accumulated cityplane.csv.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

LEVEL_PREFIX = "pop_share_beyond"

# Feature columns fed to cross-city scaling + clustering. Missing columns are
# tolerated (dropped with a log line) so partial samples still cluster.
FEATURE_GROUPS = {
    "level": [],  # filled dynamically from config thresholds
    "equity": ["gini_everyday", "gini_emergency", "p90_p50_ratio_emergency",
               "gini_t_everyday", "gini_t_emergency"],
    "coupling": ["spearman_rho", "divergence_gap"],
    "gradient": ["slope_density_everyday", "slope_density_emergency",
                 "slope_ses_everyday", "slope_ses_emergency"],
}


def level_feature_names(cfg: dict) -> list[str]:
    thr = cfg.get("cityvector", {}).get("access_thresholds_min", {})
    names = []
    for regime in ("everyday", "emergency"):
        for t in thr.get(regime, []):
            names.append(f"{LEVEL_PREFIX}_{regime}_{int(t)}")
    return names


def level_features(surfaces: pd.DataFrame, cfg: dict) -> dict:
    """Population share whose regime travel time exceeds each threshold
    (deprivation-free). NaN travel times are excluded from the denominator."""
    thr = cfg.get("cityvector", {}).get("access_thresholds_min", {})
    out = {}
    pop = surfaces["population"].to_numpy(dtype=float)
    for regime in ("everyday", "emergency"):
        col = f"t_regime_{regime}"
        if col not in surfaces.columns:
            continue
        t = surfaces[col].to_numpy(dtype=float)
        mask = np.isfinite(t) & (pop > 0)
        denom = float(pop[mask].sum())
        for thr_min in thr.get(regime, []):
            beyond = mask & (t > float(thr_min))
            share = float(pop[beyond].sum()) / denom if denom > 0 else np.nan
            out[f"{LEVEL_PREFIX}_{regime}_{int(thr_min)}"] = share
    return out


def feature_columns(cfg: dict) -> list[str]:
    cols = list(level_feature_names(cfg))
    for group in ("equity", "coupling", "gradient"):
        cols += FEATURE_GROUPS[group]
    return cols


def build_city_vectors(cfg: dict, root: Path) -> pd.DataFrame:
    """Assemble the per-city feature table from the accumulated cityplane.csv
    (level/equity/coupling) plus each city's standardised gradient betas."""
    derived = root / cfg["output"]["root"]
    plane_path = derived / "cityplane.csv"
    if not plane_path.exists() or plane_path.stat().st_size == 0:
        return pd.DataFrame()
    plane = pd.read_csv(plane_path)
    if plane.empty:
        return pd.DataFrame()
    rows = []
    for _, r in plane.iterrows():
        row = r.to_dict()
        row["log10_population"] = float(np.log10(max(r.population, 1.0)))
        regs_path = derived / str(r.city) / "equity_regressions.csv"
        if regs_path.exists():
            regs = pd.read_csv(regs_path)
            slopes = regs[regs.term != "const"]
            for _, s in slopes.iterrows():
                if s.model == "density":
                    row[f"slope_density_{s.regime}"] = s.coef
                elif s.model == "ses" and ("income" in str(s.term)
                                           or "rent" in str(s.term)):
                    row[f"slope_ses_{s.regime}"] = s.coef
        rows.append(row)
    vectors = pd.DataFrame(rows)
    vectors.to_csv(derived / "cityvector.csv", index=False)
    return vectors
