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
        print(f"NOTE: equity.ses_rank_column '{col}' not present; "
              f"falling back to the name heuristic")
    return next(
        (c for c in ses_cols if any(k in c for k in ("income", "rent", "filosofi", "imd"))),
        None,
    )


def run_equity(cfg: dict, city: str, root: Path) -> None:
    out = derived_dir(cfg, city, root)
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    pop = surfaces["population"]
    ses_cols = sorted(c for c in surfaces.columns if c.startswith("ses_"))
    equity_cfg = cfg.get("equity", {}) or {}
    ses_rank_col = _resolve_rank_column(equity_cfg, ses_cols)
    # SES gradient covariates: an explicit allow-list (intersected with what is
    # present) or every ses_ column. Each is regressed UNIVARIATELY below.
    covariates = [c for c in (equity_cfg.get("ses_covariates") or ses_cols)
                  if c in surfaces.columns]

    rows = []
    for regime in ("everyday", "emergency"):
        dep = surfaces[f"deprivation_{regime}"]
        row = {
            "regime": regime,
            "weighted_mean": weighted_mean(dep, pop),
            "gini": weighted_gini(dep, pop),
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

    reg_frames = []
    for regime in ("everyday", "emergency"):
        outcome = f"deprivation_{regime}"
        try:
            d = density_gradient(surfaces, outcome).assign(regime=regime, model="density")
            reg_frames.append(d)
        except (ValueError, ImportError) as err:
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
            except (ValueError, ImportError) as err:
                print(f"NOTE: SES regression skipped for {regime}/{col}: {err}")
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
