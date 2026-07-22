"""Travel-time matrices: every populated cell -> every facility, per service
and mode.

Real cities use a single routing engine for all modes — R5 via r5py (JDK 21
required) — so Tier-1 (walk, car) and Tier-2 (+transit) matrices are
methodologically identical. Synthetic demo cities use a deterministic
straight-line router so the pipeline runs without network/Java.

Output: one long-format parquet per (service, mode) under
data/derived/<city>/od_<service>_<mode>.parquet with columns
[origin, dest, time]; pairs beyond routing.max_time_min are absent, and a
cell with no row for a service is unreachable (flagged downstream — see
depacc.deprivation.surfaces).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from depacc.ingest.pipeline import derived_dir

# Straight-line demo speeds (km/h) with a detour factor of 1.3; used ONLY for
# synthetic fixtures.
_SYNTH_SPEED = {"walk": 4.8, "car": 30.0, "transit": 15.0}
_SYNTH_DETOUR = 1.3
_SYNTH_ACCESS_OVERHEAD_MIN = {"walk": 0.0, "car": 3.0, "transit": 5.0}


def run_access(cfg: dict, city: str, root: Path) -> None:
    out = derived_dir(cfg, city, root)
    cells_path = out / "cells.parquet"
    if not cells_path.exists():
        raise RuntimeError(
            f"{cells_path} missing — the 'ingest' stage must run before "
            f"'access'. Each GitHub run starts on a fresh machine; if you "
            f"dispatched 'access' on its own, the per-city data/derived cache "
            f"from the ingest run may not have been restored (it can expire or "
            f"miss on the first staged run). Re-dispatch stage 'ingest' (or "
            f"stage 'all') for '{city}', then 'access'."
        )
    from depacc.config import service_extract_aliases

    cells = pd.read_parquet(cells_path)
    modes = cfg["routing"].get("modes") or cfg["tiers"]["tier1"]["modes"]
    services = list(cfg.get("everyday_services", {})) + list(cfg.get("emergency_services", {}))
    aliases = service_extract_aliases(cfg)
    k = int(cfg["routing"].get("k_nearest", 30))

    synthetic = bool(cfg["city"].get("synthetic"))
    engine = cfg["routing"].get("engine", "r5")
    network = None
    fua = None
    for service in services:
        # Alias sub-types reuse the parent's OD matrices (same facilities) — no
        # re-routing. The parent is listed first, so its OD already exists.
        if service in aliases:
            parent = aliases[service]
            for mode in modes:
                dst = out / f"od_{service}_{mode}.parquet"
                src = out / f"od_{parent}_{mode}.parquet"
                if dst.exists():
                    continue
                if src.exists():
                    pd.read_parquet(src).to_parquet(dst)
                    print(f"od[{service},{mode}]: aliased from '{parent}'")
            continue
        fac_path = out / f"facilities_{service}.parquet"
        if not fac_path.exists():
            print(f"WARNING: no facilities for '{service}'; skipping")
            continue
        facilities = pd.read_parquet(fac_path)
        if facilities.empty:
            print(f"WARNING: zero facilities for '{service}'; skipping")
            continue
        for mode in modes:
            od_path = out / f"od_{service}_{mode}.parquet"
            if od_path.exists():
                continue
            mode_max_time = float(_mode_cutoff_min(cfg, mode))
            if synthetic:
                od = keep_k_nearest(
                    _synthetic_matrix(cells, facilities, mode, mode_max_time), k)
            elif engine == "friction":
                import geopandas as gpd

                from depacc.access.friction import friction_matrix

                if fua is None:
                    fua = gpd.read_parquet(out / "fua_boundary.parquet")
                od = keep_k_nearest(
                    friction_matrix(cfg, cells, facilities, mode, fua, root, city), k)
            elif engine == "r5":
                if network is None:
                    network = _build_r5_network(cfg, city, out)
                od = _r5_matrix(network, cells, facilities, mode, cfg)  # trims per chunk
            else:
                raise ValueError(f"Unknown routing engine '{engine}'")
            od.to_parquet(od_path)
            reach = od.origin.nunique()
            print(f"od[{service},{mode}]: {len(od)} pairs, "
                  f"{reach}/{len(cells)} cells reach >=1 facility")


def _synthetic_matrix(cells: pd.DataFrame, facilities: pd.DataFrame,
                      mode: str, max_time: float) -> pd.DataFrame:
    """Deterministic straight-line travel times for the demo fixture."""
    speed_m_min = _SYNTH_SPEED[mode] * 1000.0 / 60.0
    dx = cells.x.to_numpy()[:, None] - facilities.x.to_numpy()[None, :]
    dy = cells.y.to_numpy()[:, None] - facilities.y.to_numpy()[None, :]
    t = np.hypot(dx, dy) * _SYNTH_DETOUR / speed_m_min + _SYNTH_ACCESS_OVERHEAD_MIN[mode]
    o, d = np.nonzero(t <= max_time)
    return pd.DataFrame({
        "origin": cells.cell_id.to_numpy()[o],
        "dest": facilities.dest_id.to_numpy()[d],
        "time": t[o, d],
    })


def _build_r5_network(cfg: dict, city: str, out: Path):
    import r5py

    pbf = Path((out / "network_pbf_path.txt").read_text().strip())
    gtfs: list[str] = []
    gtfs_list = out / "gtfs_paths.txt"
    if gtfs_list.exists():
        gtfs = [p for p in gtfs_list.read_text().splitlines() if p]
    print(f"Building R5 network from {pbf.name} + {len(gtfs)} GTFS feed(s)")
    return r5py.TransportNetwork(str(pbf), gtfs)


def _mode_cutoff_min(cfg: dict, mode: str) -> int:
    by_mode = cfg["routing"].get("max_time_min_by_mode") or {}
    return int(by_mode.get(mode) or cfg["routing"]["max_time_min"])


def keep_k_nearest(od: pd.DataFrame, k: int) -> pd.DataFrame:
    """Keep the k nearest destinations per origin (bounds output size; far
    facilities are negligible for soft-min / nearest measures)."""
    if od.empty or k <= 0:
        return od
    return (od.sort_values("time")
              .groupby("origin", sort=False)
              .head(k)
              .reset_index(drop=True))


def _r5_matrix(network, cells: pd.DataFrame, facilities: pd.DataFrame,
               mode: str, cfg: dict) -> pd.DataFrame:
    import datetime

    import geopandas as gpd
    import r5py

    r5_modes = {
        "walk": [r5py.TransportMode.WALK],
        "car": [r5py.TransportMode.CAR],
        "transit": [r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
    }[mode]
    dep = cfg["routing"]["departure"]
    # Next occurrence of the configured weekday must fall inside the GTFS
    # validity window; r5py warns if not. Date is resolved at run time.
    departure = _next_weekday(dep["weekday"], dep["time_window_start"])
    max_time = datetime.timedelta(minutes=_mode_cutoff_min(cfg, mode))
    window = datetime.timedelta(
        minutes=int(cfg["routing"]["departure"]["time_window_minutes"]))
    walk_speed = float(cfg["routing"]["walk_speed_kmh"])
    chunk = int(cfg["routing"].get("origin_chunk", 5000))
    k = int(cfg["routing"].get("k_nearest", 30))

    destinations = gpd.GeoDataFrame(
        {"id": facilities.dest_id},
        geometry=gpd.points_from_xy(facilities.lon, facilities.lat), crs="EPSG:4326",
    )

    # r5py >= 1.0 exposes TravelTimeMatrix (the instance IS the result);
    # older versions used TravelTimeMatrixComputer(...).compute_travel_times().
    use_new_api = hasattr(r5py, "TravelTimeMatrix")

    def _compute(origins: gpd.GeoDataFrame) -> pd.DataFrame:
        kwargs = dict(
            origins=origins, destinations=destinations,
            transport_modes=r5_modes, departure=departure,
            departure_time_window=window, max_time=max_time,
            speed_walking=walk_speed,
        )
        if use_new_api:
            tt = pd.DataFrame(r5py.TravelTimeMatrix(network, **kwargs))
        else:  # pragma: no cover - legacy r5py
            tt = r5py.TravelTimeMatrixComputer(network, **kwargs).compute_travel_times()
        return tt.rename(
            columns={"from_id": "origin", "to_id": "dest", "travel_time": "time"}
        ).dropna(subset=["time"])[["origin", "dest", "time"]]

    # Batch origins so peak memory is one chunk's matrix, not 176k x n_dest.
    parts = []
    for start in range(0, len(cells), chunk):
        sub = cells.iloc[start:start + chunk]
        origins = gpd.GeoDataFrame(
            {"id": sub.cell_id},
            geometry=gpd.points_from_xy(sub.lon, sub.lat), crs="EPSG:4326",
        )
        parts.append(keep_k_nearest(_compute(origins), k))
    if not parts:
        return pd.DataFrame(columns=["origin", "dest", "time"])
    return pd.concat(parts, ignore_index=True)


def _next_weekday(weekday: str, hhmm: str):
    import datetime

    names = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]
    target = names.index(weekday.lower())
    today = datetime.date.today()
    delta = (target - today.weekday()) % 7 or 7
    day = today + datetime.timedelta(days=delta)
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime.combine(day, datetime.time(hour, minute))
