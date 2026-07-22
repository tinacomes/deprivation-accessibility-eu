"""Divergence stage: percentile typology (multi-threshold) + city-plane row.

Surfaces are wrapped as RegimeSurface and standardised to percentiles before
any cross-regime step; the raw magnitudes never meet on a shared scale.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from depacc.divergence.cityplane import city_row, upsert_cityplane
from depacc.divergence.typology import bivariate_typology, class_shares
from depacc.ingest.pipeline import derived_dir
from depacc.standardize import RegimeSurface, to_percentile


def _surface(surfaces: pd.DataFrame, regime: str, city: str) -> RegimeSurface:
    return RegimeSurface(
        values=surfaces[f"deprivation_{regime}"].to_numpy(dtype=float),
        population=surfaces["population"].to_numpy(dtype=float),
        regime=regime, city_id=city, scale_state="raw",
    )


def run_divergence(cfg: dict, city: str, root: Path) -> None:
    out = derived_dir(cfg, city, root)
    surfaces = pd.read_parquet(out / "surfaces.parquet")

    everyday_raw = _surface(surfaces, "everyday", city)
    emergency_raw = _surface(surfaces, "emergency", city)
    e_p = to_percentile(everyday_raw)
    m_p = to_percentile(emergency_raw)

    thresholds = cfg.get("typology", {}).get("thresholds", [0.5, 0.75])
    cells_out = surfaces[["x", "y", "population"]].copy()
    cells_out["everyday_pct"] = e_p.values
    cells_out["emergency_pct"] = m_p.values
    for thr in thresholds:
        key = f"{int(round(thr * 100)):02d}"
        labels, summary = bivariate_typology(e_p, m_p, threshold=thr)
        cells_out[f"typology_{key}"] = labels
        summary_out = summary.reset_index()
        summary_out["unclassified_pop_share"] = summary.attrs["unclassified_pop_share"]
        summary_out["threshold"] = thr
        summary_out.to_csv(out / f"typology_summary_{key}.csv", index=False)
        print(f"typology @ p{key} shares: "
              + "  ".join(f"{c}={summary.loc[c, 'population_share']:.1%}"
                          for c in ("LL", "LH", "HL", "HH")))
    cells_out.to_parquet(out / "typology.parquet")

    meta = surfaces.attrs if surfaces.attrs else {}
    row = city_row(
        everyday_raw, emergency_raw, cfg, city,
        name=cfg["city"].get("name", city),
        country=cfg["city"].get("country", ""),
        tier=int(cfg["city"].get("tier", 1)),
        synthetic=bool(cfg["city"].get("synthetic", False)),
        population_total=float(surfaces["population"].sum()),
        surfaces=surfaces,
    )
    # deprivation-free LEVEL features (travel-time based) join the city row.
    from depacc.cityvector.features import level_features

    row.update(level_features(surfaces, cfg))
    pd.DataFrame([row]).to_csv(out / "cityplane_row.csv", index=False)
    table = upsert_cityplane(row, root / cfg["output"]["root"] / "cityplane.csv")
    print(f"cityplane.csv: {len(table)} cities; {city}: "
          f"gini_ev={row['gini_everyday']:.3f} gini_em={row['gini_emergency']:.3f} "
          f"rho={row['spearman_rho']:.3f} "
          f"HH@50={row['compounding_pop_share_50']:.1%}")
