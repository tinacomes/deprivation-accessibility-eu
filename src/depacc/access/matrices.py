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

# Sensitivity Layer-3 accessibility "mode" axis values -> the concrete routing
# modes they require (walk_transit = the elementwise-min of walk and transit).
_SENS_MODE_ALIAS = {
    "walk": {"walk"},
    "car": {"car"},
    "transit": {"transit"},
    "walk_transit": {"walk", "transit"},
}


def _route_sensitivity_modes(cfg: dict) -> bool:
    """Whether to route the EXTRA everyday modes named by the Layer-3
    accessibility axis (e.g. car, for the walk+car variant).

    OFF by default: those matrices roughly double a friction city's access
    time (the everyday×car Dijkstra is the dominant cost — cf. Workstream A.2),
    yet they are only consumed if you actually run the Layer-3 sweep's mode
    variant. So it is opt-in — enabled per deep-dive run, off for the many-city
    batch. When off, the access stage routes only the regime modes and the
    Layer-3 sweep simply skips the variants whose modes were not saved.

    Enabled by ``routing.route_sensitivity_modes: true`` in the (merged) config
    or the ``DEPACC_ROUTE_SENSITIVITY_MODES`` env var (1/true/yes)."""
    import os

    if bool((cfg.get("routing") or {}).get("route_sensitivity_modes", False)):
        return True
    return os.environ.get("DEPACC_ROUTE_SENSITIVITY_MODES", "").strip().lower() in (
        "1", "true", "yes", "on")


def _sensitivity_access_modes(cfg: dict) -> set[str]:
    """Routing modes named by the sensitivity Layer-3 accessibility axis.

    Precomputing these here keeps the Layer-3 accessibility variants cheap:
    the sweep reuses saved OD matrices instead of re-routing. The sweep grid
    lives in its own file (config/sensitivity.yaml), not the merged per-city
    config, so fall back to loading it directly when it is absent from cfg.
    Only the everyday (2SFCA/soft-min access) regime is swept on mode.

    Gated by :func:`_route_sensitivity_modes` (OFF by default) so a normal run
    — and every many-city batch run — pays only for the regime modes.
    """
    if not _route_sensitivity_modes(cfg):
        return set()
    axis = ((cfg.get("sensitivity") or {}).get("accessibility")) or {}
    if not axis:
        try:
            import yaml

            from depacc.config import CONFIG_DIR
            grid = yaml.safe_load((CONFIG_DIR / "sensitivity.yaml").read_text()) or {}
            axis = ((grid.get("sensitivity") or {}).get("accessibility")) or {}
        except Exception:  # pragma: no cover - defensive; sensitivity is optional
            axis = {}
    modes: set[str] = set()
    for m in axis.get("mode", []) or []:
        modes |= _SENS_MODE_ALIAS.get(str(m), {str(m)})
    # Layer-3 everyday_modes variants ([[walk], [walk, car], ...]) declare the
    # concrete everyday mode sets to sweep; keep the OD for every mode any
    # declared variant needs so the sweep stays cheap (reuses saved matrices).
    for modeset in axis.get("everyday_modes", []) or []:
        for m in modeset if isinstance(modeset, (list, tuple)) else [modeset]:
            modes |= _SENS_MODE_ALIAS.get(str(m), {str(m)})
    return modes


def _service_modes(cfg: dict, available: list[str]) -> dict[str, list[str]]:
    """Map each service to the routing modes actually consumed downstream.

    The deprivation stage reads only the OD matrices for its regime's modes
    (``regimes.<regime>.modes``); computing every mode for every service is
    wasted routing. Everyday services additionally get the modes named by the
    sensitivity Layer-3 accessibility axis so those variants reuse saved
    matrices. The result is intersected with ``available`` (the modes this run
    can route) so a Tier-1 walk/car run never tries to route transit.
    """
    avail = list(dict.fromkeys(available))  # order-preserving dedupe
    avail_set = set(avail)
    regimes = cfg.get("regimes", {}) or {}
    everyday_modes = set(regimes.get("everyday", {}).get("modes", []) or [])
    emergency_modes = set(regimes.get("emergency", {}).get("modes", []) or [])
    sens_modes = _sensitivity_access_modes(cfg)

    def _ordered(wanted: set[str]) -> list[str]:
        return [m for m in avail if m in wanted]

    result: dict[str, list[str]] = {}
    for s in cfg.get("everyday_services", {}) or {}:
        result[s] = _ordered((everyday_modes | sens_modes) & avail_set)
    for s in cfg.get("emergency_services", {}) or {}:
        result[s] = _ordered(emergency_modes & avail_set)
    return result


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
    # Only route the (service, mode) pairs the service's regime consumes (plus
    # the sensitivity Layer-3 modes for everyday services); routing every mode
    # for every service is wasted work — see _service_modes.
    service_modes = _service_modes(cfg, modes)
    # Alias sub-types reuse a parent service's OD matrices (same facilities).
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
        svc_modes = service_modes.get(service, modes)
        if not svc_modes:
            print(f"WARNING: no regime mode available for '{service}'; skipping")
            continue
        for mode in svc_modes:
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
