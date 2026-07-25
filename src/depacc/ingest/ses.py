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
                         resolution_m: float | None = None,
                         bbox: tuple[float, float, float, float] | None = None,
                         pad_m: float = 1000.0,
                         chunksize: int = 500_000) -> pd.DataFrame:
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
        # These are NATIONAL grids — a Zensus theme is ~3.1 M rows for Germany,
        # of which a single FUA needs well under 1 %. Read in chunks and clip to
        # the FUA bbox (padded, so a cell on the boundary survives) so six themes
        # do not put ~18 M rows through memory for one city.
        with zf.open(name) as fh:
            reader = pd.read_csv(fh, sep=";", decimal=",", low_memory=False,
                                 chunksize=chunksize if bbox is not None else None)
            df = _read_clipped(reader, bbox, pad_m) if bbox is not None else reader
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
    keep = value_columns or [c for c in df.columns
                             if c not in (xcol, ycol) and not _is_annotation(c)]
    out = df[[xcol, ycol, *keep]].rename(columns={xcol: "x", ycol: "y"})
    for c in keep:
        out[c] = _parse_values(out[c], f"{path.name}:{name}", c)
    out.attrs["resolution_m"] = float(found or resolution_m or 100.0)
    out.attrs["member"] = name
    print(f"  {path.name}:{name} -> value columns {keep}")
    return out


# Destatis markers for a cell with no value: suppressed, zero-by-definition or
# not applicable. Not data, and not a format problem either.
_SUPPRESSION_MARKERS = frozenset(
    {"", "\u2013", "\u2014", "-", ".", "..", "...", "/", "x", "X",
     "nan", "None", "NaN"})


def _parse_values(series: pd.Series, label: str, column: str) -> pd.Series:
    """Numeric values of one theme column of a German-format INSPIRE CSV.

    ``read_csv(decimal=",")`` only converts a column it can parse ENTIRELY as
    numeric. A theme that marks suppressed cells with an en dash rather than
    leaving the field empty therefore arrives as a column of STRINGS, and
    ``pd.to_numeric("41,2")`` is NaN — so every value in it silently vanished.
    That is precisely what happened to the ownership-rate and vacancy-rate
    layers: they covered ~44 % of Hamburg's cells and carried not one value,
    while net-rent and household-size (whose suppressed cells are empty, so the
    column parsed as numeric on read) were fine.

    A string column is therefore normalised here — decimal comma to point, plus
    the decorations a rate column sometimes carries (percent sign, non-breaking
    or thin space) — and if it STILL yields nothing while holding non-marker
    text, the raw values are reported, so the format is identifiable from one run
    instead of inferred over several. Thousands separators are not expected in
    these machine-readable files; a value like "1.234,5" would fail and be
    reported rather than silently mis-parsed.
    """
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.astype(str).str.strip().fillna("")
    present = ~text.isin(_SUPPRESSION_MARKERS)
    parsed = pd.to_numeric(
        text.str.replace("\u00a0", "", regex=False)   # non-breaking space
            .str.replace("\u2009", "", regex=False)   # thin space
            .str.replace(" ", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False),       # German decimal comma
        errors="coerce")
    if not parsed.notna().any() and present.any():
        samples = text[present].unique()[:5].tolist()
        print(f"WARNING: {label} column '{column}' has {int(present.sum())} "
              f"non-empty values but NONE parse as numbers — the resulting ses_ "
              f"column would be entirely empty. Raw samples: {samples}")
    return parsed


def _read_clipped(reader, bbox: tuple[float, float, float, float],
                  pad_m: float) -> pd.DataFrame:
    """Concatenate a chunked INSPIRE CSV read, keeping only rows whose cell
    centroid falls in the padded ``bbox`` (EPSG:3035). An empty result keeps the
    columns, so the caller still sees the file's schema."""
    minx, miny, maxx, maxy = bbox
    kept, header = [], None
    for chunk in reader:
        if header is None:
            header = chunk.iloc[:0]
        xcol = next(c for c in chunk.columns if c.lower().startswith("x_mp"))
        ycol = next(c for c in chunk.columns if c.lower().startswith("y_mp"))
        x = pd.to_numeric(chunk[xcol], errors="coerce")
        y = pd.to_numeric(chunk[ycol], errors="coerce")
        block = chunk[x.between(minx - pad_m, maxx + pad_m)
                      & y.between(miny - pad_m, maxy + pad_m)]
        if not block.empty:
            kept.append(block)
    if not kept:
        return header if header is not None else pd.DataFrame()
    return pd.concat(kept, ignore_index=True)


def _is_annotation(column: str) -> bool:
    """Non-data columns of a Zensus theme file: the grid id and the
    ``werterlaeuternde_Zeichen`` annotation symbol explaining suppressed/zero
    values. Matched loosely — releases spell the annotation with and without
    the umlaut transliteration — so it never becomes an all-NaN ses_ column
    that pollutes the covariate set."""
    low = column.lower()
    return (column.upper().startswith("GITTER")
            or "werterl" in low
            or low.endswith("_zeichen"))


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
    (partition the whole population). A zero/NaN denominator yields NaN.

    Suppression is handled per ROW: a band that sums several published counts
    keeps its partial sum when some are withheld, but a band whose counts are
    ALL withheld yields NaN, never 0. This is not a nicety — Hamburg's configured
    bands are a single column each, so zero-filling put every suppressed cell at
    a share of 0.0, i.e. inside the LOW-vulnerability tail of the stratification
    rather than outside it.
    """
    out = df.copy()

    def _counts(cols: list[str]) -> pd.Series:
        # Suppressed ('–'/empty) cells parse to NaN. min_count=1 keeps a partial
        # sum across bands but returns NaN when every named count is missing.
        return out[cols].apply(pd.to_numeric, errors="coerce").sum(
            axis=1, min_count=1)

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

    Joined columns are ALWAYS named ``ses_<layer>_<column>``. The name must not
    depend on how many value columns a release happens to publish: when the
    suffix was conditional on that, dropping one annotation column silently
    renamed ``ses_net_rent_durchschnMieteQM`` to ``ses_net_rent``, breaking
    every config that referenced it.

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
        _report_join(name, layer, res, key, values, joined)
        for col in values.columns:
            out[f"ses_{name}_{col}"] = joined[col].to_numpy()
    return out


def _report_join(name: str, layer: pd.DataFrame, res: float, key: pd.Series,
                 values: pd.DataFrame, joined: pd.DataFrame) -> None:
    """Diagnose a join, keeping the two failure modes apart.

    A grid MISS (no layer cell covers the analysis cell) usually means a
    resolution or projection mismatch and is a bug; SUPPRESSION (the cell is
    covered but the value is withheld) is normal for the confidentiality-heavy
    themes and merely limits that covariate's support. Both used to look like a
    silently all-NaN column, so they are now reported separately with the value
    columns that were actually joined.
    """
    member = layer.attrs.get("member", "?")
    if values.empty or not len(joined):
        print(f"WARNING: SES layer '{name}' ({member}) contributed NO value "
              f"columns — every column was filtered as grid id / annotation. "
              f"Check the file's header.")
        return
    covered = float(key.isin(values.index).mean())
    with_value = float(joined.notna().any(axis=1).mean())
    cols = list(values.columns)
    if covered == 0.0:
        print(f"WARNING: SES layer '{name}' ({member}) covers NO analysis cell "
              f"at {res:g} m — not one join key matched, so ses_{name}_* is "
              f"entirely empty. This is a grid mismatch (resolution or CRS), "
              f"not suppression. Columns: {cols}")
    elif with_value == 0.0:
        print(f"WARNING: SES layer '{name}' ({member}) covers {covered:.1%} of "
              f"analysis cells at {res:g} m but every joined value is missing — "
              f"the theme is fully suppressed here, or {cols} parsed to NaN.")
    else:
        print(f"SES layer '{name}' joined: {covered:.1%} of analysis cells "
              f"covered, {with_value:.1%} carry a value at {res:g} m; "
              f"columns {cols}")
        # A layer that reaches the grid but loses most of its values there is the
        # in-between case the two branches above miss, and it is the one that
        # slipped through: Hamburg's vacancy rate covers 44.3 % of analysis cells
        # and carries a value on 2.6 %, yet still produced the largest everyday
        # gradient in equity_regressions.csv. Either 94 % of the covered cells are
        # genuinely suppressed — worth stating rather than inferring — or a second
        # parse problem is eating values the way the decimal comma did.
        if covered > 0.05 and with_value < 0.25 * covered:
            print(f"WARNING: SES layer '{name}' ({member}) keeps a value on only "
                  f"{with_value / covered:.1%} of the cells it covers. Check "
                  f"whether the release really suppresses that much before using "
                  f"{cols} as a covariate; equity.min_covariate_valid_share gates "
                  f"it downstream either way.")


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
        res = float(_layer_resolution(name, layer, resolution_m, resolutions))
        out[name] = {
            "resolution_m": res,
            "member": layer.attrs.get("member"),
            "columns": [f"ses_{name}_{c}" for c in cols],
            # Coarser than the 100 m analysis grid -> the value is replicated
            # over every analysis cell inside it (no within-cell variation).
            "broadcast_to_analysis_grid": res > 100.0,
        }
    return out
