"""The routing stage must survive being cut short.

An R5 city the size of Hamburg does not fit in one CI job — run 30164334307
hit the 5 h job timeout with the emergency car matrices still running, and
because a *cancelled* job skips actions/cache's save step, the 2 h 20 of walk
matrices it had already built were thrown away as well. These tests pin the two
properties that make that unrepeatable: a budgeted run stops CLEANLY, and
everything it finished — whole matrices and, inside a matrix, whole origin
chunks — is on disk and reused on the next run.
"""

import json
import sys
import types

import numpy as np
import pandas as pd
import pytest

from depacc.access.matrices import (
    BUDGET_ENV,
    AccessProgress,
    RoutingBudgetExhausted,
    _partial_dir,
    _r5_matrix,
    _routing_budget_min,
    run_access,
)
from depacc.config import load_config

pytest.importorskip("pyarrow", reason="parquet engine required for OD matrices")

#: Any positive budget expires immediately once routing starts, which is how
#: these tests provoke the stop without waiting minutes for it.
_INSTANT = "1e-9"


# --------------------------------------------------------------------------- #
# Budget resolution                                                            #
# --------------------------------------------------------------------------- #
def test_budget_defaults_to_unlimited_and_config_beats_env(monkeypatch):
    """Unlimited by default: an interactive run must never stop itself."""
    monkeypatch.delenv(BUDGET_ENV, raising=False)
    assert _routing_budget_min({"routing": {}}) is None
    assert _routing_budget_min({}) is None

    monkeypatch.setenv(BUDGET_ENV, "90")
    assert _routing_budget_min({"routing": {}}) == 90.0
    assert _routing_budget_min({"routing": {"time_budget_min": 15}}) == 15.0


@pytest.mark.parametrize("raw", ["0", "-5", "not-a-number", ""])
def test_unusable_budgets_mean_unlimited_not_zero(monkeypatch, raw):
    """A misconfigured budget must not silently route nothing at all."""
    monkeypatch.setenv(BUDGET_ENV, raw)
    assert _routing_budget_min({"routing": {}}) is None


# --------------------------------------------------------------------------- #
# Stage-level resumption                                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def demo_access(tmp_path_factory):
    """A fully routed demo city, to interrupt copies of."""
    from depacc.cli import main

    root = tmp_path_factory.mktemp("budget_demo")
    for stage in ("ingest", "access"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(root)]) == 0
    return load_config("demo"), root


def test_finished_matrices_are_never_rerouted(demo_access, monkeypatch):
    """The whole resumption story rests on this: with every matrix already on
    disk, an instantly-expired budget must still report success, because there
    is no work left to be interrupted."""
    cfg, root = demo_access
    monkeypatch.setenv(BUDGET_ENV, _INSTANT)
    progress = run_access(cfg, "demo", root)
    assert isinstance(progress, AccessProgress)
    assert progress.complete and not progress.pending
    assert progress.done


def test_budget_stop_names_exactly_the_unfinished_work(demo_access, tmp_path,
                                                       monkeypatch):
    cfg, root = demo_access
    out = root / cfg["output"]["root"] / "demo"

    work = tmp_path / "resume"
    (work / cfg["output"]["root"] / "demo").mkdir(parents=True)
    dst = work / cfg["output"]["root"] / "demo"
    for src in out.iterdir():
        if src.is_file():
            (dst / src.name).write_bytes(src.read_bytes())
    # Drop one routed matrix; everything else stays finished.
    (dst / "od_gp_walk.parquet").unlink()
    (dst / "od_gp_car.parquet").unlink()

    monkeypatch.setenv(BUDGET_ENV, _INSTANT)
    with pytest.raises(RoutingBudgetExhausted) as excinfo:
        run_access(cfg, "demo", work)

    exc = excinfo.value
    assert "gp,walk" in exc.pending
    # Reporting must be exact, or "re-dispatch to resume" is unverifiable.
    assert not any(p.startswith("pharmacy") for p in exc.pending)
    assert "pharmacy,walk" in exc.done
    assert "resume" in str(exc)

    # ...and the very next run, unbudgeted, finishes only what was left.
    monkeypatch.delenv(BUDGET_ENV, raising=False)
    progress = run_access(cfg, "demo", work)
    assert progress.complete
    assert (dst / "od_gp_walk.parquet").exists()
    pd.testing.assert_frame_equal(pd.read_parquet(dst / "od_gp_walk.parquet"),
                                  pd.read_parquet(out / "od_gp_walk.parquet"))


def test_cli_reports_a_budget_stop_as_a_distinct_exit_code(demo_access, tmp_path,
                                                           monkeypatch):
    """Exit 2, not 1: CI has to tell "stopped on budget, progress cached, come
    back" apart from a genuine failure, and must not run later stages — every
    unrouted cell would read as service-deprived."""
    from depacc.cli import BUDGET_EXIT_CODE, main

    cfg, root = demo_access
    out = root / cfg["output"]["root"] / "demo"
    work = tmp_path / "cli"
    dst = work / cfg["output"]["root"] / "demo"
    dst.mkdir(parents=True)
    for src in out.iterdir():
        if src.is_file() and not src.name.startswith("od_"):
            (dst / src.name).write_bytes(src.read_bytes())

    monkeypatch.setenv(BUDGET_ENV, _INSTANT)
    rc = main(["run", "--city", "demo", "--stage", "deprivation",
               "--project-root", str(work)])
    assert rc == BUDGET_EXIT_CODE
    assert not (dst / "surfaces.parquet").exists()


# --------------------------------------------------------------------------- #
# Chunk-level checkpointing                                                    #
# --------------------------------------------------------------------------- #
class _StubTransportMode:
    WALK, CAR, TRANSIT = "WALK", "CAR", "TRANSIT"


def _install_stub_r5py(monkeypatch, calls: list):
    """A minimal r5py stand-in: r5py itself needs a JDK and a .pbf, and what is
    under test here is the checkpoint bookkeeping around the router, not the
    router."""
    module = types.ModuleType("r5py")
    module.TransportMode = _StubTransportMode

    def _matrix(_network, origins=None, destinations=None, **_kwargs):
        calls.append(list(origins["id"]))
        return pd.DataFrame({
            "from_id": np.repeat(origins["id"].to_numpy(), len(destinations)),
            "to_id": np.tile(destinations["id"].to_numpy(), len(origins)),
            "travel_time": np.tile(
                np.arange(1.0, len(destinations) + 1.0), len(origins)),
        })

    module.TravelTimeMatrix = _matrix
    monkeypatch.setitem(sys.modules, "r5py", module)
    return module


def _chunked_inputs(n_cells=10, chunk=4):
    cells = pd.DataFrame({
        "cell_id": [f"c{i}" for i in range(n_cells)],
        "lon": np.linspace(10.0, 10.1, n_cells),
        "lat": np.linspace(53.5, 53.6, n_cells),
    })
    facilities = pd.DataFrame({"dest_id": ["f0", "f1"],
                               "lon": [10.05, 10.06], "lat": [53.55, 53.56]})
    cfg = {"routing": {
        "departure": {"weekday": "tuesday", "time_window_start": "08:00",
                      "time_window_minutes": 60},
        "max_time_min": 60, "walk_speed_kmh": 4.8,
        "origin_chunk": chunk, "k_nearest": 30,
    }}
    return cells, facilities, cfg


def test_finished_origin_chunks_are_checkpointed_and_reused(tmp_path, monkeypatch):
    """A single 60-minute-cutoff car matrix over 176k origins outlives a CI job,
    so whole-matrix granularity is not enough — an interrupted matrix must not
    cost its finished chunks."""
    pytest.importorskip("geopandas")
    calls: list = []
    _install_stub_r5py(monkeypatch, calls)
    cells, facilities, cfg = _chunked_inputs(n_cells=10, chunk=4)
    part_dir = _partial_dir(tmp_path / "od_gp_car.parquet")

    class _ExpiresAfterTwoChunks:
        budget_min = 1.0

        def expired(self_inner):
            return len(calls) >= 2

    with pytest.raises(Exception) as excinfo:
        _r5_matrix(None, cells, facilities, "car", cfg,
                   part_dir=part_dir, deadline=_ExpiresAfterTwoChunks())
    assert excinfo.type.__name__ == "_ChunkBudgetStop"
    assert sorted(p.name for p in part_dir.glob("*.parquet")) == \
        ["chunk_00000.parquet", "chunk_00001.parquet"]

    # Resuming routes ONLY the chunks that were never finished.
    calls.clear()
    od = _r5_matrix(None, cells, facilities, "car", cfg,
                    part_dir=part_dir, deadline=None)
    assert calls == [["c8", "c9"]]
    assert sorted(od.origin.unique()) == [f"c{i}" for i in range(10)]


def test_foreign_engine_matrix_is_never_reused(tmp_path):
    """The Köln 'friction' baseline was silently built over four r5 walk
    matrices left in the derived cache by a cancelled forward-r5 run
    (30476375657 -> 30484261519 -> the ρ=0.9997 anomaly of run 30535437441).
    An OD file may be reused only when its provenance sidecar matches what the
    current run would route; no sidecar means no reuse."""
    from depacc.cli import main

    root = tmp_path / "prov"
    for stage in ("ingest", "access"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(root)]) == 0
    out = next((root / "data" / "derived").glob("*"))
    od_files = sorted(out.glob("od_*.parquet"))
    assert od_files, "demo access stage produced no matrices"
    for od in od_files:
        meta = json.loads(od.with_suffix(".meta.json").read_text())
        assert meta["engine"] == "synthetic"

    # Same engine, same provenance: a re-run reuses every matrix untouched.
    victim = od_files[0]
    poison = pd.DataFrame({"origin": ["nope"], "dest": ["nope"], "time": [1.0]})
    before = victim.stat().st_mtime_ns
    assert main(["run", "--city", "demo", "--stage", "access",
                 "--project-root", str(root)]) == 0
    assert victim.stat().st_mtime_ns == before

    # Foreign provenance: the matrix is re-routed, not trusted.
    poison.to_parquet(victim)
    victim.with_suffix(".meta.json").write_text(json.dumps(
        {**json.loads(victim.with_suffix(".meta.json").read_text()),
         "engine": "r5"}))
    assert main(["run", "--city", "demo", "--stage", "access",
                 "--project-root", str(root)]) == 0
    rebuilt = pd.read_parquet(victim)
    assert "nope" not in set(rebuilt.origin)
    assert json.loads(victim.with_suffix(".meta.json").read_text())["engine"] \
        == "synthetic"

    # No sidecar at all (every pre-provenance cache): also re-routed.
    poison.to_parquet(victim)
    victim.with_suffix(".meta.json").unlink()
    assert main(["run", "--city", "demo", "--stage", "access",
                 "--project-root", str(root)]) == 0
    assert "nope" not in set(pd.read_parquet(victim).origin)


def test_reverse_chunks_are_capped_by_pair_budget(monkeypatch):
    """Reverse mode's dense side is the CELLS, so the facility-count chunk that
    is fine forward becomes a chunk x n_cells allocation reversed — the frame
    that starved the Köln cross-check runner to death (run 30526795903). The
    pair budget must shrink the chunk, and the per-chunk trim + fold must still
    yield exactly the k nearest facilities per cell."""
    pytest.importorskip("geopandas")
    calls: list = []
    _install_stub_r5py(monkeypatch, calls)
    n_cells, n_fac = 50, 8
    cells = pd.DataFrame({
        "cell_id": [f"c{i}" for i in range(n_cells)],
        "lon": np.linspace(10.0, 10.1, n_cells),
        "lat": np.linspace(53.5, 53.6, n_cells),
    })
    facilities = pd.DataFrame({
        "dest_id": [f"f{i}" for i in range(n_fac)],
        "lon": np.linspace(10.02, 10.08, n_fac),
        "lat": np.linspace(53.52, 53.58, n_fac),
    })
    cfg = {"routing": {
        "departure": {"weekday": "tuesday", "time_window_start": "08:00",
                      "time_window_minutes": 60},
        "max_time_min": 60, "walk_speed_kmh": 4.8,
        "origin_chunk": 5000, "k_nearest": 2,
        # 100 pairs / 50 cells -> at most 2 facilities searched per chunk.
        "reverse_pair_budget": 100,
    }}
    od = _r5_matrix(None, cells, facilities, "car", cfg, reverse=True)
    assert [len(c) for c in calls] == [2, 2, 2, 2]
    assert set(od.origin) == set(cells.cell_id)
    assert od.groupby("origin").size().max() <= 2
    assert not od.duplicated(["origin", "dest"]).any()


def test_reverse_resume_across_a_chunk_size_change_does_not_duplicate(
        tmp_path, monkeypatch):
    """A checkpoint written under an older (larger) chunking can cover pairs
    the new chunking routes again; both copies tie on time, so without the
    dedupe the k-nearest trim would keep duplicates."""
    pytest.importorskip("geopandas")
    calls: list = []
    _install_stub_r5py(monkeypatch, calls)
    n_cells, n_fac = 50, 8
    cells = pd.DataFrame({
        "cell_id": [f"c{i}" for i in range(n_cells)],
        "lon": np.linspace(10.0, 10.1, n_cells),
        "lat": np.linspace(53.5, 53.6, n_cells),
    })
    facilities = pd.DataFrame({
        "dest_id": [f"f{i}" for i in range(n_fac)],
        "lon": np.linspace(10.02, 10.08, n_fac),
        "lat": np.linspace(53.52, 53.58, n_fac),
    })
    cfg = {"routing": {
        "departure": {"weekday": "tuesday", "time_window_start": "08:00",
                      "time_window_minutes": 60},
        "max_time_min": 60, "walk_speed_kmh": 4.8,
        "origin_chunk": 5000, "k_nearest": 2,
        "reverse_pair_budget": 100,
    }}
    part_dir = _partial_dir(tmp_path / "od_gp_car.parquet", reverse=True)
    part_dir.mkdir(parents=True)
    # Stale chunk 0: the WHOLE matrix, as a single-chunk run would have written.
    stale = pd.DataFrame({
        "origin": np.tile([f"c{i}" for i in range(n_cells)], n_fac),
        "dest": np.repeat([f"f{i}" for i in range(n_fac)], n_cells),
        "time": np.repeat(np.arange(1.0, n_fac + 1.0), n_cells),
    })
    stale.to_parquet(part_dir / "chunk_00000.parquet")
    od = _r5_matrix(None, cells, facilities, "car", cfg,
                    part_dir=part_dir, reverse=True)
    assert not od.duplicated(["origin", "dest"]).any()
    assert od.groupby("origin").size().max() <= 2


def test_repeated_dispatches_converge_without_repeating_work(tmp_path, monkeypatch):
    """The operating procedure is "dispatch until it finishes", so the property
    that matters is not just that a stop is clean but that the dispatches
    COMPOSE: each makes forward progress, none re-routes anything an earlier
    one finished, and the last one produces the comparison.

    Simulated by budgeting each dispatch to a fixed number of matrices — what a
    240-minute budget does to Hamburg — with the derived directory persisting
    in between, which is exactly what the workflow's cache provides.
    """
    from depacc.access import matrices as m
    from depacc.cli import main

    root = tmp_path / "dispatched"
    for stage in ("ingest", "access", "deprivation"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(root)]) == 0

    routed: list[str] = []
    real_matrix = m._synthetic_matrix
    real_deadline = m._Deadline          # captured BEFORE any patching
    monkeypatch.setattr(m, "_synthetic_matrix",
                        lambda *a, **kw: (routed.append(a[2]),
                                          real_matrix(*a, **kw))[1])

    per_dispatch = 3

    class _ExpiresAfterN:
        budget_min = 240.0
        elapsed_min = 240.0

        def __init__(self, start):
            self._start = start

        def expired(self):
            return len(routed) - self._start >= per_dispatch

    dispatches = 0
    while True:
        dispatches += 1
        assert dispatches < 25, "not converging"
        start = len(routed)
        monkeypatch.setattr(m, "_Deadline", lambda _b, _s=start: _ExpiresAfterN(_s))
        rc = main(["engine-check", "--city", "demo", "--engine", "synthetic",
                   "--project-root", str(root)])
        if rc == 0:
            break
        assert rc == 2, f"dispatch {dispatches} exited {rc}, not a budget stop"
        assert len(routed) - start > 0, \
            f"dispatch {dispatches} made no forward progress — this is the " \
            f"livelock the whole resume design has to avoid"

    assert dispatches > 1, "budget never bit; the test proves nothing"
    total_dispatched = len(routed)
    assert (root / "data/derived/validation/demo_engine_check.csv").exists()

    # The decisive one: routing the same city in a single unbudgeted run costs
    # the SAME number of matrices. Any work repeated across dispatches would
    # show up here as a higher count above.
    oneshot = tmp_path / "oneshot"
    monkeypatch.setattr(m, "_Deadline", real_deadline)
    for stage in ("ingest", "access", "deprivation"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(oneshot)]) == 0
    routed.clear()   # count the SHADOW routing only, as above
    assert main(["engine-check", "--city", "demo", "--engine", "synthetic",
                 "--project-root", str(oneshot)]) == 0
    assert total_dispatched == len(routed)


def test_reverse_routing_transposes_back_to_origin_cell(tmp_path, monkeypatch):
    """R5 costs one street search per ORIGIN, so a service with 27 facilities
    and 176k cells is ~6500x cheaper routed backwards. The transpose must be
    invisible downstream: every consumer expects origin=cell, dest=facility.
    """
    pytest.importorskip("geopandas")
    calls: list = []
    _install_stub_r5py(monkeypatch, calls)
    cells, facilities, cfg = _chunked_inputs(n_cells=10, chunk=4)

    od = _r5_matrix(None, cells, facilities, "car", cfg, reverse=True)

    # R5 searched from the two FACILITIES, not from the ten cells.
    assert calls == [["f0", "f1"]]
    assert set(od.origin) == set(cells.cell_id)
    assert set(od.dest) == set(facilities.dest_id)
    assert len(od) == len(cells) * len(facilities)


def test_reverse_keeps_k_nearest_per_cell_not_per_facility_batch(tmp_path,
                                                                 monkeypatch):
    """The subtle one. Forward, a chunk holds whole origins, so trimming to the
    k nearest per chunk is correct. Reverse, a chunk holds ALL cells for a FEW
    facilities — trimming per chunk would keep k per facility-batch and let
    k x n_chunks rows through per cell. Trimming must happen after the concat.
    """
    pytest.importorskip("geopandas")
    calls: list = []
    _install_stub_r5py(monkeypatch, calls)
    # 6 facilities in chunks of 2 => 3 chunks; k=2 must still mean 2 per cell.
    cells = pd.DataFrame({
        "cell_id": [f"c{i}" for i in range(5)],
        "lon": np.linspace(10.0, 10.1, 5), "lat": np.linspace(53.5, 53.6, 5),
    })
    facilities = pd.DataFrame({
        "dest_id": [f"f{i}" for i in range(6)],
        "lon": np.linspace(10.0, 10.1, 6), "lat": np.linspace(53.5, 53.6, 6),
    })
    cfg = {"routing": {
        "departure": {"weekday": "tuesday", "time_window_start": "08:00",
                      "time_window_minutes": 60},
        "max_time_min": 60, "walk_speed_kmh": 4.8,
        "origin_chunk": 2, "k_nearest": 2,
    }}

    od = _r5_matrix(None, cells, facilities, "car", cfg, reverse=True)

    assert len(calls) == 3, "expected the facilities to be chunked"
    assert od.groupby("origin").size().max() == 2


def test_reverse_and_forward_checkpoints_never_share_a_directory(tmp_path):
    """Their chunks index different things — cells forward, facilities reverse —
    so one directory for both would load a handful of cell-chunks as though
    they were facility-chunks, silently truncating the matrix."""
    od_path = tmp_path / "od_emergency_dept_hospital_car.parquet"
    assert _partial_dir(od_path, reverse=False) != _partial_dir(od_path, reverse=True)
    assert _partial_dir(od_path, reverse=False).name.endswith(".partial")
    assert _partial_dir(od_path, reverse=True).name.endswith(".partial-rev")


def test_asymmetry_is_measured_on_the_pairs_both_directions_computed():
    """Reverse routing trades exactness for speed, so the error has to be
    reported rather than assumed. Hamburg has 4 forward chunks (20 000 origins)
    already on disk from run 30251028718 to check it against, for free."""
    from depacc.access.matrices import asymmetry_report

    forward = pd.DataFrame({
        "origin": ["c0", "c1", "c2"], "dest": ["f0", "f0", "f0"],
        "time": [10.0, 20.0, 30.0],
    })
    # c2 is absent from the reverse frame; it must not enter the statistics.
    reverse = pd.DataFrame({
        "origin": ["c0", "c1", "c3"], "dest": ["f0", "f0", "f0"],
        "time": [11.0, 23.0, 99.0],
    })
    stats = asymmetry_report(forward, reverse, "emergency_dept_hospital,car")
    assert stats["pairs"] == 2
    assert stats["median_abs_min"] == pytest.approx(2.0)
    assert stats["max_abs_min"] == pytest.approx(3.0)
    assert stats["mean_signed_min"] == pytest.approx(2.0)
    assert asymmetry_report(forward, pd.DataFrame(columns=forward.columns),
                            "x") is None


def test_a_completed_matrix_clears_its_checkpoints(demo_access, tmp_path,
                                                   monkeypatch):
    """Stale chunk files would be silently re-read into a later matrix, so a
    finished matrix must take its partial directory with it."""
    cfg, root = demo_access
    out = root / cfg["output"]["root"] / "demo"
    work = tmp_path / "clear"
    dst = work / cfg["output"]["root"] / "demo"
    dst.mkdir(parents=True)
    for src in out.iterdir():
        if src.is_file():
            (dst / src.name).write_bytes(src.read_bytes())
    (dst / "od_gp_walk.parquet").unlink()
    stale = _partial_dir(dst / "od_gp_walk.parquet")
    stale.mkdir()
    (stale / "chunk_00000.parquet").write_bytes(b"not a parquet")

    monkeypatch.delenv(BUDGET_ENV, raising=False)
    run_access(cfg, "demo", work)
    assert not stale.exists()
