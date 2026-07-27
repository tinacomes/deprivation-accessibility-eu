"""The routing stage must survive being cut short.

An R5 city the size of Hamburg does not fit in one CI job — run 30164334307
hit the 5 h job timeout with the emergency car matrices still running, and
because a *cancelled* job skips actions/cache's save step, the 2 h 20 of walk
matrices it had already built were thrown away as well. These tests pin the two
properties that make that unrepeatable: a budgeted run stops CLEANLY, and
everything it finished — whole matrices and, inside a matrix, whole origin
chunks — is on disk and reused on the next run.
"""

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
