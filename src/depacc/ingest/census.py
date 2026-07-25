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


def _norm(name: str) -> str:
    """Normalise a column / layer name for code matching: upper case, '-' and
    '.' unified to '_'."""
    return re.sub(r"[-.\s]+", "_", str(name).strip()).upper()


def code_matches(name: str, code: str) -> bool:
    """Does ``name`` carry the census variable ``code``?

    GISCO wraps the Reg. 2018/1799 codes: total population arrives as the column
    ``OBS_VALUE_T`` and (in the per-variable distributions) as members/layers
    like ``ESTAT_OBS-VALUE-Y_LT15_2021_V1-0``. So a code matches its own name, a
    trailing ``_<CODE>``, or an embedded ``_<CODE>_`` — never a partial word, so
    ``T`` does not match ``Y_LT15``.
    """
    n, c = _norm(name), _norm(code)
    return n == c or n.endswith(f"_{c}") or f"_{c}_" in n


def _resolve_columns(wanted: list[str], available: list[str]) -> dict[str, str]:
    """Map configured variable codes onto the file's actual column names.

    Exact (case-insensitive) matches win; otherwise the GISCO ``OBS_VALUE_*``
    wrapping is unwrapped via :func:`code_matches`. A code matching several
    columns is reported and skipped rather than silently taking one. Absent
    codes are simply missing from the result — that is how a share whose
    variables this file does not publish gets skipped.
    """
    lookup = {c.lower(): c for c in available}
    out: dict[str, str] = {}
    for code in wanted:
        if code.lower() in lookup:
            out[code] = lookup[code.lower()]
            continue
        hits = [c for c in available if code_matches(c, code)]
        if len(hits) == 1:
            out[code] = hits[0]
        elif len(hits) > 1:
            print(f"WARNING: census code '{code}' matches {hits} — skipping it; "
                  f"name the column exactly in sources.census.shares")
    return out


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


def list_geo_layers(path: Path) -> list[str]:
    """Layer names in a GeoPackage, or ``[]`` if they cannot be enumerated.

    A GeoPackage can hold one layer per census variable, in which case reading
    the driver's default (first) layer yields only that variable — which is
    exactly how the first run came back with nothing but ``OBS_VALUE_T``.
    """
    try:
        import pyogrio

        return [str(n) for n in pyogrio.list_layers(path)[:, 0]]
    except Exception:  # pyogrio absent or unreadable schema
        try:
            import fiona

            return list(fiona.listlayers(str(path)))
        except Exception:
            return []


def _read_geo_layer(path: Path, layer: str | None, padded, label: str):
    import geopandas as gpd

    if path.suffix.lower() in (".parquet", ".geoparquet"):
        try:
            return gpd.read_parquet(path)
        except (ValueError, KeyError):  # plain (non-geo) parquet
            return pd.read_parquet(path)
    kwargs = {"layer": layer} if layer else {}
    try:
        frame = gpd.read_file(path, bbox=padded, **kwargs)
    except (TypeError, ValueError) as err:
        print(f"NOTE: bbox-filtered read unavailable for {label} ({err}); "
              f"reading the whole layer and clipping afterwards")
        frame = gpd.read_file(path, **kwargs)
    if getattr(frame, "crs", None) is not None and frame.crs.to_epsg() != 3035:
        # The dataset is EPSG:3035, matching the analysis CRS and the bbox; a
        # re-versioned release in another CRS is reprojected rather than trusted.
        frame = frame.to_crs("EPSG:3035")
    return frame


def _load_census_geo(path: Path, *, bbox, columns, id_column, layer: str | None,
                     pad_m: float) -> pd.DataFrame:
    """Load a GeoPackage / (Geo)Parquet census table as cell centroids.

    Two published shapes are handled. A **wide** table carries every variable as
    a column of one layer. A **per-variable** GeoPackage carries one layer per
    variable (each just the grid id plus its own ``OBS_VALUE_*``); those layers
    are read individually — only the ones a configured share actually needs —
    and merged on the cell centroid. Reads are bbox-filtered through the layer's
    spatial index where the driver supports it, with a read-all-then-clip
    fallback for older stacks.
    """
    padded = None if bbox is None else (bbox[0] - pad_m, bbox[1] - pad_m,
                                        bbox[2] + pad_m, bbox[3] + pad_m)
    available_layers = [] if path.suffix.lower() != ".gpkg" else list_geo_layers(path)
    if available_layers:
        print(f"census: {len(available_layers)} layer(s) in {path.name}: "
              f"{available_layers}")

    # Which layers to read: the configured one, else those matching a wanted
    # code, else the default layer.
    targets: list[tuple[str | None, str | None]] = [(layer, None)]
    if layer is None and len(available_layers) > 1 and columns:
        matched = [(lyr, code) for code in columns
                   for lyr in available_layers if code_matches(lyr, code)]
        if matched:
            targets = matched
            print(f"census: per-variable layers matched "
                  f"{[(c, lyr) for lyr, c in matched]}")
        else:
            print(f"WARNING: none of the requested codes {sorted(columns)} names "
                  f"a layer of {path.name}; reading its default layer only")

    frames: list[pd.DataFrame] = []
    for target_layer, code in targets:
        label = f"{path.name}:{target_layer}" if target_layer else path.name
        frame = _read_geo_layer(path, target_layer, padded, label)
        geometry = getattr(frame, "geometry", None)
        # A per-variable layer holds exactly one value column, whose name is the
        # wrapped code (OBS_VALUE_T); ask for that code alone and let
        # _resolve_columns unwrap it.
        want = [code] if code else columns
        resolved = _select_value_columns(frame, want, id_column, label)
        if not resolved:
            continue
        values = frame[list(resolved.values())].apply(pd.to_numeric, errors="coerce")
        block = pd.concat(
            [_cell_coordinates(frame, id_column, label, geometry), values], axis=1)
        frames.append(_clip(block, bbox, pad_m).rename(
            columns={v: k for k, v in resolved.items()}).reset_index(drop=True))

    if not frames:
        return pd.DataFrame(columns=["x", "y"])
    out = frames[0]
    for extra in frames[1:]:
        out = out.merge(extra, on=["x", "y"], how="outer")
    return out.reset_index(drop=True)


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


def fetch_census_grid(cfg: dict, root: Path) -> dict[str, Path]:
    """Download the configured census-grid file(s) (cached, provenance-logged).

    ``sources.census.url`` fetches one archive holding the grid;
    ``sources.census.urls`` is a ``{variable code: url}`` mapping for the
    per-variable distributions, mirroring how ``sources.ses.urls`` already
    works — the frames are merged on the cell centroid downstream. Both may be
    set: the wide archive plus extra per-variable files it does not carry.

    Returns ``{label: path}``, empty — with a warning, never an exception — when
    nothing is configured or every download fails, so a stale upstream URL
    degrades one city's covariates instead of killing an all-city batch run.
    """
    census = (cfg.get("sources", {}) or {}).get("census") or {}
    wanted: dict[str, str] = {}
    if census.get("url"):
        wanted["grid"] = census["url"]
    wanted.update(census.get("urls") or {})
    if not wanted:
        print("NOTE: no sources.census.url / .urls configured; skipping the EU "
              "census 1 km demographics layer")
        return {}
    raw = root / cfg["output"]["raw_root"] / "census"
    out: dict[str, Path] = {}
    for label, url in wanted.items():
        name = (census.get("filename") if label == "grid" else None) \
            or url.rsplit("/", 1)[-1]
        try:
            out[label] = download(url, raw / name,
                                  licence=census.get("licence", ""),
                                  note=str(census.get("provider", "")))
        except (OSError, ValueError) as err:
            # A moved GISCO release (404) or a network failure degrades ONE
            # city's covariates; it must not kill an all-city batch. requests'
            # exceptions are OSError subclasses, so HTTP errors and timeouts
            # both land here.
            print(f"WARNING: census download failed for '{label}' ({url}): "
                  f"{err}; continuing without it")
    return out


def census_layer(cfg: dict, root: Path, fua) -> pd.DataFrame | None:
    """The joinable EU census layer for one city: fetch, clip to the FUA,
    derive the vulnerability shares, and return ``x``/``y`` plus the share
    columns (raw counts are dropped — the equity stage wants shares, and the
    population count already comes from GHS-POP).

    ``None`` means "not available for this city" (no URL, failed download, or
    no census cell overlapping the FUA) and is a warning, not an error.
    """
    census = (cfg.get("sources", {}) or {}).get("census") or {}
    paths = fetch_census_grid(cfg, root)
    if not paths:
        return None
    shares = census.get("shares") or {}
    keep = sorted({c for entry in shares.values()
                   for c in (entry.get("numerator") or [])
                   + (entry.get("denominator") or [])})
    bbox = tuple(fua.total_bounds) if fua is not None else None
    unpack = root / cfg["output"].get("cache_root", "data/cache") / "census"
    # One frame per configured source, merged on the cell centroid: a wide
    # release contributes every variable at once, a per-variable release one
    # each, and a mix of the two works without special-casing.
    frames = []
    for label, path in paths.items():
        grid = load_census_grid(
            path, bbox=bbox, columns=keep or None,
            id_column=str(census.get("id_column", "GRD_ID")),
            member=census.get("member"), layer=census.get("layer"),
            # Unpack under the cache root, never the workflow-cached data/raw.
            unpack_dir=unpack,
        )
        if grid.empty or list(grid.columns) == ["x", "y"]:
            print(f"NOTE: census source '{label}' contributed no usable cells "
                  f"over the FUA")
            continue
        frames.append(grid)
    if not frames:
        print("WARNING: no census 1 km cells overlap the FUA; skipping the "
              "EU census demographics layer")
        return None
    grid = frames[0]
    for extra in frames[1:]:
        grid = grid.merge(extra, on=["x", "y"], how="outer")
    derived = share_columns(grid, shares)
    share_cols = [c for c in shares if c in derived.columns]
    if not share_cols:
        print(f"WARNING: no census shares could be derived from "
              f"{sorted(paths)}; the loaded variables were "
              f"{[c for c in grid.columns if c not in ('x', 'y')]}. Correct "
              f"sources.census.shares (or add per-variable sources.census.urls) "
              f"to match what the release publishes; skipping the layer.")
        return None
    out = derived[["x", "y", *share_cols]]
    print(f"census 1 km grid: {len(out)} cells over the FUA, "
          f"shares {share_cols}")
    return out
