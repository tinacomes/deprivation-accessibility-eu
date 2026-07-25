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
* **Column codes.** Everything about the published file — its URL, the CSV
  member inside the archive, the id column and the variable codes — comes from
  ``sources.census`` in the config, never from this module. Shares whose source
  columns are absent from the file are skipped with a warning (this is what
  makes "foreign-born share *where published*" work), and the loaded column
  list is printed so a first run tells you precisely what to correct.
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


def _csv_member(zf: zipfile.ZipFile, member: str | None) -> str:
    """Pick the CSV inside the archive: the configured ``member`` (substring
    match) or, failing that, the largest .csv — GISCO archives bundle small
    metadata/lookup CSVs alongside the data table."""
    csvs = [i for i in zf.infolist() if i.filename.lower().endswith(".csv")]
    if not csvs:
        raise ValueError(f"No .csv member in {zf.filename}; "
                         f"members: {[i.filename for i in zf.infolist()]}")
    if member:
        hits = [i for i in csvs if member.lower() in i.filename.lower()]
        if not hits:
            raise ValueError(
                f"sources.census.member '{member}' matches no .csv in "
                f"{zf.filename}; members: {[i.filename for i in csvs]}")
        csvs = hits
    return max(csvs, key=lambda i: i.file_size).filename


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


def load_census_grid(
    path: Path,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    columns: list[str] | None = None,
    id_column: str = "GRD_ID",
    member: str | None = None,
    chunksize: int = 500_000,
    pad_m: float = 2000.0,
) -> pd.DataFrame:
    """Load the census grid CSV (plain or inside a zip) as cell centroids.

    The published table is continental (millions of rows), so it is read in
    chunks and clipped to ``bbox`` (minx, miny, maxx, maxy in the grid's CRS,
    padded by ``pad_m`` so cells straddling the FUA edge survive) before
    anything is concatenated. Returns ``x``, ``y`` plus the requested value
    columns coerced to numeric (Eurostat's ':' confidentiality marker and any
    other non-numeric flag become NaN).
    """
    path = Path(path)
    is_zip = zipfile.is_zipfile(path)

    def _open():
        if is_zip:
            zf = zipfile.ZipFile(path)
            return zf, zf.open(_csv_member(zf, member))
        return None, open(path, "rb")

    zf, fh = _open()
    try:
        sep = _sniff_sep(fh.readline())
    finally:
        fh.close()
        if zf is not None:
            zf.close()

    zf, fh = _open()
    frames: list[pd.DataFrame] = []
    resolved: dict[str, str] = {}
    seen: list[str] = []
    try:
        reader = pd.read_csv(fh, sep=sep, chunksize=chunksize,
                             dtype=str, low_memory=False)
        for chunk in reader:
            if not seen:
                seen = list(chunk.columns)
                id_col = _resolve_columns([id_column], seen).get(id_column)
                if id_col is None:
                    raise ValueError(
                        f"census id column '{id_column}' not in {path.name}; "
                        f"columns: {seen}")
                wanted = columns if columns is not None else [
                    c for c in seen if c != id_col]
                resolved = _resolve_columns(wanted, seen)
                missing = sorted(set(wanted) - set(resolved))
                if missing:
                    print(f"WARNING: census columns absent from "
                          f"{path.name}: {missing}")
            geo = parse_grid_id(chunk[id_col])
            block = pd.concat(
                [geo[["x", "y"]],
                 chunk[list(resolved.values())].apply(pd.to_numeric,
                                                      errors="coerce")],
                axis=1,
            )
            block = block[block.x.notna() & block.y.notna()]
            if bbox is not None:
                minx, miny, maxx, maxy = bbox
                block = block[block.x.between(minx - pad_m, maxx + pad_m)
                              & block.y.between(miny - pad_m, maxy + pad_m)]
            if not block.empty:
                frames.append(block)
    finally:
        fh.close()
        if zf is not None:
            zf.close()

    print(f"census grid columns in {path.name}: {seen}")
    if not frames:
        return pd.DataFrame(columns=["x", "y", *resolved])
    out = pd.concat(frames, ignore_index=True)
    # Config codes, not the file's casing, name the columns downstream. NB the
    # census code for total population is literally "T", which collides with
    # DataFrame.T — always subscript these columns, never attribute-access them.
    return out.rename(columns={v: k for k, v in resolved.items()})


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
        member=census.get("member"),
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
