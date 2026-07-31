"""OSM ingest: Geofabrik .pbf downloads and facility extraction.

Facilities are extracted per service from `config/services.yaml` tag rules
with pyrosm. Point features keep their coordinates; polygon features (e.g.
hospitals mapped as areas, parks) are represented by boundary access points
(vertices thinned to ~100 m spacing) so travel time is measured to the edge,
plus a representative point fallback. Capacity is parsed per the service's
capacity source (`beds` tag, polygon area, or uniform proxy — flagged).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from depacc.provenance import download

OSM_LICENCE = "ODbL 1.0 (© OpenStreetMap contributors)"

#: Geofabrik country extracts for `depacc make-city` (r5 needs a street
#: network; a generated Tier-1 config has no hand-picked regional extract).
#: A country file is 1-5 GB but is clipped to the FUA window with osmium
#: streaming before anything parses it, and cached per city. A hand-tuned
#: regional extract (see hamburg.yaml) is always the better substitute.
GEOFABRIK_COUNTRY = {
    "AT": "austria", "BE": "belgium", "BG": "bulgaria", "CH": "switzerland",
    "CZ": "czech-republic", "DE": "germany", "DK": "denmark", "EE": "estonia",
    "EL": "greece", "ES": "spain", "FI": "finland", "FR": "france",
    "HR": "croatia", "HU": "hungary", "IE": "ireland-and-northern-ireland",
    "IT": "italy", "LT": "lithuania", "LU": "luxembourg", "LV": "latvia",
    "NL": "netherlands", "NO": "norway", "PL": "poland", "PT": "portugal",
    "RO": "romania", "SE": "sweden", "SI": "slovenia", "SK": "slovakia",
    "UK": "great-britain",
}


def geofabrik_country_url(country: str) -> str | None:
    """Geofabrik download URL for a two-letter country code, or None when the
    country is not mapped (the caller should then ask for an explicit URL)."""
    slug = GEOFABRIK_COUNTRY.get(country.upper())
    return (f"https://download.geofabrik.de/europe/{slug}-latest.osm.pbf"
            if slug else None)


def fetch_pbfs(cfg: dict, root: Path) -> list[Path]:
    src = cfg["sources"]["osm_pbf"]
    raw = root / cfg["output"]["raw_root"] / "osm"
    urls = [src["url"], *src.get("extra_urls", [])]
    return [
        download(u, raw / Path(u).name, licence=src.get("licence", OSM_LICENCE))
        for u in urls
    ]


def clip_pbf(pbf: Path, bbox4326: tuple[float, float, float, float], out: Path) -> Path:
    """Clip an extract to the FUA bounding box with osmium-tool (streaming,
    low memory) BEFORE any parsing — state-level extracts (e.g. the 1.3 GB
    Niedersachsen file for Hamburg's commuting zone) otherwise exhaust RAM in
    pyrosm/R5. Falls back to the unclipped file when osmium is unavailable."""
    if out.exists():
        return out
    if shutil.which("osmium") is None:
        print(f"WARNING: osmium-tool not found; parsing FULL extract "
              f"{pbf.name} — install osmium-tool to avoid high memory use.",
              flush=True)
        return pbf
    minx, miny, maxx, maxy = bbox4326
    subprocess.run(
        ["osmium", "extract", "-b", f"{minx},{miny},{maxx},{maxy}",
         str(pbf), "-o", str(out), "--overwrite"],
        check=True,
    )
    print(f"clipped {pbf.name}: {pbf.stat().st_size >> 20} MB -> "
          f"{out.stat().st_size >> 20} MB", flush=True)
    return out


def merge_pbfs(pbfs: list[Path], out: Path) -> Path:
    """Merge extracts with osmium-tool when several cover the FUA. Falls back
    to the primary extract (with a warning) if osmium is unavailable."""
    if len(pbfs) == 1:
        return pbfs[0]
    if out.exists():
        return out
    if shutil.which("osmium") is None:
        print("WARNING: osmium-tool not found; routing network restricted to "
              f"the primary extract {pbfs[0].name}. Install osmium-tool to "
              "cover the whole FUA.")
        return pbfs[0]
    subprocess.run(
        ["osmium", "merge", *map(str, pbfs), "-o", str(out), "--overwrite"],
        check=True,
    )
    return out


def _thin_boundary_points(geom, spacing_m: float = 100.0):
    """Access points along a polygon boundary at ~spacing_m intervals
    (computed in the geometry's CRS units; call in a projected CRS)."""
    boundary = geom.boundary
    n = max(int(boundary.length // spacing_m), 1)
    return [boundary.interpolate(i / n, normalized=True) for i in range(n)]


def _capacity(row: pd.Series, spec: dict, area: float | None) -> float:
    source = spec.get("capacity", {}).get("source", "uniform")
    if source == "beds":
        tag = spec["capacity"].get("tag", "beds")
        val = row.get(tag)
        try:
            return float(str(val).split(";")[0])
        except (TypeError, ValueError):
            return 1.0  # fallback proxy, flagged via capacity_proxy column
    if source == "area_m2" and area is not None:
        return float(area)
    return 1.0


def _matches(gdf, rule: dict):
    m = gdf.get(rule["key"])
    if m is None:
        return pd.Series(False, index=gdf.index)
    mask = m == rule["value"]
    req = rule.get("require")
    if req is not None:
        r = gdf.get(req["key"])
        mask &= (r == req["value"]) if r is not None else False
    return mask.fillna(False)


def extract_facilities(pbfs: list[Path], services: dict, cfg: dict, fua) -> dict[str, pd.DataFrame]:
    """Extract facilities per service from the extracts, clipped to the FUA.

    Returns {service: DataFrame[dest_id, lon, lat, x, y, capacity,
    capacity_proxy]} in analysis CRS + WGS84.
    """
    import geopandas as gpd
    from pyrosm import OSM

    analysis_crs = cfg["crs"]["analysis"]
    local_crs = cfg["crs"].get("local") or analysis_crs
    fua_wgs = fua.to_crs("EPSG:4326")
    keys = sorted({r["key"] for s in services.values() for r in s["osm"]}
                  | {r.get("require", {}).get("key") for s in services.values()
                     for r in s["osm"] if r.get("require")}
                  | {s.get("capacity", {}).get("tag") for s in services.values()
                     if s.get("capacity", {}).get("source") == "beds"})
    keys = [k for k in keys if k]

    per_service: dict[str, list[pd.DataFrame]] = {s: [] for s in services}
    for pbf in pbfs:
        osm = OSM(str(pbf))
        custom = {r["key"]: True for s in services.values() for r in s["osm"]}
        gdf = osm.get_data_by_custom_criteria(
            custom_filter=custom, keep_nodes=True, keep_ways=True,
            keep_relations=True, extra_attributes=keys,
        )
        if gdf is None or gdf.empty:
            continue
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        gdf = gdf[gdf.intersects(fua_wgs.union_all())]
        for name, spec in services.items():
            mask = pd.Series(False, index=gdf.index)
            for rule in spec["osm"]:
                mask |= _matches(gdf, rule)
            hits = gdf[mask]
            if hits.empty and spec.get("fallback_osm"):
                fmask = pd.Series(False, index=gdf.index)
                for rule in spec["fallback_osm"]:
                    fmask |= _matches(gdf, rule)
                hits = gdf[fmask]
            if hits.empty:
                continue
            per_service[name].append(_to_points(hits, spec, local_crs, analysis_crs))

    out = {}
    for name, frames in per_service.items():
        if not frames:
            out[name] = pd.DataFrame(
                columns=["dest_id", "lon", "lat", "x", "y", "capacity", "capacity_proxy"]
            )
            continue
        fac = pd.concat(frames, ignore_index=True)
        # De-duplicate across overlapping extracts.
        fac = fac.drop_duplicates(subset=["lon", "lat"]).reset_index(drop=True)
        fac["dest_id"] = [f"{name}_{i}" for i in range(len(fac))]
        out[name] = fac
    return out


def _to_points(hits, spec: dict, local_crs: str, analysis_crs: str) -> pd.DataFrame:
    """Point + boundary-access-point representation with capacity columns."""
    import geopandas as gpd
    from shapely.geometry import Point

    min_area = spec.get("min_area_m2")
    local = hits.to_crs(local_crs)
    rows = []
    for (_, row), geom_l in zip(hits.iterrows(), local.geometry):
        area = None
        if geom_l.geom_type in ("Polygon", "MultiPolygon"):
            area = geom_l.area
            if min_area and area < min_area:
                continue
            points_l = _thin_boundary_points(geom_l)
        else:
            points_l = [geom_l if isinstance(geom_l, Point) else geom_l.representative_point()]
        cap = _capacity(row, spec, area)
        proxy = bool(spec.get("capacity", {}).get("proxy", True))
        # A polygon's capacity is shared over its access points so 2SFCA
        # supply is not multiplied by the number of entrances.
        share = cap / len(points_l)
        for p in points_l:
            rows.append({"geometry": p, "capacity": share, "capacity_proxy": proxy})
    if not rows:
        return pd.DataFrame(columns=["lon", "lat", "x", "y", "capacity", "capacity_proxy"])
    g = gpd.GeoDataFrame(rows, crs=local_crs)
    wgs = g.to_crs("EPSG:4326")
    ana = g.to_crs(analysis_crs)
    return pd.DataFrame({
        "lon": wgs.geometry.x, "lat": wgs.geometry.y,
        "x": ana.geometry.x, "y": ana.geometry.y,
        "capacity": g["capacity"], "capacity_proxy": g["capacity_proxy"],
    })
