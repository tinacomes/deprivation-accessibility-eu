"""EU-harmonised demographics: Eurostat Census 2021 1 km grid (Tier 1, all cities).

This is the layer that makes population vulnerability available for EVERY city
in the sample, not just the Tier-2 cities with a fine national SES grid
(``ingest/ses.py``). It is the demographics source already declared for Tier 1
in ``config/defaults.yaml`` (``tiers.tier1.demographics:
eurostat_census_2021_1km``).

What it is: the 2021 population-and-housing census aggregated by the national
statistical institutes onto the EU-wide 1 km² INSPIRE grid and published by
GISCO in EPSG:3035, with the 13 variables of EU Regulation 2018/1799 — total
population, sex, broad age (under 15 / 15-64 / 65 and over), current activity
status (employed persons, voluntary), country of birth, and place of usual
residence one year before the census. We derive the vulnerability *shares* the
equity stage consumes (share < 15, share >= 65, employment share, foreign-born
share where published) and prefix them ``ses_census_*`` so they flow into
``equity/pipeline.py`` like any other SES column.

Two things to keep honest about this layer:

* **Resolution.** The census grid is 1 km while the analysis grid (GHS-POP) is
  100 m, so a joined value is *broadcast*: every 100 m cell inside a 1 km cell
  inherits the same value. Within-kilometre variation in age/employment is
  therefore absent by construction — the shares are a neighbourhood attribute
  of the cell, exactly like the Tier-2 ownership/vacancy covariates. The
  broadcast happens in :func:`depacc.ingest.ses.join_ses_to_cells` (see its
  ``resolutions`` argument) and the per-layer grid resolution is recorded in
  ``ses_resolutions.json`` next to ``cells.parquet``.
* **Column codes.** Everything about the published file — its URL, the member
  inside the archive, the id column and the variable codes — comes from
  ``sources.census`` in the config, never from this module. Shares whose source
  columns are absent from the file are skipped with a warning (this is what
  makes "foreign-born share *where published*" work), and the loaded column
  list is printed so a first run tells you precisely what to correct.

The v1.0 release archive (verified by download) contains::

    CENSUS_INS21ES_A_IT_2021_0000_TOTAL _POPULATION.zip   nested INSPIRE delivery
    ESMS_Census_Grid 2021.pdf                             metadata
    ESTAT_Census_2021_V1-0.gpkg                           <- the attribute table
    ESTAT_OBS-VALUE-T_2021_V1-0.tiff                      total-population raster
    read.me

so the tabular data is a **GeoPackage**, not a CSV. :func:`_data_member` picks
it by extension preference (``.gpkg`` > ``.geoparquet``/``.parquet`` > ``.csv``,
never the raster or the docs), extracts it once beside the archive, and
:func:`_load_census_geo` reads it bbox-filtered through the layer's spatial
index. The CSV path is kept because the landing page also advertises CSV and
GeoParquet distributions, and a later release may reorganise.
"""

from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path

import pandas as pd

from depacc.provenance import download

# INSPIRE grid cell identifier, both spellings GISCO publishes:
#   "CRS3035RES1000mN2696000E4341000"  (resolution + coordinates in metres)
#   "1kmN2696E4341"                    (resolution + coordinates in km units)
# N/E always reference the cell's LOWER-LEFT corner, so the centroid is the
# corner plus half a cell (the same convention the Zensus x_mp/y_mp columns
# already express explicitly).
GRID_ID_RE = re.compile(
    r"(?:CRS(?P<crs>\d+))?(?:RES)?(?P<res>\d+)(?P<unit>km|m)"
    r"N(?P<n>-?\d+)E(?P<e>-?\d+)",
    re.IGNORECASE,
)


def parse_grid_id(ids: pd.Series) -> pd.DataFrame:
    """Parse INSPIRE grid ids into cell-CENTRE coordinates.

    Returns a frame with ``x``, ``y`` (centroids, in the CRS the ids are
    expressed in — EPSG:3035 for the GISCO grids) and ``resolution_m``.
    Unparseable ids yield NaN rather than raising, so one malformed row cannot
    void a continental file.
    """
    parts = ids.astype(str).str.extract(GRID_ID_RE)
    if parts["n"].isna().all():
        raise ValueError(
            f"No INSPIRE grid id parsed from column values like "
            f"{ids.iloc[0] if len(ids) else '<empty>'!r}; expected e.g. "
            f"'CRS3035RES1000mN2696000E4341000' or '1kmN2696E4341'"
        )
    # 'km' ids express BOTH the resolution and the coordinates in km units.
    factor = parts["unit"].str.lower().map({"km": 1000.0, "m": 1.0})
    res = pd.to_numeric(parts["res"], errors="coerce") * factor
    east = pd.to_numeric(parts["e"], errors="coerce") * factor
    north = pd.to_numeric(parts["n"], errors="coerce") * factor
    return pd.DataFrame(
        {"x": east + res / 2.0, "y": north + res / 2.0, "resolution_m": res},
        index=ids.index,
    )


# Readable data members of a GISCO census archive, most preferred first. The
# v1.0 release ships a GeoPackage (plus a total-population GeoTIFF, the ESMS
# metadata PDF, a read.me and a nested INSPIRE country delivery — none of them
# the attribute table), while the landing page also advertises CSV and
# GeoParquet; all three tabular forms are handled.
DATA_EXTENSIONS = (".gpkg", ".geoparquet", ".parquet", ".csv")


def _data_member(zf: zipfile.ZipFile, member: str | None) -> str:
    """Pick the tabular data member of the archive.

    ``member`` (a case-insensitive substring) wins; otherwise the first
    extension in :data:`DATA_EXTENSIONS` that is present, largest file of that
    kind — GISCO archives bundle small metadata/lookup tables beside the data.
    Raster and documentation members are never candidates.
    """
    infos = zf.infolist()
    listing = [i.filename for i in infos]
    if member:
        hits = [i for i in infos if member.lower() in i.filename.lower()]
        if not hits:
            raise ValueError(
                f"sources.census.member '{member}' matches nothing in "
                f"{zf.filename}; members: {listing}")
        return max(hits, key=lambda i: i.file_size).filename
    for ext in DATA_EXTENSIONS:
        hits = [i for i in infos if i.filename.lower().endswith(ext)]
        if hits:
            return max(hits, key=lambda i: i.file_size).filename
    raise ValueError(
        f"No readable census table ({', '.join(DATA_EXTENSIONS)}) in "
        f"{zf.filename}; members: {listing}. Set sources.census.member to name "
        f"one explicitly.")


def _extract_member(zf: zipfile.ZipFile, name: str, dest_dir: Path) -> Path:
    """Extract one archive member once and cache it beside the archive.

    GDAL can read a GeoPackage through /vsizip/, but only by random access into
    the compressed stream, which is punishing on a continental file. Extracting
    once keeps the reads cheap. Callers put ``dest_dir`` under the CACHE root,
    not ``data/raw``: the workflows cache ``data/raw`` wholesale per city, so an
    unpacked continental GeoPackage there would be stored once per city and
    could evict the far more expensive OSM extracts. Re-extracting per run is a
    single decompress; a lost .pbf cache is a re-download.
    """
    dest = dest_dir / Path(name).name
    if dest.exists() and dest.stat().st_size == zf.getinfo(name).file_size:
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with zf.open(name) as src, open(part, "wb") as fh:
        while chunk := src.read(1 << 20):
            fh.write(chunk)
    part.replace(dest)
    print(f"census: extracted {name} -> {dest} "
          f"({dest.stat().st_size / 1e6:.0f} MB)")
    return dest


def _sniff_sep(header: bytes) -> str:
    try:
        return csv.Sniffer().sniff(header.decode("utf-8", "replace"),
                                   delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def _resolve_columns(wanted: list[str], available: list[str]) -> dict[str, str]:
    """Map configured column codes onto the file's actual column names,
    case-insensitively (releases differ on ``Y_GE65`` vs ``y_ge65``). Absent
    codes are simply missing from the result."""
    lookup = {c.lower(): c for c in available}
    return {w: lookup[w.lower()] for w in wanted if w.lower() in lookup}


def _cell_coordinates(frame: pd.DataFrame, id_column: str, label: str,
                      geometry=None) -> pd.DataFrame:
    """Cell-centre x/y for a loaded census table.

    The INSPIRE ``GRD_ID`` is preferred over geometry: it is exact, needs no
    geometry engine, and is present in every published form. Geometry (a
    GeoPackage's cell polygons or points) is the fallback.
    """
    id_col = _resolve_columns([id_column], list(frame.columns)).get(id_column)
    if id_col is not None:
        return parse_grid_id(frame[id_col])[["x", "y"]]
    if geometry is not None:
        centres = geometry.representative_point()
        return pd.DataFrame({"x": centres.x.to_numpy(), "y": centres.y.to_numpy()},
                            index=frame.index)
    raise ValueError(
        f"census id column '{id_column}' not in {label} and no geometry to fall "
        f"back on; columns: {list(frame.columns)}")


def _select_value_columns(frame: pd.DataFrame, columns: list[str] | None,
                          id_column: str, label: str) -> dict[str, str]:
    available = [c for c in frame.columns if c != "geometry"]
    id_col = _resolve_columns([id_column], available).get(id_column)
    wanted = columns if columns is not None else [c for c in available if c != id_col]
    resolved = _resolve_columns(wanted, available)
    missing = sorted(set(wanted) - set(resolved))
    if missing:
        print(f"WARNING: census columns absent from {label}: {missing}")
    print(f"census grid columns in {label}: {available}")
    return resolved


def _clip(frame: pd.DataFrame, bbox, pad_m: float) -> pd.DataFrame:
    frame = frame[frame.x.notna() & frame.y.notna()]
    if bbox is None:
        return frame
    minx, miny, maxx, maxy = bbox
    return frame[frame.x.between(minx - pad_m, maxx + pad_m)
                 & frame.y.between(miny - pad_m, maxy + pad_m)]


def _load_census_csv(opener, label: str, *, bbox, columns, id_column,
                     chunksize: int, pad_m: float) -> pd.DataFrame:
    """Stream a census CSV in chunks, clipping each chunk before concatenating —
    the published table is continental (millions of rows)."""
    with opener() as fh:
        sep = _sniff_sep(fh.readline())
    frames: list[pd.DataFrame] = []
    resolved: dict[str, str] = {}
    with opener() as fh:
        for i, chunk in enumerate(pd.read_csv(fh, sep=sep, chunksize=chunksize,
                                              dtype=str, low_memory=False)):
            if i == 0:
                resolved = _select_value_columns(chunk, columns, id_column, label)
                if not _resolve_columns([id_column], list(chunk.columns)):
                    raise ValueError(
                        f"census id column '{id_column}' not in {label}; "
                        f"columns: {list(chunk.columns)}")
            block = pd.concat(
                [_cell_coordinates(chunk, id_column, label),
                 chunk[list(resolved.values())].apply(pd.to_numeric,
                                                      errors="coerce")],
                axis=1,
            )
            block = _clip(block, bbox, pad_m)
            if not block.empty:
                frames.append(block)
    if not frames:
        return pd.DataFrame(columns=["x", "y", *resolved])
    out = pd.concat(frames, ignore_index=True)
    return out.rename(columns={v: k for k, v in resolved.items()})


def _load_census_geo(path: Path, *, bbox, columns, id_column, layer: str | None,
                     pad_m: float) -> pd.DataFrame:
    """Load a GeoPackage / (Geo)Parquet census table as cell centroids.

    The v1.0 GISCO release ships the attribute table as
    ``ESTAT_Census_2021_V1-0.gpkg``. The read is bbox-filtered through the
    layer's spatial index where the driver supports it (pyogrio/fiona), with a
    read-everything-then-clip fallback so an older stack still works.
    """
    import geopandas as gpd

    label = path.name
    padded = None if bbox is None else (bbox[0] - pad_m, bbox[1] - pad_m,
                                        bbox[2] + pad_m, bbox[3] + pad_m)
    if path.suffix.lower() in (".parquet", ".geoparquet"):
        try:
            frame = gpd.read_parquet(path)
        except (ValueError, KeyError):  # plain (non-geo) parquet
            frame = pd.read_parquet(path)
    else:
        kwargs = {"layer": layer} if layer else {}
        try:
            frame = gpd.read_file(path, bbox=padded, **kwargs)
        except (TypeError, ValueError) as err:
            print(f"NOTE: bbox-filtered read unavailable ({err}); reading the "
                  f"whole census layer and clipping afterwards")
            frame = gpd.read_file(path, **kwargs)
    geometry = getattr(frame, "geometry", None)
    if geometry is not None and getattr(frame, "crs", None) is not None:
        # The dataset is EPSG:3035, matching the analysis CRS and the bbox; a
        # re-versioned release in another CRS is reprojected rather than trusted.
        if frame.crs.to_epsg() != 3035:
            frame = frame.to_crs("EPSG:3035")
            geometry = frame.geometry
    resolved = _select_value_columns(frame, columns, id_column, label)
    values = frame[list(resolved.values())].apply(pd.to_numeric, errors="coerce")
    out = pd.concat([_cell_coordinates(frame, id_column, label, geometry), values],
                    axis=1)
    return _clip(out, bbox, pad_m).rename(
        columns={v: k for k, v in resolved.items()}).reset_index(drop=True)


def load_census_grid(
    path: Path,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    columns: list[str] | None = None,
    id_column: str = "GRD_ID",
    member: str | None = None,
    layer: str | None = None,
    unpack_dir: Path | None = None,
    chunksize: int = 500_000,
    pad_m: float = 2000.0,
) -> pd.DataFrame:
    """Load the census grid table as cell centroids, whatever form it ships in.

    ``path`` may be the published zip (the data member is picked by
    :func:`_data_member` and, unless it is a CSV, extracted once into
    ``unpack_dir`` — the cache root, see :func:`_extract_member`) or an
    already-unpacked ``.gpkg`` / ``.parquet`` / ``.csv``.
    Everything is clipped to ``bbox`` — (minx, miny, maxx, maxy) in EPSG:3035,
    padded by ``pad_m`` so a 1 km cell straddling the FUA edge survives — and
    value columns are coerced to numeric, so Eurostat's ':' confidentiality
    marker and any other flag become NaN.

    NB the census code for total population is literally ``T``, which collides
    with ``DataFrame.T`` — always subscript these columns.
    """
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            name = _data_member(zf, member)
            print(f"census: reading '{name}' from {path.name}")
            if name.lower().endswith(".csv"):
                return _load_census_csv(
                    lambda: zipfile.ZipFile(path).open(name), f"{path.name}:{name}",
                    bbox=bbox, columns=columns, id_column=id_column,
                    chunksize=chunksize, pad_m=pad_m)
            data_path = _extract_member(
                zf, name, unpack_dir or path.parent / "unpacked")
    else:
        data_path = path
    if data_path.suffix.lower() == ".csv":
        return _load_census_csv(
            lambda: open(data_path, "rb"), data_path.name, bbox=bbox,
            columns=columns, id_column=id_column, chunksize=chunksize, pad_m=pad_m)
    return _load_census_geo(data_path, bbox=bbox, columns=columns,
                            id_column=id_column, layer=layer, pad_m=pad_m)


def share_columns(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Derive share columns from raw census counts.

    ``spec`` maps an output share name to
    ``{numerator: [cols], denominator: [cols]}`` — a list on both sides so a
    share can sum several published categories (foreign-born = born in another
    EU country + born elsewhere) and use its own denominator (the employment
    share belongs over the working-age population, not the total). A share
    whose numerator or denominator columns are absent is SKIPPED with a note:
    that is how "where published" is honoured for the voluntary variables.
    A non-positive or missing denominator yields NaN, never a division blow-up.
    """
    out = df.copy()
    for name, entry in (spec or {}).items():
        num = [c for c in (entry.get("numerator") or [])]
        den = [c for c in (entry.get("denominator") or [])]
        absent = sorted({c for c in num + den if c not in out.columns})
        if absent or not num or not den:
            print(f"NOTE: census share '{name}' skipped; columns absent: "
                  f"{absent or 'numerator/denominator not configured'}")
            continue
        # A suppressed category counts as zero so one missing band does not
        # void the whole share; the denominator must be genuinely present.
        numerator = out[num].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
        denominator = out[den].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        out[name] = numerator / denominator.where(denominator > 0)
    return out


def fetch_census_grid(cfg: dict, root: Path) -> Path | None:
    """Download the configured census-grid archive (cached, provenance-logged).

    Returns ``None`` — with a warning, never an exception — when no URL is
    configured or the download fails, so a stale upstream URL degrades one
    city's covariates instead of killing an all-city batch run.
    """
    census = (cfg.get("sources", {}) or {}).get("census") or {}
    url = census.get("url")
    if not url:
        print("NOTE: no sources.census.url configured; skipping the EU census "
              "1 km demographics layer")
        return None
    dest = (root / cfg["output"]["raw_root"] / "census"
            / (census.get("filename") or url.rsplit("/", 1)[-1]))
    try:
        return download(url, dest, licence=census.get("licence", ""),
                        note=str(census.get("provider", "")))
    except (OSError, ValueError) as err:
        # A moved GISCO release (404) or a network failure degrades ONE city's
        # covariates; it must not kill an all-city batch. requests' exceptions
        # are OSError subclasses, so this covers HTTP errors and timeouts.
        print(f"WARNING: census grid download failed ({url}): {err}; "
              f"continuing without the EU census demographics layer")
        return None


def census_layer(cfg: dict, root: Path, fua) -> pd.DataFrame | None:
    """The joinable EU census layer for one city: fetch, clip to the FUA,
    derive the vulnerability shares, and return ``x``/``y`` plus the share
    columns (raw counts are dropped — the equity stage wants shares, and the
    population count already comes from GHS-POP).

    ``None`` means "not available for this city" (no URL, failed download, or
    no census cell overlapping the FUA) and is a warning, not an error.
    """
    census = (cfg.get("sources", {}) or {}).get("census") or {}
    path = fetch_census_grid(cfg, root)
    if path is None:
        return None
    shares = census.get("shares") or {}
    keep = sorted({c for entry in shares.values()
                   for c in (entry.get("numerator") or [])
                   + (entry.get("denominator") or [])})
    bbox = tuple(fua.total_bounds) if fua is not None else None
    grid = load_census_grid(
        path, bbox=bbox, columns=keep or None,
        id_column=str(census.get("id_column", "GRD_ID")),
        member=census.get("member"), layer=census.get("layer"),
        # Unpack under the cache root, never under the workflow-cached data/raw.
        unpack_dir=root / cfg["output"].get("cache_root", "data/cache") / "census",
    )
    if grid.empty:
        print("WARNING: no census 1 km cells overlap the FUA; skipping the "
              "EU census demographics layer")
        return None
    derived = share_columns(grid, shares)
    share_cols = [c for c in shares if c in derived.columns]
    if not share_cols:
        print("WARNING: no census shares could be derived; skipping the layer")
        return None
    out = derived[["x", "y", *share_cols]]
    print(f"census 1 km grid: {len(out)} cells over the FUA, "
          f"shares {share_cols}")
    return out
