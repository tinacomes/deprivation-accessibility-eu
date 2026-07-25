"""Equity stage: population-weighted indices per regime + Tier-2 gradient
regressions on SES covariates."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from depacc.equity.indices import concentration_index, weighted_gini, weighted_mean
from depacc.equity.regressions import density_gradient, gradient_regression
from depacc.ingest.pipeline import derived_dir


def _resolve_rank_column(equity_cfg: dict, ses_cols: list[str]) -> str | None:
    """SES ranking column for the concentration index: an explicit
    ``equity.ses_rank_column`` config key wins; otherwise fall back to the
    first income/rent/deprivation-index-like column by name."""
    col = equity_cfg.get("ses_rank_column")
    if col:
        if col in ses_cols:
            return col
        print(f"NOTE: equity.ses_rank_column '{col}' not present or below the "
              f"support gate; falling back to the name heuristic")
    return next(
        (c for c in ses_cols if any(k in c for k in ("income", "rent", "filosofi", "imd"))),
        None,
    )


def _covariate_coverage(surfaces: pd.DataFrame, cols: list[str],
                        pop: pd.Series) -> pd.DataFrame:
    """Per-covariate support: cells and population share carrying a value.

    Written next to the regressions because a gradient's credibility rests on it
    and the coefficient alone hides it. Hamburg's run made both failure modes
    visible in one table: ``ses_census_employment_share`` is non-null on 295 of
    176 137 cells (EMP is voluntary under Reg. 2018/1799 and DE did not report
    it), while ``ses_vacancy_rate_Leerstandsquote`` produced the LARGEST everyday
    gradient in the table off 4633 cells — 2.6 % of the FUA, and Destatis
    publishes tenure preferentially where there is dense rental housing, so the
    support is not a random 2.6 %.
    """
    p = pd.to_numeric(pop, errors="coerce").fillna(0.0)
    total_pop = float(p[p > 0].sum())
    if not cols:  # a city with no SES layer at all — an empty table, not a crash
        return pd.DataFrame(columns=["column", "n_cells", "cell_share",
                                     "pop_share", "n_distinct"])
    rows = []
    for col in cols:
        ok = surfaces[col].notna().to_numpy()
        rows.append({
            "column": col,
            "n_cells": int(ok.sum()),
            "cell_share": float(ok.mean()) if len(ok) else float("nan"),
            "pop_share": (float(p.to_numpy()[ok].sum()) / total_pop
                          if total_pop > 0 else float("nan")),
            "n_distinct": int(surfaces.loc[ok, col].nunique()),
        })
    return pd.DataFrame(rows)


def _regression_errors() -> tuple[type[BaseException], ...]:
    """Exception types a single gradient regression may legitimately fail with.

    ``statsmodels.tools.sm_exceptions.MissingDataError`` derives straight from
    ``Exception``, NOT from ``ValueError``, so listing only (ValueError,
    ImportError) let it escape and abort the whole equity stage — one degenerate
    covariate took the run down with it. A regression that cannot be estimated
    must always degrade to a NOTE: the other covariates and the other regime are
    still valid outputs.
    """
    errors: tuple[type[BaseException], ...] = (ValueError, ImportError)
    try:
        from statsmodels.tools.sm_exceptions import MissingDataError
    except ImportError:
        return errors
    return errors + (MissingDataError,)


def _regime_units(cfg: dict, regime: str) -> str:
    """Units of the regime's deprivation surface, recorded next to every
    reported level. The everyday DLF is a fraction of its saturation ceiling
    while the emergency DCF is unbounded (in multiples of its reporting anchor
    when ``deprivation.emergency.reference_time_min`` is set, in arbitrary
    relative units otherwise) — so a ``weighted_mean`` of 0.21 and one of 0.03
    are NOT on the same scale, and the column says so. Empty when the config
    carries no deprivation spec (unit tests on synthetic surfaces)."""
    from depacc.config import ConfigError, deprivation_spec
    from depacc.deprivation.functions import DeprivationFunction

    try:
        return DeprivationFunction.from_spec(deprivation_spec(cfg, regime)).units
    except (ConfigError, KeyError, TypeError):
        return ""


def run_equity(cfg: dict, city: str, root: Path) -> None:
    out = derived_dir(cfg, city, root)
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    pop = surfaces["population"]
    ses_cols = sorted(c for c in surfaces.columns if c.startswith("ses_"))
    equity_cfg = cfg.get("equity", {}) or {}

    # Support gate, applied BEFORE anything picks a column. A covariate on a
    # small, non-randomly-published subsample yields a p-value that describes
    # that subsample and not the FUA, and nothing downstream tells it apart from
    # a covariate on the whole city. The coverage table is written either way.
    min_share = float(equity_cfg.get("min_covariate_valid_share", 0.2))
    usable, support = [], _covariate_coverage(surfaces, ses_cols, pop)
    support.to_csv(out / "equity_ses_coverage.csv", index=False)
    support = support.set_index("column")
    for col in ses_cols:
        share = float(support.loc[col, "cell_share"])
        if share < min_share:
            print(f"NOTE: SES column '{col}' unusable — carries a value on "
                  f"{share:.1%} of cells (n={int(support.loc[col, 'n_cells'])}), "
                  f"below equity.min_covariate_valid_share={min_share:.0%}")
        elif int(support.loc[col, "n_distinct"]) < 2:
            print(f"NOTE: SES column '{col}' unusable — constant over its "
                  f"{int(support.loc[col, 'n_cells'])} valid cells")
        else:
            usable.append(col)

    ses_rank_col = _resolve_rank_column(equity_cfg, usable)
    # SES gradient covariates: an explicit allow-list (intersected with what is
    # usable) or every usable ses_ column. Each is regressed UNIVARIATELY below.
    covariates = [c for c in (equity_cfg.get("ses_covariates") or usable)
                  if c in usable]

    rows = []
    for regime in ("everyday", "emergency"):
        dep = surfaces[f"deprivation_{regime}"]
        row = {
            "regime": regime,
            "weighted_mean": weighted_mean(dep, pop),
            "gini": weighted_gini(dep, pop),
            "units": _regime_units(cfg, regime),
        }
        if ses_rank_col:
            row["concentration_index"] = concentration_index(
                dep, surfaces[ses_rank_col], pop
            )
            row["concentration_ses_col"] = ses_rank_col
        rows.append(row)
    indices = pd.DataFrame(rows)
    indices.to_csv(out / "equity_indices.csv", index=False)
    print(indices.to_string(index=False))

    reg_errors = _regression_errors()
    reg_frames = []
    for regime in ("everyday", "emergency"):
        outcome = f"deprivation_{regime}"
        try:
            d = density_gradient(surfaces, outcome).assign(regime=regime, model="density")
            reg_frames.append(d)
        except reg_errors as err:
            print(f"NOTE: density gradient skipped for {regime}: {err}")
        # One univariate regression PER covariate with pairwise deletion: a
        # single-column listwise regression over every ses_ column collapses to
        # zero complete cells whenever the themes are suppressed on disjoint
        # cells (Zensus net rent exists only where there is rental housing,
        # vacancy elsewhere), so each covariate must stand on its own support.
        for col in covariates:
            try:
                g = gradient_regression(surfaces, outcome, [col]).assign(
                    regime=regime, model="ses")
                reg_frames.append(g)
            except reg_errors as err:
                print(f"NOTE: SES regression skipped for {regime}/{col}: "
                      f"{type(err).__name__}: {err}")
    if reg_frames:
        regs = pd.concat(reg_frames, ignore_index=True)
        regs.to_csv(out / "equity_regressions.csv", index=False)
        slopes = regs[regs.term != "const"]
        print(slopes[["regime", "model", "term", "coef", "p"]].to_string(index=False))

    # Vulnerability-stratified deprivation (needs the divergence typology for
    # the HH share). Skipped cleanly when no strata are configured or the
    # typology has not been written yet.
    strata = equity_cfg.get("vulnerability_strata") or []
    typ_path = out / "typology.parquet"
    if strata and typ_path.exists():
        from depacc.equity.vulnerability import vulnerability_strata

        typology = pd.read_parquet(typ_path).reindex(surfaces.index)
        hh_key = str(equity_cfg.get("vulnerability_hh_threshold", 50))
        vuln = vulnerability_strata(surfaces, typology, strata, hh_key=hh_key)
        vuln.to_csv(out / "equity_vulnerability.csv", index=False)
        print(vuln.to_string(index=False))
    elif strata:
        print("NOTE: vulnerability_strata configured but typology.parquet "
              "absent; run the divergence stage first")
