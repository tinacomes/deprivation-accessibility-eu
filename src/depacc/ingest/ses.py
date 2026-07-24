"""National fine-grained SES grids (Tier 2).

Implemented: Germany Zensus 2022 100 m INSPIRE grid CSVs (population, age,
household size, net rent, ownership/vacancy — open data, dl-de/by-2-0).
NL CBS 100 m, FR INSEE Filosofi 200 m and UK LSOA+IMD follow the same
pattern: a per-layer download URL in the city config and a loader that
returns values on EPSG:3035 cell centroids for joining onto the GHS grid.

Layer download URLs live in the city config under `sources.ses.urls`
(zensus2022.de publishes versioned zip names; record the exact URL used —
the provenance sidecar captures it for reproducibility).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from depacc.provenance import download


def fetch_ses_layers(cfg: dict, root: Path) -> dict[str, Path]:
    ses = cfg.get("sources", {}).get("ses", {}) or {}
    urls: dict[str, str] = ses.get("urls", {}) or {}
    raw = root / cfg["output"]["raw_root"] / "ses"
    out = {}
    for layer in ses.get("layers", []):
        if layer not in urls:
            print(f"WARNING: no download URL configured for SES layer "
                  f"'{layer}' (sources.ses.urls.{layer}); skipping.")
            continue
        out[layer] = download(urls[layer], raw / f"{layer}.zip",
                              licence=ses.get("licence", ""))
    return out


def load_inspire_csv_zip(path: Path, value_columns: list[str] | None = None) -> pd.DataFrame:
    """Load a Zensus-2022-style INSPIRE 100 m grid CSV (semicolon-separated,
    German decimal commas) from a zip. Returns a frame with x, y (EPSG:3035
    cell centroids) plus the value columns."""
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(name) as fh:
            df = pd.read_csv(fh, sep=";", decimal=",", low_memory=False)
    xcol = next(c for c in df.columns if c.lower().startswith("x_mp"))
    ycol = next(c for c in df.columns if c.lower().startswith("y_mp"))
    # Every Zensus theme carries a `werterlaeuternde_Zeichen` field — an
    # annotation symbol explaining suppressed/zero values, NOT data. Drop it so
    # it never becomes an all-NaN ses_ column that pollutes the covariate set.
    keep = value_columns or [
        c for c in df.columns
        if c not in (xcol, ycol)
        and not c.upper().startswith("GITTER")
        and "werterlaeuternde" not in c.lower()
    ]
    out = df[[xcol, ycol, *keep]].rename(columns={xcol: "x", ycol: "y"})
    # Zensus files use '–' / empty for suppressed cells -> NaN.
    for c in keep:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def age_group_shares(df: pd.DataFrame, bands: dict[str, list[str]],
                     population_col: str | None = None) -> pd.DataFrame:
    """Derive population shares from raw age-band count columns.

    The Zensus age-structure grid ships absolute head-counts per 5-year band,
    but the downstream vulnerability stratification (share < 15, share >= 65)
    and the EU-census age layer both want *shares*. ``bands`` maps an output
    share name to the count columns that make it up, e.g.
    ``{"share_u15": ["u3", "3_5", "6_14"], "share_ge65": ["65_74", "ge75"]}``.
    Shares are taken over ``population_col`` when given (the correct choice for
    partial bands such as under-15 + 65-plus, which skip the middle of the age
    range). Without it the denominator is the row-sum of every column named
    across all bands, which is only meaningful when those bands are EXHAUSTIVE
    (partition the whole population). Missing counts are treated as zero; a
    zero/NaN denominator yields NaN.
    """
    out = df.copy()

    def _counts(cols: list[str]) -> pd.Series:
        # Suppressed ('–'/empty) cells parse to NaN; treat as a zero count so
        # one missing band does not void the whole share.
        return out[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)

    if population_col is not None:
        denom = pd.to_numeric(out[population_col], errors="coerce")
    else:
        denom = _counts(sorted({c for cols in bands.values() for c in cols}))
    denom = denom.where(denom > 0)  # zero/NaN denominator -> NaN share
    for name, cols in bands.items():
        out[name] = _counts(cols) / denom
    return out


def join_ses_to_cells(cells: pd.DataFrame, layers: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join SES layers onto GHS cells by snapping both to the same 100 m
    EPSG:3035 grid cell (INSPIRE convention: coordinates are cell centres)."""
    out = cells.copy()
    key = (out["x"] // 100).astype(int).astype(str) + "_" + (out["y"] // 100).astype(int).astype(str)
    for name, layer in layers.items():
        lkey = (layer["x"] // 100).astype(int).astype(str) + "_" + (layer["y"] // 100).astype(int).astype(str)
        values = layer.drop(columns=["x", "y"]).set_index(lkey)
        values = values[~values.index.duplicated(keep="first")]
        joined = values.reindex(key)
        for col in values.columns:
            out[f"ses_{name}_{col}" if len(values.columns) > 1 else f"ses_{name}"] = (
                joined[col].to_numpy()
            )
    return out
