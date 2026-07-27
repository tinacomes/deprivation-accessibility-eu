"""Workstream E.1 — the routing-engine cross-check.

The plumbing is tested by running the check with the city's OWN engine: every
delta must come out zero and no cell may change class. That exercises the whole
path — shadow dir, inherited artefacts, re-routing, deprivation, comparison,
CSV — without needing a second real engine (r5 needs a JDK and a .pbf). The
disagreement metrics themselves are then tested against synthetic surfaces whose
answer is known.
"""

import shutil

import numpy as np
import pandas as pd
import pytest

from depacc.config import load_config
from depacc.quality.engine_check import (
    compare_engines,
    prepare_shadow,
    run_engine_check,
    shadow_city_id,
    shadow_config,
)

pytest.importorskip("pyarrow", reason="parquet engine required for cached inputs")


def test_shadow_id_nests_inside_the_city_directory():
    """A SIBLING directory would be published as a phantom city:
    tools/persist_results.py walks data/derived/* and treats every entry as one.
    Nested, the shadow is invisible to that walk."""
    assert shadow_city_id("hamburg", "r5") == "hamburg/engine_r5"


def test_shadow_config_overrides_only_the_engine():
    cfg = load_config("hamburg")
    alt = shadow_config(cfg, "r5")
    assert alt["routing"]["engine"] == "r5"
    assert cfg["routing"]["engine"] == "friction"        # original untouched
    for section in ("softmin", "catchment", "regimes", "unreachable",
                    "everyday_services", "emergency_services"):
        assert alt[section] == cfg[section], section
    # The mode set is overridable, and only when asked for.
    assert alt["routing"]["modes"] == cfg["routing"]["modes"]
    assert shadow_config(cfg, "r5", ["walk", "car", "transit"])["routing"]["modes"] \
        == ["walk", "car", "transit"]


@pytest.fixture(scope="module")
def demo_baseline(tmp_path_factory):
    from depacc.cli import main

    root = tmp_path_factory.mktemp("engine_check_demo")
    for stage in ("ingest", "access", "deprivation"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(root)]) == 0
    yield load_config("demo"), root
    shutil.rmtree(root, ignore_errors=True)


def test_shadow_inherits_facilities_rather_than_re_extracting(demo_baseline):
    """The check must isolate the ROUTING ENGINE. Hamburg's friction config takes
    facilities from Overpass while an r5 config would take them from the .pbf, so
    re-extracting would confound engine disagreement with facility-set
    disagreement — which is E.2's separate question."""
    cfg, root = demo_baseline
    _alt_cfg, base_out, alt_out = prepare_shadow(cfg, "demo", root, "synthetic")

    base_fac = sorted(p.name for p in base_out.glob("facilities_*.parquet"))
    alt_fac = sorted(p.name for p in alt_out.glob("facilities_*.parquet"))
    assert base_fac and alt_fac == base_fac
    for name in base_fac:
        pd.testing.assert_frame_equal(pd.read_parquet(base_out / name),
                                      pd.read_parquet(alt_out / name))
    pd.testing.assert_frame_equal(pd.read_parquet(base_out / "cells.parquet"),
                                  pd.read_parquet(alt_out / "cells.parquet"))


def test_same_engine_check_is_a_perfect_null(demo_baseline, tmp_path_factory):
    """The plumbing self-test: re-routing with the city's own engine must
    reproduce it exactly, so every delta is zero and no cell changes class. A
    non-zero row here means the shadow run diverged from the pipeline somewhere,
    which is precisely the failure the Layer-3 sweep shipped with once."""
    cfg, root = demo_baseline
    table = run_engine_check(cfg, "demo", root,
                             engine=cfg["routing"].get("engine", "r5"),
                             reuse=False)

    assert not table.empty
    assert (table["delta"].abs() < 1e-9).all(), \
        table.loc[table["delta"].abs() >= 1e-9]
    tt = table[table.scope == "travel_time"].dropna(subset=["spearman"])
    assert not tt.empty
    assert (tt["spearman"] > 0.999).all()
    flip = table[table.scope == "typology"]
    assert float(flip.iloc[0]["alt"]) == pytest.approx(0.0)

    val = root / cfg["output"]["root"] / "validation"
    assert (val / "demo_engine_check.csv").exists()


def test_check_reports_the_rank_disagreement_that_matters(tmp_path):
    """Every headline output is rank-based, so a constant shift costs nothing
    while REORDERING invalidates the typology. The comparison must separate
    the two: same ranks + offset -> ρ = 1 with a non-zero median delta;
    reversed ranks -> ρ = -1."""
    n = 200
    # Uniform weights on purpose: a population-weighted median is only invariant
    # under a permutation of the values when the weights are equal, and the point
    # of this test is rank-vs-level, not weighting (covered elsewhere).
    pop = np.ones(n)
    t_ev = np.linspace(1.0, 40.0, n)
    t_em = np.linspace(1.0, 25.0, n)

    def _write(dirpath, ev, em):
        dirpath.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "population": pop,
            "t_regime_everyday": ev, "t_regime_emergency": em,
            "deprivation_everyday": ev / 50.0,
            "deprivation_emergency": em / 50.0,
        }).to_parquet(dirpath / "surfaces.parquet")

    cfg = {"routing": {"engine": "friction"}, "city": {"name": "T"}}
    base = tmp_path / "base"
    _write(base, t_ev, t_em)

    shifted = tmp_path / "shifted"
    _write(shifted, t_ev + 5.0, t_em)          # monotone shift: ranks preserved
    tab = compare_engines(base, shifted, cfg, "t", "alt").set_index("item")
    assert tab.loc["everyday_median_min", "spearman"] == pytest.approx(1.0)
    assert tab.loc["everyday_median_min", "delta"] == pytest.approx(5.0, abs=0.2)
    assert tab.loc["flip_pop_share_50", "alt"] == pytest.approx(0.0)

    reversed_ = tmp_path / "reversed"
    _write(reversed_, t_ev[::-1], t_em)        # same values, opposite order
    tab2 = compare_engines(base, reversed_, cfg, "t", "alt").set_index("item")
    assert tab2.loc["everyday_median_min", "spearman"] == pytest.approx(-1.0)
    assert tab2.loc["everyday_median_min", "delta"] == pytest.approx(0.0, abs=0.2)
    # A reordering leaves the median untouched but moves the typology.
    assert tab2.loc["flip_pop_share_50", "alt"] > 0.5


def test_travel_times_are_compared_on_the_cells_both_engines_reach(tmp_path):
    """Summarising each engine over its OWN reachable set confounds a level
    difference with a composition one: an engine that simply gives up on the
    far periphery would post a lower median for that reason alone. The
    travel-time rows must be PAIRED — and the composition difference reported
    separately rather than swallowed."""
    n = 100
    pop = np.ones(n)
    t_ev = np.linspace(1.0, 100.0, n)
    t_em = np.linspace(1.0, 50.0, n)

    def _write(dirpath, ev, em):
        dirpath.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "population": pop,
            "t_regime_everyday": ev, "t_regime_emergency": em,
            "deprivation_everyday": np.nan_to_num(ev) / 200.0,
            "deprivation_emergency": em / 200.0,
        }).to_parquet(dirpath / "surfaces.parquet")

    base = tmp_path / "base"
    _write(base, t_ev, t_em)

    # The alternative reaches only the nearest half of the city, and is 2 min
    # SLOWER on every cell it does reach.
    alt_ev = np.where(np.arange(n) < n // 2, t_ev + 2.0, np.nan)
    alt = tmp_path / "alt"
    _write(alt, alt_ev, t_em)

    cfg = {"routing": {"engine": "friction"}, "city": {"name": "T"}}
    tab = compare_engines(base, alt, cfg, "t", "alt").set_index("item")

    row = tab.loc["everyday_median_min"]
    assert row["n"] == n // 2
    # Paired: the +2 min penalty is what shows up, NOT the ~-25 min that
    # comparing base-over-all against alt-over-half would have produced.
    assert row["delta"] == pytest.approx(2.0, abs=0.6)
    assert row["base"] < 55.0

    cov = tab.loc["everyday_reachable_pop_share"]
    assert cov["base"] == pytest.approx(1.0)
    assert cov["alt"] == pytest.approx(0.5)


def test_an_interrupted_check_leaves_a_progress_manifest(tmp_path):
    """Run 30164334307 timed out and uploaded nothing at all — the artefact
    step reported "No files were found". A stop must be legible as an artefact,
    naming what is done and what is still owed."""
    from depacc.access.matrices import RoutingBudgetExhausted
    from depacc.quality.engine_check import write_progress_manifest

    exc = RoutingBudgetExhausted(done=["gp,walk", "pharmacy,walk"],
                                 pending=["emergency_dept_hospital,car"],
                                 elapsed_min=241.0)
    path = write_progress_manifest(tmp_path, "hamburg", "r5", exc)

    table = pd.read_csv(path)
    assert path.name == "hamburg_engine_check_progress.csv"
    assert set(table["status"]) == {"done", "pending"}
    assert table.loc[table.status == "pending", "matrix"].tolist() == \
        ["emergency_dept_hospital,car"]
    assert (table["alt_engine"] == "r5").all()
