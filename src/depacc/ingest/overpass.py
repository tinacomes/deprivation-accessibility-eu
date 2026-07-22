"""Facility extraction via the Overpass API — the light-weight bypass.

Instead of downloading country-scale .pbf extracts (hundreds of MB per
city), each service is fetched as one small Overpass query over the FUA
bounding box (typically a few hundred KB of JSON). This is the default for
the Tier-1 fast path; the pbf/pyrosm route remains for Tier-2 cities where
the .pbf is needed for R5 routing anyway.

Limitations vs the pbf route (documented in methods.md): polygon features
are reduced to their Overpass 'center' point (no boundary access points,
no min_area filter), so green-space access is measured to park centres.
At Tier-1's 1 km friction-surface resolution this is immaterial.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
# Mirrors tried in order when the primary endpoint refuses (406/429/504/5xx).
DEFAULT_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# A descriptive User-Agent is REQUIRED: the public Overpass endpoints reject
# the bare python-requests UA with 406 Not Acceptable.
HTTP_HEADERS = {
    "User-Agent": "depacc/0.1 (accessibility research; https://github.com/tinacomes/DisasterAI)",
    "Accept": "application/json",
}
OSM_LICENCE = "ODbL 1.0 (© OpenStreetMap contributors, via Overpass API)"


def _rule_clause(rule: dict) -> str:
    clause = f'["{rule["key"]}"="{rule["value"]}"]'
    req = rule.get("require")
    if req:
        clause += f'["{req["key"]}"="{req["value"]}"]'
    return clause


def build_query(rules: list[dict], bbox: tuple[float, float, float, float],
                timeout_s: int = 120) -> str:
    """Overpass QL for a service's tag rules within (south, west, north, east)."""
    s, w, n, e = bbox
    parts = []
    for rule in rules:
        clause = _rule_clause(rule)
        for element in ("node", "way", "relation"):
            parts.append(f"{element}{clause}({s},{w},{n},{e});")
    body = "".join(parts)
    return f"[out:json][timeout:{timeout_s}];({body});out tags center;"


def _parse_elements(elements: list[dict], spec: dict) -> pd.DataFrame:
    rows = []
    for el in elements:
        if "lat" in el:
            lon, lat = el["lon"], el["lat"]
        elif "center" in el:
            lon, lat = el["center"]["lon"], el["center"]["lat"]
        else:
            continue
        tags = el.get("tags", {})
        cap, proxy = 1.0, True
        capspec = spec.get("capacity", {})
        if capspec.get("source") == "beds":
            try:
                cap = float(str(tags.get(capspec.get("tag", "beds"), "")).split(";")[0])
                proxy = False
            except (TypeError, ValueError):
                cap, proxy = 1.0, True
        rows.append({"lon": lon, "lat": lat, "capacity": cap,
                     "capacity_proxy": proxy,
                     "osm_id": f"{el.get('type', '?')}/{el.get('id', '?')}"})
    df = pd.DataFrame(rows, columns=["lon", "lat", "capacity", "capacity_proxy", "osm_id"])
    return df.drop_duplicates(subset=["osm_id"]).reset_index(drop=True)


def _endpoints(cfg: dict) -> list[str]:
    ov = cfg.get("sources", {}).get("overpass", {}) or {}
    if ov.get("endpoints"):
        return list(ov["endpoints"])
    primary = ov.get("endpoint")
    mirrors = list(DEFAULT_MIRRORS)
    if primary and primary not in mirrors:
        mirrors.insert(0, primary)
    return mirrors


def _post_overpass(query: str, endpoints: list[str], timeout: int = 300):
    """POST the query, rotating through mirrors and backing off on transient
    failures. Sends the required User-Agent header (bare requests UA -> 406)."""
    last_err = None
    for endpoint in endpoints:
        for attempt in range(3):
            try:
                resp = requests.post(endpoint, data={"data": query},
                                     headers=HTTP_HEADERS, timeout=timeout)
            except requests.RequestException as err:  # network hiccup -> next try
                last_err = err
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code == 200:
                return resp, endpoint
            # 429/504/5xx are transient; 400/406 mean this endpoint won't serve
            # the request as formed — move to the next mirror.
            last_err = requests.HTTPError(
                f"{resp.status_code} from {endpoint}", response=resp)
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(15 * (attempt + 1))
            else:
                break
        print(f"WARNING: Overpass endpoint {endpoint} failed ({last_err}); "
              f"trying next mirror", flush=True)
    raise RuntimeError(f"All Overpass endpoints failed; last error: {last_err}")


def fetch_service(service: str, spec: dict, bbox, cfg: dict, root: Path,
                  city: str) -> pd.DataFrame:
    """Query one service's facilities, cache the raw JSON with provenance."""
    from depacc.provenance import sha256_of, sidecar_path

    endpoints = _endpoints(cfg)
    raw = root / cfg["output"]["raw_root"] / "overpass" / city
    raw.mkdir(parents=True, exist_ok=True)
    cache = raw / f"{service}.json"

    if not cache.exists():
        used_endpoint = endpoints[0]
        for rules in ([spec["osm"]] + ([spec["fallback_osm"]] if spec.get("fallback_osm") else [])):
            query = build_query(rules, bbox)
            resp, used_endpoint = _post_overpass(query, endpoints)
            payload = resp.json()
            if payload.get("elements"):
                break
        cache.write_text(json.dumps(payload))
        sidecar = {
            "url": used_endpoint, "query": query, "sha256": sha256_of(cache),
            "bytes": cache.stat().st_size, "licence": OSM_LICENCE,
            "retrieved_utc": pd.Timestamp.utcnow().isoformat(),
        }
        sidecar_path(cache).write_text(json.dumps(sidecar, indent=2))
        time.sleep(2)  # rate-limit courtesy between services

    payload = json.loads(cache.read_text())
    fac = _parse_elements(payload.get("elements", []), spec)
    fac["dest_id"] = [f"{service}_{i}" for i in range(len(fac))]
    return fac


def extract_facilities_overpass(cfg: dict, fua, root: Path, city: str) -> dict[str, pd.DataFrame]:
    """All services for a city via Overpass, clipped to the FUA polygon,
    with x/y in the analysis CRS (same schema as the pbf route)."""
    import geopandas as gpd

    fua_wgs = fua.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = fua_wgs.total_bounds
    bbox = (miny, minx, maxy, maxx)  # overpass wants (s, w, n, e)
    services = {**cfg.get("everyday_services", {}), **cfg.get("emergency_services", {})}
    out = {}
    for service, spec in services.items():
        # Alias sub-types reuse a parent's extraction (handled by the ingest
        # orchestrator); they have no OSM tags of their own.
        if (spec or {}).get("extract_alias"):
            continue
        fac = fetch_service(service, spec, bbox, cfg, root, city)
        if fac.empty:
            out[service] = fac.assign(x=pd.NA, y=pd.NA)
            continue
        g = gpd.GeoDataFrame(fac, geometry=gpd.points_from_xy(fac.lon, fac.lat),
                             crs="EPSG:4326")
        g = g[g.within(fua_wgs.union_all())]
        ana = g.to_crs(cfg["crs"]["analysis"])
        fac = pd.DataFrame({
            "dest_id": g["dest_id"], "lon": g.lon, "lat": g.lat,
            "x": ana.geometry.x, "y": ana.geometry.y,
            "capacity": g.capacity, "capacity_proxy": g.capacity_proxy,
        }).reset_index(drop=True)
        out[service] = fac
    return out
