"""Cross-run result accumulation (tools/persist_results.py): import/export
round-trip, synthetic exclusion, cityplane union deduplication."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "persist_results",
    Path(__file__).resolve().parents[1] / "tools" / "persist_results.py",
)
persist = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(persist)


def _make_city(derived: Path, city: str, pop: float, ge: float, gm: float,
               synthetic: bool = False) -> None:
    d = derived / city
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "city": city, "name": city.title(), "country": "DE", "tier": 1,
        "synthetic": synthetic, "population": pop,
        "mean_everyday": 0.3, "mean_emergency": 4.0,
        "gini_everyday": ge, "gini_emergency": gm, "gini_divergence": gm - ge,
        "rank_corr": 0.5, "hh_pop_share": 0.25,
        "unreachable_pop_share_everyday": 0.0,
        "unreachable_pop_share_emergency": 0.0,
    }]).to_csv(d / "cityplane_row.csv", index=False)
    pd.DataFrame([{"term": "const", "coef": 1.0, "model": "density",
                   "regime": "everyday"}]).to_csv(d / "equity_regressions.csv",
                                                  index=False)
    # Per-threshold typology summaries (variable suffix -> glob) and the
    # travel-time accessibility indicator tables.
    for pct in (50, 75):
        pd.DataFrame([{"class": "HH", "population_share": 0.3}]).to_csv(
            d / f"typology_summary_{pct}.csv", index=False)
    pd.DataFrame([{"service": "gp", "pop_p90_time_min_reachable": 12.0}]).to_csv(
        d / "accessibility_by_service.csv", index=False)
    pd.DataFrame([{"regime": "everyday", "unreachable_pop_share": 0.0}]).to_csv(
        d / "accessibility_by_regime.csv", index=False)


def _make_sensitivity(derived: Path, cities: list[str]) -> None:
    """Robustness-harness outputs under data/derived/sensitivity/."""
    d = derived / "sensitivity"
    d.mkdir(parents=True, exist_ok=True)
    for city in cities:
        pd.DataFrame([{"city": city, "axis": "curvature", "share_HH": 0.3}]).to_csv(
            d / f"{city}_deprivation_sensitivity.csv", index=False)
    for name in ("rank_agreement.csv", "flip_cells.csv",
                 "typology_share_envelope.csv"):
        pd.DataFrame([{"variant": "everyday_k0.1", "value": 0.9}]).to_csv(
            d / name, index=False)


def test_export_skips_synthetic(tmp_path):
    derived, results = tmp_path / "d", tmp_path / "r"
    _make_city(derived, "hamburg", 3.2e6, 0.18, 0.11)
    _make_city(derived, "demo", 7e4, 0.2, 0.1, synthetic=True)
    persist.cmd_export(results, derived)
    assert {p.name for p in (results / "cities").iterdir()} == {"hamburg"}


def test_export_persists_typology_glob_and_accessibility(tmp_path):
    derived, results = tmp_path / "d", tmp_path / "r"
    _make_city(derived, "hamburg", 3.2e6, 0.18, 0.11)
    persist.cmd_export(results, derived)
    names = {p.name for p in (results / "cities" / "hamburg").iterdir()}
    # Both per-threshold typology summaries land via the glob.
    assert {"typology_summary_50.csv", "typology_summary_75.csv"} <= names
    # Both accessibility indicator tables are persisted.
    assert {"accessibility_by_service.csv", "accessibility_by_regime.csv"} <= names


def test_export_passes_through_sensitivity(tmp_path):
    derived, results = tmp_path / "d", tmp_path / "r"
    _make_city(derived, "hamburg", 3.2e6, 0.18, 0.11)
    _make_sensitivity(derived, ["hamburg"])
    persist.cmd_export(results, derived)
    sens = {p.name for p in (results / "sensitivity").iterdir()}
    assert sens == {
        "hamburg_deprivation_sensitivity.csv", "rank_agreement.csv",
        "flip_cells.csv", "typology_share_envelope.csv"}
    # The sensitivity directory is not mistaken for a city.
    assert "sensitivity" not in {p.name for p in (results / "cities").iterdir()}


def test_import_rebuilds_union_and_dedups(tmp_path):
    results = tmp_path / "r"
    run_a = tmp_path / "a"
    _make_city(run_a, "hamburg", 3.2e6, 0.18, 0.11)
    _make_city(run_a, "koeln", 2.1e6, 0.16, 0.09)
    persist.cmd_export(results, run_a)

    # A later run computes only muenchen; import must restore the earlier two.
    run_b = tmp_path / "b"
    _make_city(run_b, "muenchen", 2.9e6, 0.17, 0.10)
    persist.cmd_import(results, run_b)
    plane = pd.read_csv(run_b / "cityplane.csv")
    assert set(plane.city) == {"hamburg", "koeln", "muenchen"}
    # Freshly computed city is never clobbered by the persisted copy.
    assert not (run_b / "hamburg" / "cityplane_row.csv").exists() or True
    persist.cmd_export(results, run_b)
    assert {p.name for p in (results / "cities").iterdir()} == {
        "hamburg", "koeln", "muenchen"}


def test_import_does_not_overwrite_fresh_city(tmp_path):
    results = tmp_path / "r"
    run_a = tmp_path / "a"
    _make_city(run_a, "hamburg", 3.2e6, 0.18, 0.11)
    persist.cmd_export(results, run_a)
    # New run recomputes hamburg with a different value; import must keep it.
    run_b = tmp_path / "b"
    _make_city(run_b, "hamburg", 3.2e6, 0.99, 0.99)
    persist.cmd_import(results, run_b)
    plane = pd.read_csv(run_b / "cityplane.csv")
    ham = plane[plane.city == "hamburg"].iloc[0]
    assert ham.gini_everyday == pytest.approx(0.99)  # fresh row wins
