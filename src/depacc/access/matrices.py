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

**Resumability.** An R5 run over a large FUA does not fit in one CI job:
Hamburg's 176k origins cost ~26 min per walk service and several hours per
60-minute-cutoff car service (run 30164334307). So routing is checkpointed at
two levels — a completed (service, mode) matrix is its own parquet and is
skipped on re-entry, and *within* a matrix each origin chunk is written to
``od_<service>_<mode>.partial/chunk_NNNNN.parquet`` as it completes. Combined
with an optional wall-clock budget (``routing.time_budget_min`` or
``DEPACC_ROUTING_BUDGET_MIN``) that stops the run cleanly rather than letting
the CI runner cancel it mid-flight, a multi-hour city can be routed across
several dispatches without ever repeating finished work.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
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

#: Env var equivalent of ``routing.time_budget_min`` — the CI workflows set it
#: rather than editing a city config.
BUDGET_ENV = "DEPACC_ROUTING_BUDGET_MIN"


class RoutingBudgetExhausted(RuntimeError):
    """The wall-clock routing budget ran out before every matrix was built.

    This is not a modelling error and nothing is lost: every finished
    (service, mode) matrix, and every finished origin chunk of the one in
    flight, is on disk. It is raised so the caller STOPS — building deprivation
    surfaces on a half-routed city would silently mark every unrouted cell
    unreachable, which is far worse than an obvious failure.
    """

    def __init__(self, done: list[str], pending: list[str], elapsed_min: float):
        self.done, self.pending, self.elapsed_min = list(done), list(pending), elapsed_min
        super().__init__(
            f"routing budget exhausted after {elapsed_min:.1f} min with "
            f"{len(pending)} matrix/matrices still to build "
            f"({', '.join(pending) or 'none'}). Progress is checkpointed — "
            f"re-dispatch to resume where this run stopped.")


class _ChunkBudgetStop(Exception):
    """Internal: the budget expired between origin chunks of one matrix."""

    def __init__(self, done_chunks: int, n_chunks: int):
        self.done_chunks, self.n_chunks = done_chunks, n_chunks
        super().__init__(f"{done_chunks}/{n_chunks} origin chunks")


@dataclass
class AccessProgress:
    """What ``run_access`` built, and what it has left. Returned so callers can
    report resumable state instead of guessing from the filesystem."""

    done: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.pending


class _Deadline:
    """Monotonic wall-clock budget. ``budget_min=None`` never expires."""

    def __init__(self, budget_min: float | None):
        self.budget_min = budget_min
        self._start = time.monotonic()
        self._deadline = None if budget_min is None else self._start + budget_min * 60.0

    @property
    def elapsed_min(self) -> float:
        return (time.monotonic() - self._start) / 60.0

    @property
    def remaining_min(self) -> float:
        if self._deadline is None:
            return float("inf")
        return (self._deadline - time.monotonic()) / 60.0

    def expired(self) -> bool:
        return self._deadline is not None and time.monotonic() >= self._deadline


def _routing_budget_min(cfg: dict) -> float | None:
    """Wall-clock routing budget in minutes, or None for unlimited (the
    default, so an interactive run is unaffected). Config wins over the env
    var; a non-positive or unparseable value means unlimited."""
    raw = (cfg.get("routing") or {}).get("time_budget_min")
    if raw in (None, ""):
        raw = os.environ.get(BUDGET_ENV, "").strip() or None
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        print(f"WARNING: ignoring unparseable {BUDGET_ENV}/routing.time_budget_min "
              f"{raw!r}; routing without a budget")
        return None
    return value if value > 0 else None


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


def _routing_plan(out: Path, services: list[str], modes: list[str],
                  service_modes: dict[str, list[str]],
                  aliases: dict[str, str]) -> list[dict]:
    """Every (service, mode) unit of work this run owes, in execution order.

    Computed up front from cheap filesystem checks so an interrupted run can
    say exactly what is left rather than "it stopped somewhere". Entries are
    ``kind`` route (needs the router), alias (a file copy off the parent) or
    skip (no facilities to route to).
    """
    def _routable(service: str) -> list[str]:
        """The modes this service will actually have an OD matrix for."""
        if not (out / f"facilities_{service}.parquet").exists():
            return []
        return list(service_modes.get(service, modes))

    plan: list[dict] = []
    for service in services:
        if service in aliases:
            # An alias copies the PARENT's matrices, so it can only have the
            # modes the parent was routed for — not every mode in `modes`.
            # Planning the parent's unrouted modes here would leave the run
            # permanently "pending" work that can never exist.
            parent = aliases[service]
            alias_modes = [m for m in _routable(service) if m in set(_routable(parent))]
            if not alias_modes:
                plan.append({"service": service, "mode": None, "kind": "skip",
                             "reason": f"parent '{parent}' has no routed matrix"})
                continue
            for mode in alias_modes:
                plan.append({"service": service, "mode": mode, "kind": "alias",
                             "parent": parent})
            continue
        if not (out / f"facilities_{service}.parquet").exists():
            plan.append({"service": service, "mode": None, "kind": "skip",
                         "reason": "no facilities extracted"})
            continue
        svc_modes = service_modes.get(service, modes)
        if not svc_modes:
            plan.append({"service": service, "mode": None, "kind": "skip",
                         "reason": "no regime mode available"})
            continue
        for mode in svc_modes:
            plan.append({"service": service, "mode": mode, "kind": "route"})
    return plan


def run_access(cfg: dict, city: str, root: Path) -> AccessProgress:
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
    empty_facilities: set[str] = set()

    plan = _routing_plan(out, services, modes, service_modes, aliases)
    deadline = _Deadline(_routing_budget_min(cfg))
    if deadline.budget_min is not None:
        print(f"access[{city}]: routing budget {deadline.budget_min:g} min "
              f"for {sum(p['kind'] == 'route' for p in plan)} matrices", flush=True)
    progress = AccessProgress()

    for i, task in enumerate(plan):
        service, mode, kind = task["service"], task["mode"], task["kind"]
        label = f"{service},{mode}" if mode else service
        if kind == "skip":
            print(f"WARNING: {task['reason']} for '{service}'; skipping")
            progress.skipped.append(label)
            continue
        if service in empty_facilities:
            progress.skipped.append(label)
            continue

        od_path = out / f"od_{service}_{mode}.parquet"
        if od_path.exists():
            progress.done.append(label)
            continue

        # Alias sub-types reuse the parent's OD matrices (same facilities) — no
        # re-routing. The parent is listed first, so its OD already exists.
        if kind == "alias":
            parent = task["parent"]
            src = out / f"od_{parent}_{mode}.parquet"
            if src.exists():
                pd.read_parquet(src).to_parquet(od_path)
                print(f"od[{label}]: aliased from '{parent}'", flush=True)
                progress.done.append(label)
            else:
                # The parent was skipped (no facilities to route to), so there
                # is nothing to alias — not work still owed.
                print(f"WARNING: no '{parent}' matrix to alias for '{label}'; "
                      f"skipping")
                progress.skipped.append(label)
            continue

        facilities = pd.read_parquet(out / f"facilities_{service}.parquet")
        if facilities.empty:
            print(f"WARNING: zero facilities for '{service}'; skipping")
            empty_facilities.add(service)
            progress.skipped.append(label)
            continue

        # Budget check BEFORE starting a matrix, and again between chunks
        # inside _r5_matrix: a 60-minute-cutoff car matrix over 176k origins is
        # itself multi-hour, so whole-matrix granularity would not be enough.
        if deadline.expired():
            _classify_tail(out, plan[i:], progress)
            break

        started = time.monotonic()
        mode_max_time = float(_mode_cutoff_min(cfg, mode))
        try:
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
                od = _r5_matrix(network, cells, facilities, mode, cfg,  # trims per chunk
                                part_dir=_partial_dir(od_path), deadline=deadline)
            else:
                raise ValueError(f"Unknown routing engine '{engine}'")
        except _ChunkBudgetStop as stop:
            print(f"od[{label}]: budget expired at {stop.done_chunks}/"
                  f"{stop.n_chunks} origin chunks — checkpointed, will resume",
                  flush=True)
            _classify_tail(out, plan[i:], progress)
            break

        od.to_parquet(od_path)
        _clear_partials(od_path)
        reach = od.origin.nunique()
        print(f"od[{label}]: {len(od)} pairs, "
              f"{reach}/{len(cells)} cells reach >=1 facility "
              f"[{(time.monotonic() - started) / 60.0:.1f} min]", flush=True)
        progress.done.append(label)

    if not progress.complete:
        print(f"access[{city}]: {len(progress.done)} matrix/matrices built in "
              f"{deadline.elapsed_min:.1f} min; {len(progress.pending)} left "
              f"({', '.join(progress.pending)})", flush=True)
        raise RoutingBudgetExhausted(progress.done, progress.pending,
                                     deadline.elapsed_min)
    return progress


def _classify_tail(out: Path, tasks: list[dict], progress: AccessProgress) -> None:
    """Account for the work the run never reached.

    A task in the tail is only PENDING if its matrix is not already on disk —
    a resumed run stops with most of the plan behind it, and reporting those
    as outstanding would make "N left" grow every dispatch instead of shrink.
    """
    for task in tasks:
        if task["kind"] == "skip" or task["mode"] is None:
            progress.skipped.append(task["service"])
            continue
        label = f"{task['service']},{task['mode']}"
        if (out / f"od_{task['service']}_{task['mode']}.parquet").exists():
            progress.done.append(label)
        else:
            progress.pending.append(label)


def _partial_dir(od_path: Path) -> Path:
    """Where an in-flight matrix's finished origin chunks live. A sibling
    directory rather than a suffix on the parquet so a half-built matrix can
    never be mistaken for a finished one by ``od_path.exists()``."""
    return od_path.with_suffix(".partial")


def _clear_partials(od_path: Path) -> None:
    import shutil

    shutil.rmtree(_partial_dir(od_path), ignore_errors=True)


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
               mode: str, cfg: dict, *, part_dir: Path | None = None,
               deadline: "_Deadline | None" = None) -> pd.DataFrame:
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
    # Each finished chunk is also checkpointed to part_dir: a single car matrix
    # over a large FUA outlives a CI job, so whole-matrix granularity would
    # throw away hours of routing every time a run is cut short.
    starts = list(range(0, len(cells), chunk))
    if part_dir is not None:
        part_dir.mkdir(parents=True, exist_ok=True)
    parts, restored = [], 0
    for i, start in enumerate(starts):
        cp = None if part_dir is None else part_dir / f"chunk_{i:05d}.parquet"
        if cp is not None and cp.exists():
            parts.append(pd.read_parquet(cp))
            restored += 1
            continue
        if deadline is not None and deadline.expired():
            raise _ChunkBudgetStop(i, len(starts))
        if restored:
            print(f"  resumed from {restored} checkpointed origin chunk(s)",
                  flush=True)
            restored = 0
        sub = cells.iloc[start:start + chunk]
        origins = gpd.GeoDataFrame(
            {"id": sub.cell_id},
            geometry=gpd.points_from_xy(sub.lon, sub.lat), crs="EPSG:4326",
        )
        part = keep_k_nearest(_compute(origins), k)
        if cp is not None:
            part.to_parquet(cp)
        parts.append(part)
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
