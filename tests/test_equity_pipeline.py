"""Equity stage wiring: concentration-index column selection and the
per-covariate SES gradient regressions that must not collapse when Zensus
themes are suppressed on disjoint cells."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")

from depacc.equity.pipeline import _resolve_rank_column, run_equity


def _write_surfaces(root, city, surfaces):
    out = root / "data" / "derived" / city
    out.mkdir(parents=True, exist_ok=True)
    surfaces.to_parquet(out / "surfaces.parquet")
    return out


def _base_cfg():
    return {"output": {"root": "data/derived"}}


def test_resolve_rank_column_explicit_then_heuristic():
    cols = ["ses_age_share_ge65", "ses_net_rent_qm", "ses_vacancy"]
    # Explicit key wins.
    assert _resolve_rank_column({"ses_rank_column": "ses_vacancy"}, cols) == "ses_vacancy"
    # Absent explicit key -> fall back to income/rent heuristic.
    assert _resolve_rank_column({"ses_rank_column": "ses_missing"}, cols) == "ses_net_rent_qm"
    # No key at all -> heuristic.
    assert _resolve_rank_column({}, cols) == "ses_net_rent_qm"
    # Nothing rent/income-like -> None.
    assert _resolve_rank_column({}, ["ses_age_share_ge65"]) is None


def _disjoint_suppression_surfaces(n=400):
    rng = np.random.default_rng(0)
    pop = rng.uniform(1, 100, n)
    # A real everyday gradient the regressions should recover.
    age65 = rng.uniform(0, 0.4, n)
    dep_ev = 0.2 + 0.5 * age65 + rng.normal(0, 0.02, n)
    df = pd.DataFrame({
        "population": pop,
        "deprivation_everyday": dep_ev,
        "deprivation_emergency": rng.uniform(0, 30, n),
        "ses_age_share_ge65": age65,          # dense: every cell present
        "ses_net_rent_qm": rng.uniform(6, 14, n),
    })
    # Suppress the two SES themes on DISJOINT halves: no cell has both present,
    # so a single listwise regression over both columns sees zero complete rows.
    df.loc[: n // 2, "ses_net_rent_qm"] = np.nan
    df.loc[n // 2 :, "ses_age_share_ge65"] = np.nan
    return df


def test_ses_regressions_survive_disjoint_suppression(tmp_path):
    df = _disjoint_suppression_surfaces()
    # Sanity: no cell has both covariates -> the old all-columns listwise path
    # would drop every row.
    assert df[["ses_age_share_ge65", "ses_net_rent_qm"]].dropna().empty

    _write_surfaces(tmp_path, "sup", df)
    run_equity(_base_cfg(), "sup", tmp_path)

    regs = pd.read_csv(tmp_path / "data" / "derived" / "sup" / "equity_regressions.csv")
    ses = regs[regs.model == "ses"]
    terms = set(ses.term)
    # Both covariates produced a gradient on their own support (not collapsed).
    assert "ses_age_share_ge65" in terms
    assert "ses_net_rent_qm" in terms
    assert ses.coef.notna().all()
    # Each univariate regression ran on ~half the cells, not the empty overlap.
    assert (ses[ses.term != "const"].n > 100).all()


def test_run_equity_writes_vulnerability_table(tmp_path):
    rng = np.random.default_rng(2)
    n = 300
    age65 = np.linspace(0, 0.5, n)
    surfaces = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "deprivation_everyday": 0.2 + 0.6 * age65,
        "deprivation_emergency": rng.uniform(0, 30, n),
        "ses_age_share_ge65": age65,
    }, index=[f"c{i}" for i in range(n)])
    out = _write_surfaces(tmp_path, "vuln", surfaces)
    # A row-aligned typology with HH concentrated in the elderly tail.
    pd.DataFrame(
        {"typology_50": np.where(age65 >= 0.375, "HH", "LL")}, index=surfaces.index,
    ).to_parquet(out / "typology.parquet")

    cfg = {**_base_cfg(), "equity": {"vulnerability_strata": [
        {"name": "elderly", "column": "ses_age_share_ge65", "direction": "high",
         "quantile": 0.75, "level": "age"}]}}
    run_equity(cfg, "vuln", tmp_path)

    vuln = pd.read_csv(out / "equity_vulnerability.csv")
    assert list(vuln.stratum) == ["overall", "elderly"]
    elderly = vuln[vuln.stratum == "elderly"].iloc[0]
    assert elderly.mean_dep_everyday_ratio > 1.0
    assert elderly.hh_share_gap > 0


def test_ses_covariates_allow_list_restricts_regressions(tmp_path):
    df = _disjoint_suppression_surfaces()
    _write_surfaces(tmp_path, "allow", df)
    cfg = {**_base_cfg(), "equity": {"ses_covariates": ["ses_age_share_ge65"]}}
    run_equity(cfg, "allow", tmp_path)

    regs = pd.read_csv(tmp_path / "data" / "derived" / "allow" / "equity_regressions.csv")
    ses_terms = set(regs[regs.model == "ses"].term)
    assert "ses_age_share_ge65" in ses_terms
    assert "ses_net_rent_qm" not in ses_terms  # excluded by the allow-list


def test_equity_indices_record_the_units_of_every_reported_level(tmp_path):
    """A level without its units invites the cross-regime magnitude comparison
    the standardisation layer exists to forbid (methods.md §3a/§3c)."""
    from depacc.config import load_config

    rng = np.random.default_rng(5)
    n = 200
    surfaces = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "deprivation_everyday": rng.uniform(0, 1, n),
        "deprivation_emergency": rng.uniform(0, 1, n),
    })
    out = _write_surfaces(tmp_path, "units", surfaces)
    cfg = {**load_config(), "output": {"root": "data/derived"}}
    run_equity(cfg, "units", tmp_path)

    indices = pd.read_csv(out / "equity_indices.csv").set_index("regime")
    assert "saturation ceiling" in indices.loc["everyday", "units"]
    # The emergency DCF is anchored, so its level is in multiples of g(15 min).
    assert "multiples of g(15 min)" in indices.loc["emergency", "units"]


def test_shipped_defaults_stratify_every_city_on_the_census_age_layer():
    """The EU census layer is what makes vulnerability available for all
    cities, so the default strata must reference ses_census_* columns and label
    their level so no cross-city comparison pools them with a Tier-2 layer."""
    from depacc.config import load_config

    for city in (None, "hamburg"):
        strata = load_config(city)["equity"]["vulnerability_strata"]
        census = [s for s in strata if s["level"] == "age_census"]
        assert {s["column"] for s in census} == {"ses_census_share_ge65",
                                                "ses_census_share_u15"}
    # Hamburg additionally carries its finer national layer, kept apart.
    hh = load_config("hamburg")["equity"]["vulnerability_strata"]
    assert {s["level"] for s in hh} == {"age_census", "age_national",
                                        "income_tier2"}


# ---------------------------------------------------------------------------
# A degenerate covariate must never take the stage down. statsmodels raises
# MissingDataError("exog contains inf or nans"), which derives from Exception —
# NOT ValueError — so it escaped the caller's guard and aborted the run.
# ---------------------------------------------------------------------------

def test_missing_data_error_is_not_a_value_error():
    """The premise of the bug, pinned: if statsmodels ever makes this a
    ValueError the guard below is redundant, but until then it is required."""
    from statsmodels.tools.sm_exceptions import MissingDataError

    from depacc.equity.pipeline import _regression_errors

    assert not issubclass(MissingDataError, ValueError)
    assert MissingDataError in _regression_errors()


def test_zero_variance_covariate_raises_a_handled_error():
    """A constant covariate standardises to 0/0 = NaN for every row. Refuse it
    by name, with an error type the caller already handles."""
    from depacc.equity.regressions import gradient_regression

    rng = np.random.default_rng(11)
    n = 100
    df = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "deprivation_everyday": rng.uniform(0, 1, n),
        "ses_flat": np.full(n, 0.25),        # constant on its whole support
    })
    with pytest.raises(ValueError, match="zero variance"):
        gradient_regression(df, "deprivation_everyday", ["ses_flat"])


def test_equity_survives_a_constant_covariate_and_keeps_the_others(tmp_path, capsys):
    """The regression that cannot be estimated is skipped with a NOTE; every
    other covariate, the density gradient and the indices still land."""
    rng = np.random.default_rng(12)
    n = 300
    age65 = np.linspace(0.05, 0.45, n)
    surfaces = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "deprivation_everyday": 0.2 + 0.5 * age65 + rng.normal(0, 0.02, n),
        "deprivation_emergency": rng.uniform(0, 1, n),
        "ses_census_share_ge65": age65,
        # Degenerate in two different ways: constant, and constant-on-support.
        "ses_census_employment_share": np.full(n, 0.63),
        "ses_flat_with_gaps": np.where(np.arange(n) % 2 == 0, 0.5, np.nan),
    })
    out = _write_surfaces(tmp_path, "degen", surfaces)
    cfg = {**_base_cfg(), "equity": {"ses_covariates": [
        "ses_census_share_ge65", "ses_census_employment_share",
        "ses_flat_with_gaps"]}}

    run_equity(cfg, "degen", tmp_path)   # must NOT raise

    log = capsys.readouterr().out
    # The support gate now catches a constant covariate before statsmodels sees
    # it, so the message is the gate's rather than the regression's. The
    # regression-level guard (_regression_errors) still matters for a covariate
    # that passes the gate and fails inside statsmodels anyway.
    assert "ses_census_employment_share" in log and "unusable" in log
    regs = pd.read_csv(out / "equity_regressions.csv")
    terms = set(regs[regs.model == "ses"].term)
    assert "ses_census_share_ge65" in terms          # the good one survived
    assert "ses_census_employment_share" not in terms
    assert "ses_flat_with_gaps" not in terms
    # The density gradient and both regimes are still there.
    assert set(regs[regs.model == "density"].regime) == {"everyday", "emergency"}
    assert (out / "equity_indices.csv").exists()


def test_gradient_regression_rejects_a_non_finite_design_matrix():
    """Belt and braces: statsmodels must never see a non-finite exog, whatever
    route produced it."""
    from depacc.equity.regressions import gradient_regression

    rng = np.random.default_rng(13)
    n = 60
    df = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "deprivation_everyday": rng.uniform(0, 1, n),
        # inf is stripped up front (replace -> NaN -> dropna), so a regression
        # on the remaining rows is either clean or refused.
        "ses_x": np.where(np.arange(n) < 3, np.inf, rng.uniform(0, 1, n)),
    })
    fit = gradient_regression(df, "deprivation_everyday", ["ses_x"])
    assert fit.n.iloc[0] == n - 3
    assert np.isfinite(fit.coef).all()


# --------------------------------------------------------------------------- #
# Support gate                                                                #
# --------------------------------------------------------------------------- #
def _thin_covariate_surfaces(n=400):
    rng = np.random.default_rng(3)
    df = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "deprivation_everyday": rng.uniform(0, 1, n),
        "deprivation_emergency": rng.uniform(0, 30, n),
        "ses_dense_share": rng.uniform(0, 0.4, n),      # full support: usable
        "ses_thin_share": np.nan,                        # 2% support: dropped
        "ses_flat_share": 0.0,                           # constant: dropped
        "ses_net_rent_qm": rng.uniform(6, 14, n),        # full support: usable
    })
    df.loc[: int(0.02 * n), "ses_thin_share"] = rng.uniform(0, 1, int(0.02 * n) + 1)
    return df


def test_support_gate_drops_thin_and_constant_covariates(tmp_path, capsys):
    """Hamburg's two failure modes in one table: a covariate published on 0.2 %
    of cells and constant there (the census employment share, EMP being
    voluntary), and one on 2.6 % that was still supplying the LARGEST everyday
    gradient in equity_regressions.csv (the Zensus vacancy rate). Neither
    describes the city, and nothing downstream told them apart from a covariate
    on the whole FUA."""
    out = _write_surfaces(tmp_path, "gated", _thin_covariate_surfaces())
    run_equity(_base_cfg(), "gated", tmp_path)

    coverage = pd.read_csv(out / "equity_ses_coverage.csv").set_index("column")
    assert coverage.loc["ses_dense_share", "cell_share"] == pytest.approx(1.0)
    assert coverage.loc["ses_thin_share", "cell_share"] < 0.05
    assert coverage.loc["ses_flat_share", "n_distinct"] == 1

    terms = set(pd.read_csv(out / "equity_regressions.csv").term)
    assert "ses_dense_share" in terms and "ses_net_rent_qm" in terms
    assert "ses_thin_share" not in terms      # below min_covariate_valid_share
    assert "ses_flat_share" not in terms      # no variance to estimate
    assert "unusable" in capsys.readouterr().out


def test_support_gate_also_governs_the_rank_column(tmp_path):
    """The concentration index must not rank on a column the gate rejected —
    the default ses_rank_column is the census employment share, which is exactly
    the column that fails the gate in Germany."""
    df = _thin_covariate_surfaces()
    out = _write_surfaces(tmp_path, "ranked", df)
    cfg = {**_base_cfg(), "equity": {"ses_rank_column": "ses_thin_share"}}
    run_equity(cfg, "ranked", tmp_path)
    indices = pd.read_csv(out / "equity_indices.csv")
    # Falls through to the rent heuristic rather than ranking on 2% of cells.
    assert set(indices["concentration_ses_col"]) == {"ses_net_rent_qm"}
