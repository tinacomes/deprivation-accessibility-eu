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
