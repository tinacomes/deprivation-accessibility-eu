"""National fine-grained SES grids (Tier 2).

Implemented: Germany Zensus 2022 100 m INSPIRE grid CSVs (population, age,
household size, net rent, ownership/vacancy — open data, dl-de/by-2-0).
NL CBS 100 m, FR INSEE Filosofi 200 m and UK LSOA+IMD follow the same
pattern: a per-layer download URL in the city config and a loader that
returns values on EPSG:3035 cell centroids for joining onto the GHS grid.

Layer download URLs live in the city config under `sources.ses.urls`
(zensus2022.de publishes versioned zip names; record the exact URL used —
the provenance sidecar captures it for reproducibility).

**One Zensus zip holds SEVERAL grids.** Each destatis "Gitterdaten" archive
bundles the same theme at 10 km, 1 km and 100 m (plus a
`Datenzusatzbeschreibung` readme), e.g.
``Leerstandsquote_in_Gitterzellen-100m-Gitter.csv`` beside the 1 km and 10 km
files. The member is therefore selected by RESOLUTION, never by "the first
.csv in the archive" — and the resolution is then re-derived from the chosen
file's own column names (`x_mp_100m`) and cross-checked against what the
config asked for, so a wrong pick fails loudly instead of producing an
all-NaN covariate. That silent failure is exactly what happened to the
ownership/vacancy layers in the first Hamburg run: a coarser member was
loaded, every 100 m join key missed, and the columns arrived empty.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

from depacc.provenance import download

# Grid-resolution token as it appears in Zensus member names and coordinate
# column suffixes: 100 -> "100m", 1000 -> "1km", 10000 -> "10km".
_RES_SUFFIX_RE = re.compile(r"(?<![0-9])(?P<n>[0-9]+)(?P<unit>km|m)\b", re.IGNORECASE)


def resolution_token(resolution_m: float) -> str:
    """Member/column token for a grid resolution in metres."""
    res = int(round(float(resolution_m)))
    return f"{res // 1000}km" if res >= 1000 and res % 1000 == 0 else f"{res}m"


def _token_resolution_m(token: str) -> float | None:
    m = _RES_SUFFIX_RE.search(token)
    if not m:
        return None
    return float(m.group("n")) * (1000.0 if m.group("unit").lower() == "km" else 1.0)


def select_grid_member(names: list[str], *, member: str | None = None,
                       resolution_m: float | None = None,
                       archive: str = "") -> str:
    """Pick the CSV member of a Zensus-style archive.

    ``member`` (a case-insensitive substring) wins; otherwise the resolution
    token — ``resolution_m=100`` matches ``…-100m-Gitter.csv`` and not the
    1 km / 10 km siblings. With neither, a single-CSV archive is unambiguous
    and anything else raises rather than guessing: picking the first member of
    a multi-resolution archive is how a whole layer silently joins to nothing.
    """
    csvs = [n for n in names if n.lower().endswith(".csv")]
    if not csvs:
        raise ValueError(f"No .csv member in {archive or 'archive'}; members: {names}")
    if member:
        hits = [n for n in csvs if member.lower() in n.lower()]
        criterion = f"member substring {member!r}"
    elif resolution_m is not None:
        token = resolution_token(resolution_m)
        hits = [n for n in csvs
                if re.search(rf"(?<![0-9]){re.escape(token)}\b", n, re.IGNORECASE)]
        criterion = f"resolution {token}"
    else:
        hits, criterion = csvs, "the only .csv"
    if len(hits) != 1:
        raise ValueError(
            f"{criterion} selects {len(hits)} of {len(csvs)} CSVs in "
            f"{archive or 'the archive'} — expected exactly 1. A Zensus zip "
            f"bundles 10 km / 1 km / 100 m grids, so set sources.ses.resolution_m "
            f"(or sources.ses.members.<layer>) to disambiguate. Candidates: {csvs}"
        )
    return hits[0]


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


def load_inspire_csv_zip(path: Path, value_columns: list[str] | None = None,
                         *, member: str | None = None,
                         resolution_m: float | None = None) -> pd.DataFrame:
    """Load a Zensus-2022-style INSPIRE grid CSV (semicolon-separated, German
    decimal commas) from a zip. Returns a frame with x, y (EPSG:3035 cell
    centroids) plus the value columns, and ``attrs["resolution_m"]`` set to the
    grid resolution read off the file itself — which is what
    :func:`join_ses_to_cells` keys on, so the join follows the data rather than
    a config promise.

    The member is chosen by :func:`select_grid_member` (explicit ``member``
    substring, else ``resolution_m``); a multi-resolution archive with neither
    raises. When ``resolution_m`` is given it is also cross-checked against the
    resolution the loaded file's own coordinate columns declare, so selecting
    the wrong grid can never pass silently.
    """
    with zipfile.ZipFile(path) as zf:
        name = select_grid_member(zf.namelist(), member=member,
                                  resolution_m=resolution_m,
                                  archive=str(path))
        with zf.open(name) as fh:
            df = pd.read_csv(fh, sep=";", decimal=",", low_memory=False)
    xcol = next(c for c in df.columns if c.lower().startswith("x_mp"))
    ycol = next(c for c in df.columns if c.lower().startswith("y_mp"))
    # The coordinate column carries the grid it belongs to (`x_mp_100m`), as
    # does the id column (`GITTER_ID_100m`) — trust the FILE over the config.
    found = _token_resolution_m(xcol) or next(
        (_token_resolution_m(c) for c in df.columns
         if c.upper().startswith("GITTER") and _token_resolution_m(c)), None)
    if resolution_m is not None and found is not None and found != float(resolution_m):
        raise ValueError(
            f"{path.name}:{name} is a {resolution_token(found)} grid "
            f"(column '{xcol}') but sources.ses declares "
            f"{resolution_token(resolution_m)} — joining it would silently "
            f"produce empty ses_ columns. Fix the resolution or the member.")
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
    out.attrs["resolution_m"] = float(found or resolution_m or 100.0)
    out.attrs["member"] = name
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


def _grid_key(x: pd.Series, y: pd.Series, resolution_m: float) -> pd.Series:
    """Index of the ``resolution_m`` EPSG:3035 grid cell containing each point
    (INSPIRE convention: layer coordinates are cell CENTRES, so flooring the
    centre by the resolution recovers the cell)."""
    ix = (x // resolution_m).astype("int64").astype(str)
    iy = (y // resolution_m).astype("int64").astype(str)
    return ix + "_" + iy


def join_ses_to_cells(
    cells: pd.DataFrame,
    layers: dict[str, pd.DataFrame],
    *,
    resolution_m: float = 100.0,
    resolutions: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Join SES / demographic layers onto the GHS analysis cells by snapping
    both sides to the same EPSG:3035 grid cell.

    Layers do not all share the analysis grid's resolution: the national fine
    grids are 100 m (DE Zensus) or 200 m (FR Filosofi), while the EU-harmonised
    census 2021 grid is 1 km. Each layer is therefore keyed on ITS OWN grid —
    ``resolutions[name]``, else the layer frame's ``attrs["resolution_m"]``,
    else ``resolution_m`` — and a coarser layer is **broadcast**: every 100 m
    analysis cell inside one coarse cell receives the same value. That is a
    real limitation, not a rounding detail: a 1 km census share carries no
    within-kilometre variation, so it is a neighbourhood attribute of the cell
    (exactly like the Tier-2 ownership/vacancy covariates), and cross-city
    comparisons must not read it as 100 m detail. The resolution actually used
    per layer is returned by :func:`ses_join_resolutions` for the provenance
    sidecar.

    An analysis cell with no covering layer cell gets NaN — never a nearest
    neighbour's value.
    """
    out = cells.copy()
    for name, layer in layers.items():
        res = float(_layer_resolution(name, layer, resolution_m, resolutions))
        key = _grid_key(out["x"], out["y"], res)
        lkey = _grid_key(layer["x"], layer["y"], res)
        values = layer.drop(columns=["x", "y"]).set_index(lkey)
        values = values[~values.index.duplicated(keep="first")]
        joined = values.reindex(key)
        matched = float(joined.notna().any(axis=1).mean()) if len(joined) else 0.0
        if matched == 0.0:
            # Every join key missed. The usual cause is a resolution mismatch
            # (a 1 km member keyed on the 100 m grid), and the symptom used to
            # be an all-NaN covariate that quietly dropped out of the
            # regressions and produced an empty vulnerability stratum.
            print(f"WARNING: SES layer '{name}' matched NO analysis cell at "
                  f"{res:g} m resolution (member "
                  f"{layer.attrs.get('member', '?')}) — the resulting ses_"
                  f"{name}* columns are entirely empty; check the layer's grid "
                  f"resolution.")
        elif matched < 0.5:
            print(f"NOTE: SES layer '{name}' covers {matched:.1%} of analysis "
                  f"cells at {res:g} m (suppression or partial extent).")
        for col in values.columns:
            out[f"ses_{name}_{col}" if len(values.columns) > 1 else f"ses_{name}"] = (
                joined[col].to_numpy()
            )
    return out


def _layer_resolution(name: str, layer: pd.DataFrame, default: float,
                      resolutions: dict[str, float] | None) -> float:
    if resolutions and name in resolutions:
        return resolutions[name]
    return float(layer.attrs.get("resolution_m", default))


def ses_join_resolutions(
    layers: dict[str, pd.DataFrame],
    *,
    resolution_m: float = 100.0,
    resolutions: dict[str, float] | None = None,
) -> dict[str, dict]:
    """Per-layer join provenance: the grid resolution each layer was keyed on
    and the ``ses_*`` columns it produced. Written beside ``cells.parquet`` so
    a downstream reader can tell a 100 m covariate from a broadcast 1 km one."""
    out = {}
    for name, layer in layers.items():
        cols = [c for c in layer.columns if c not in ("x", "y")]
        prefix = f"ses_{name}"
        res = float(_layer_resolution(name, layer, resolution_m, resolutions))
        out[name] = {
            "resolution_m": res,
            "columns": [f"{prefix}_{c}" for c in cols] if len(cols) > 1 else [prefix],
            # Coarser than the 100 m analysis grid -> the value is replicated
            # over every analysis cell inside it (no within-cell variation).
            "broadcast_to_analysis_grid": res > 100.0,
        }
    return out
