"""Specification curve: the headline claims under EVERY deprivation
parameterisation, not just the baseline.

The deprivation score has free parameters (curvature, onset, saturation) and
Layer-2 swaps the functional form altogether. The per-city sensitivity tables
already evaluate every city under the same variant grid; this module turns
them from a defensive appendix into an active robustness argument by
re-estimating the cross-city claims once per variant:

* the size slopes of the everyday and emergency deprivation Ginis
  (country-clustered SEs, as in cityvector/inference.py), and
* the regional permutation contrasts for the emergency Gini and the
  divergence gap (permutation over whole countries).

Rank-based outcomes (coupling rho, the LL/HL/LH/HH typology at a fixed
threshold) are NEAR-invariant under these variants — every deprivation
function in the grid is strictly increasing in travel time, so per-service
ranks never move; the multi-service composite can drift slightly because a
curvature change reweights how the services mix (the per-city flip-cell and
share-envelope tables measure that drift). The curve therefore covers the
claims the parameters bend materially: the Gini-based ones.

The result reads like: "the everyday-Gini size slope is +X to +Y and
significant under all N parameterisations" — or it is not, and we learn that
before a reviewer does.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from depacc.cityvector.inference import SEED, _permutation_p

SPEC_OUTCOMES = ("gini_everyday", "gini_emergency")
PERM_OUTCOMES = ("gini_emergency", "divergence_gap")
N_PERM_PER_VARIANT = 2_000     # per-variant curve; the baseline's primary
                               # p uses the full budget in inference.py
MIN_CITIES = 8


def load_variant_planes(sens_dir: Path) -> pd.DataFrame:
    """Stack every city's variant table (curvature + form_swap + baseline
    rows; the threshold axis is a different question — how high is high —
    and stays out of this curve). Keeps only variants present for EVERY
    city, so each variant's regression runs on the same sample."""
    frames = []
    for p in sorted(sens_dir.glob("*_deprivation_sensitivity.csv")):
        f = pd.read_csv(p)
        frames.append(f[f.axis.isin(["curvature", "form_swap"])])
    if not frames:
        return pd.DataFrame()
    stacked = pd.concat(frames, ignore_index=True)
    n_cities = stacked.city.nunique()
    coverage = stacked.groupby("variant")["city"].nunique()
    full = coverage[coverage == n_cities].index
    dropped = sorted(set(coverage.index) - set(full))
    if dropped:
        print(f"spec curve: {len(dropped)} variant(s) not present for all "
              f"{n_cities} cities, dropped: {dropped}")
    return stacked[stacked.variant.isin(full)]


def _clustered_elasticity(df: pd.DataFrame, outcome: str) -> dict | None:
    import statsmodels.api as sm

    sub = df.dropna(subset=[outcome, "population", "country"])
    sub = sub[(sub.population > 0) & (sub[outcome] > 0)]
    if len(sub) < MIN_CITIES or sub.country.nunique() < 5:
        return None
    fit = sm.OLS(np.log(sub[outcome].values),
                 sm.add_constant(np.log(sub.population.values))) \
        .fit(cov_type="cluster", cov_kwds={"groups": sub.country.values})
    return {"elasticity": float(fit.params[1]), "se": float(fit.bse[1]),
            "p": float(fit.pvalues[1]), "n_cities": len(sub)}


def specification_curve(planes: pd.DataFrame, cityplane: pd.DataFrame,
                        region_of: dict[str, str],
                        seed: int = SEED,
                        n_perm: int = N_PERM_PER_VARIANT) -> pd.DataFrame:
    """One row per (variant, outcome): the re-estimated size slope and the
    per-variant regional permutation p (for the outcomes in PERM_OUTCOMES)."""
    meta = cityplane[["city", "country", "population"]].drop_duplicates("city")
    rng = np.random.default_rng(seed)
    rows = []
    for variant, vf in planes.groupby("variant", sort=True):
        df = vf.merge(meta, on="city", how="inner")
        df["region"] = df.country.map(region_of)
        axis = vf.axis.iloc[0] if variant != "baseline" else "baseline"
        for outcome in SPEC_OUTCOMES:
            est = _clustered_elasticity(df, outcome)
            if est is None:
                continue
            row = {"variant": variant, "axis": axis, "outcome": outcome, **est}
            if outcome in PERM_OUTCOMES:
                sub = df.dropna(subset=[outcome, "region"])
                cm = sub.groupby("country")[outcome].mean()
                cr = sub.groupby("country")["region"].first()
                row["p_regional_permutation"] = _permutation_p(
                    cm, cr, rng, n_perm)
            rows.append(row)
        # divergence_gap has no meaningful elasticity (signed, spans zero) —
        # only its regional permutation contrast rides the curve.
        sub = df.dropna(subset=["divergence_gap", "region"])
        if len(sub) >= MIN_CITIES:
            cm = sub.groupby("country")["divergence_gap"].mean()
            cr = sub.groupby("country")["region"].first()
            rows.append({"variant": variant, "axis": axis,
                         "outcome": "divergence_gap",
                         "elasticity": np.nan, "se": np.nan, "p": np.nan,
                         "n_cities": len(sub),
                         "p_regional_permutation": _permutation_p(
                             cm, cr, rng, n_perm)})
    return pd.DataFrame(rows)


def plot_spec_curve(curve: pd.DataFrame, figdir: Path) -> None:
    """Classic specification-curve panel per Gini outcome: variants ordered
    by estimate, point + 95 % CI whisker (country-clustered), baseline
    ringed. A claim is robust when the whole curve sits on one side of
    zero."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import stats

    AXIS_COLOUR = {"baseline": "#0b0b0b", "curvature": "#2a78d6",
                   "form_swap": "#eb6834"}
    outcomes = [o for o in SPEC_OUTCOMES
                if not curve[curve.outcome == o].elasticity.isna().all()]
    if not outcomes:
        return
    fig, axes = plt.subplots(len(outcomes), 1,
                             figsize=(7.4, 2.9 * len(outcomes)), sharex=False)
    for ax, outcome in zip(np.atleast_1d(axes), outcomes):
        sub = curve[(curve.outcome == outcome)
                    & curve.elasticity.notna()].sort_values("elasticity") \
            .reset_index(drop=True)
        t95 = stats.t.ppf(0.975, np.maximum(sub.n_cities - 2, 2))
        for i, r in sub.iterrows():
            colour = AXIS_COLOUR.get(r.axis, "#898781")
            ax.vlines(i, r.elasticity - t95[i] * r.se,
                      r.elasticity + t95[i] * r.se,
                      color=colour, lw=1.4, zorder=2)
            ax.scatter(i, r.elasticity, c=colour, s=26, zorder=3)
            if r.variant == "baseline":
                ax.scatter(i, r.elasticity, facecolors="none",
                           edgecolors="#0b0b0b", s=120, linewidths=1.2,
                           zorder=4)
        ax.axhline(0, color="0.75", lw=1, ls="--", zorder=1)
        ax.set_xticks(range(len(sub)), sub.variant, rotation=60,
                      ha="right", fontsize=6.5)
        ax.set_ylabel(f"{outcome}\nsize slope (per ln pop)", fontsize=8.5)
        ax.tick_params(labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, axis="y", lw=0.4, alpha=0.35)
        ax.set_axisbelow(True)
    handles = [plt.Line2D([], [], color=c, marker="o", ls="-", lw=1.4)
               for c in AXIS_COLOUR.values()]
    np.atleast_1d(axes)[0].legend(handles, list(AXIS_COLOUR),
                                  frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Specification curve: size slopes of the deprivation Ginis\n"
                 "under every deprivation parameterisation "
                 "(whisker = 95 % CI, country-clustered; ring = baseline)",
                 fontsize=10, y=1.0)
    fig.tight_layout()
    fig.savefig(figdir / "specification_curve.png", dpi=180,
                bbox_inches="tight")
    plt.close(fig)


def run_spec_curve(derived: Path, region_of: dict[str, str]) -> None:
    """Orchestrator for the collect flow: variant tables from
    derived/sensitivity (unioned across runs by the persist import),
    city metadata from the union cityplane."""
    sens_dir = derived / "sensitivity"
    plane_path = derived / "cityplane.csv"
    if not sens_dir.exists() or not plane_path.exists():
        return
    planes = load_variant_planes(sens_dir)
    if planes.empty or planes.city.nunique() < MIN_CITIES:
        print(f"spec curve skipped: "
              f"{0 if planes.empty else planes.city.nunique()} cities with "
              f"variant tables (needs >= {MIN_CITIES})")
        return
    curve = specification_curve(planes, pd.read_csv(plane_path), region_of)
    if curve.empty:
        return
    curve.to_csv(sens_dir / "specification_curve.csv", index=False)
    plot_spec_curve(curve, sens_dir)
    for outcome in SPEC_OUTCOMES:
        sub = curve[(curve.outcome == outcome) & curve.elasticity.notna()]
        if sub.empty:
            continue
        sig = (sub.p < 0.05).sum()
        print(f"spec curve {outcome}: slope {sub.elasticity.min():+.3f} to "
              f"{sub.elasticity.max():+.3f} across {len(sub)} variants, "
              f"significant in {sig}/{len(sub)}")
    dg = curve[(curve.outcome == "divergence_gap")]
    if not dg.empty:
        p = dg.p_regional_permutation
        print(f"spec curve divergence_gap regional contrast: p_perm "
              f"{p.min():.4f} to {p.max():.4f} across {len(dg)} variants")
