"""End-to-end integration test on the synthetic demo city (no network).

Exercises the full CLI pipeline: ingest -> access -> deprivation ->
divergence -> equity (viz excluded to keep CI light; it runs when matplotlib
is installed).
"""

import shutil

import pandas as pd
import pytest

from depacc.cli import main
from depacc.config import load_config

pytest.importorskip("pyarrow", reason="parquet engine required for pipeline outputs")


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo_project")
    for stage in ("ingest", "access", "deprivation", "divergence"):
        assert main(["run", "--city", "demo", "--stage", stage,
                     "--project-root", str(root)]) == 0
    cfg = load_config("demo")
    yield cfg, root
    shutil.rmtree(root, ignore_errors=True)


def test_outputs_exist_and_watermarked(demo_run):
    cfg, root = demo_run
    out = root / cfg["output"]["root"] / "demo"
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    assert bool(surfaces["synthetic"].all())
    assert {"deprivation_everyday", "deprivation_emergency",
            "unreachable_everyday", "unreachable_emergency"} <= set(surfaces.columns)
    # Both regimes also carry per-service nearest-time baselines.
    assert any(c.startswith("t_nearest_") for c in surfaces.columns)


def test_genuinely_unroutable_sets_equal_across_regimes(demo_run):
    """Phase 1 invariant: "no network path" is service- and mode-independent,
    so both regimes' genuinely-unroutable masks must be identical, and every
    masked cell is NaN on the composite surface the typology reads (one shared
    mask for the choropleth and the typology)."""
    cfg, root = demo_run
    out = root / cfg["output"]["root"] / "demo"
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    ev = surfaces["unreachable_everyday"].to_numpy(bool)
    em = surfaces["unreachable_emergency"].to_numpy(bool)
    assert (ev == em).all()
    assert surfaces.loc[ev, "deprivation_everyday"].isna().all()
    assert surfaces.loc[em, "deprivation_emergency"].isna().all()


def test_everyday_vs_emergency_differ(demo_run):
    cfg, root = demo_run
    out = root / cfg["output"]["root"] / "demo"
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    # The two regimes are computed by different mechanisms on different
    # services; identical surfaces would mean a wiring bug.
    corr = surfaces["deprivation_everyday"].corr(surfaces["deprivation_emergency"])
    assert corr < 0.999


def test_typology_and_cityplane(demo_run):
    cfg, root = demo_run
    out = root / cfg["output"]["root"] / "demo"
    summary = pd.read_csv(out / "typology_summary_50.csv")
    assert summary.population_share.sum() == pytest.approx(1.0, abs=1e-9)
    plane = pd.read_csv(root / cfg["output"]["root"] / "cityplane.csv")
    row = plane[plane.city == "demo"].iloc[0]
    assert bool(row.synthetic) is True
    assert 0 <= row.gini_everyday <= 1
    assert 0 <= row.gini_emergency <= 1
    assert 0 <= row.compounding_pop_share_50 <= 1
    assert 0 <= row.spearman_rho <= 1  # demo surfaces positively coupled


def test_equity_stage(demo_run):
    cfg, root = demo_run
    pytest.importorskip("statsmodels")
    assert main(["run", "--city", "demo", "--stage", "equity",
                 "--project-root", str(root)]) == 0
    out = root / cfg["output"]["root"] / "demo"
    indices = pd.read_csv(out / "equity_indices.csv")
    assert set(indices.regime) == {"everyday", "emergency"}
    regs = pd.read_csv(out / "equity_regressions.csv")
    # Synthetic city has an income gradient falling from the centre; the SES
    # concentration/regression machinery must produce finite estimates.
    assert regs.coef.notna().all()
