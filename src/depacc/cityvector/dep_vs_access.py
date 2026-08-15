"""Deprivation vs pure access — what the deprivation layer adds (and costs).

The study's outcomes are *deprivation* surfaces: anchored, convex/S-shaped
loss functions of effective travel time (methods §3). A referee will ask the
obvious question — would the headlines survive if we dropped that layer and
regressed plain minutes instead? This module answers it in three moves, all
on the deprivation-function-free travel-time indicators that every city
already writes to ``accessibility_by_regime.csv``:

1. ``size_elasticity_contrast`` — the H1 size regressions re-run on median
   and mean minutes per regime, side by side with the deprivation outcomes,
   plus the deprivation-vs-time Gini correlations
   (``deprivation_vs_access.csv``). Robustness *and* added value: the signs
   agree, so the claims do not depend on the deprivation layer, while the
   deprivation outcome is the better-behaved regression (the loss function
   discounts welfare-irrelevant variation in the flat part of the curve).

   The everyday p90 minutes column is deliberately NOT regressed: above the
   walk cutoff the everyday composite time behaves as a count of unmet
   service categories rather than a travel time (methods §4.2), and the
   published p90 is conditional on reachability. Median and mean are the
   honest access companions.

2. ``desert_contrast`` — for the flagged emergency-desert cities, their
   access ratio vs the sample next to their deprivation ratio
   (``desert_access_contrast.csv``). This is where the two framings part
   company: a desert whose *median* minute count is ordinary is invisible to
   an access average, and only the convex, clinically anchored DCF — which
   prices the tail — exposes it.

3. ``scaling_by_grade`` — the emergency size gradient within each
   emergency-coverage grade, with a country-clustered slope-x-grade Wald
   test (``scaling_by_grade.csv`` + ``figures/scaling_by_coverage_grade.png``).
   The severity ordering, not city size, sets the level.

**Coverage grades.** The grade is the k-means severity ordering of §4.4 read
off the two clustering passes, never a hand-picked threshold:

* ``desert`` — the flagged outlier group of the main pass
  (``clustering._outlier_group``: the five emergency-desert capitals);
* ``partial desert`` — the smaller cluster of the *peeled* pass, i.e. the
  same axis at lower intensity;
* ``covered`` — everything else.

So the grades are exactly the 5 / 12 / 50 split that ``cluster_null.csv`` and
``cluster_null_peeled.csv`` document, and they change only when the
clustering changes. Cities are graded ``covered`` when the peeled pass did
not run (too few cities, or no flagged group).

All estimation is cross-sectional space-for-time and clusters on country,
like the rest of the cityvector stage.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ACCESS_TABLE = "accessibility_by_regime.csv"
SERVICE_TABLE = "accessibility_by_service.csv"
GRADE_ORDER = ("covered", "partial desert", "desert")
INFERENCE_NOTE = ("log-log, country-clustered SE; "
                  "cross-sectional space-for-time")
MIN_CITIES = 8


# --------------------------------------------------------------------------
# access indicators (deprivation-function-free)
# --------------------------------------------------------------------------

def access_indicators(derived: Path, cities: list[str]) -> pd.DataFrame:
    """One row per city of travel-time indicators per regime, read from the
    per-city ``accessibility_by_regime.csv`` (minutes, no deprivation
    function anywhere in them)."""
    rows = []
    for city in cities:
        path = Path(derived) / city / ACCESS_TABLE
        if not path.exists():
            continue
        table = pd.read_csv(path)
        row: dict[str, object] = {"city": city}
        for regime in ("everyday", "emergency"):
            sel = table[table["regime"].astype(str) == regime]
            if sel.empty:
                continue
            r = sel.iloc[0]
            row[f"{regime}_median_time"] = float(r["pop_median_time_min"])
            row[f"{regime}_mean_time"] = float(r["pop_mean_time_min"])
            row[f"{regime}_p90_time"] = float(r["pop_p90_time_min_reachable"])
        rows.append(row)
    return pd.DataFrame(rows)


SERVICE_COLUMNS = ("n_facilities", "pop_median_time_min", "pop_mean_time_min",
                   "pop_share_beyond_15min", "pop_share_beyond_30min",
                   "pop_service_deprived_share", "unreachable_pop_share")


def service_accessibility(derived: Path, cities: pd.DataFrame
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-service travel times and facility counts, per city and pooled.

    The methods section needs a sentence like "we found a median of 1 598
    GPs per FUA, at a population-weighted median walk of 5.8 minutes", and a
    referee will want the per-city version to check that no city's facility
    extraction collapsed. Neither existed: `accessibility_by_service.csv` is
    written per city and never pooled.

    Returns ``(per_city, pooled)``. Pooling is over CITIES, not over cells:
    each city contributes one observation per service, so a 12.9 M FUA and a
    101 k one weigh the same. That is the right unit for "what does a
    European city look like", and it is not a population-weighted European
    average — do not report it as one.
    """
    frames = []
    for city in cities["city"].astype(str):
        path = Path(derived) / city / SERVICE_TABLE
        if not path.exists():
            continue
        table = pd.read_csv(path)
        table = table[table["level"].astype(str) == "service"]
        if table.empty:
            continue
        frames.append(table.assign(city=city))
    if not frames:
        return pd.DataFrame(), pd.DataFrame()

    keep = ["city", "regime", "service",
            *[c for c in SERVICE_COLUMNS if c in frames[0].columns]]
    per_city = pd.concat(frames, ignore_index=True)[keep]
    meta = cities[["city", "name", "country"]] if "name" in cities.columns \
        else cities[["city", "country"]]
    per_city = meta.merge(per_city, on="city", how="right")
    per_city = per_city.sort_values(["regime", "service", "city"]) \
                       .reset_index(drop=True)

    rows = []
    for (regime, service), grp in per_city.groupby(["regime", "service"],
                                                   sort=False):
        row = {"regime": regime, "service": service,
               "n_cities": int(grp["city"].nunique())}
        for col in SERVICE_COLUMNS:
            if col not in grp.columns:
                continue
            vals = pd.to_numeric(grp[col], errors="coerce").dropna()
            if vals.empty:
                continue
            row[f"{col}_median"] = float(vals.median())
            row[f"{col}_min"] = float(vals.min())
            row[f"{col}_max"] = float(vals.max())
        rows.append(row)
    return per_city, pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 1. size elasticities: deprivation next to access
# --------------------------------------------------------------------------

def _clustered_loglog(df: pd.DataFrame, outcome: str) -> dict | None:
    """log(outcome) ~ log(population) with country-clustered SEs."""
    import statsmodels.api as sm

    sub = df.dropna(subset=[outcome, "population", "country"])
    sub = sub[(sub["population"] > 0) & (sub[outcome] > 0)]
    if len(sub) < MIN_CITIES or sub["country"].nunique() < 5:
        return None
    y = np.log(sub[outcome].values)
    X = sm.add_constant(np.log(sub["population"].values))
    fit = sm.OLS(y, X).fit(cov_type="cluster",
                           cov_kwds={"groups": sub["country"].values})
    return {"elasticity": float(fit.params[1]), "se": float(fit.bse[1]),
            "p": float(fit.pvalues[1]), "r2": float(fit.rsquared),
            "n_cities": int(len(sub))}


ACCESS_OUTCOMES = {
    "everyday": ("everyday_median_time", "everyday_mean_time"),
    "emergency": ("emergency_median_time", "emergency_mean_time",
                  "emergency_p90_time"),
}
DEPRIVATION_OUTCOMES = {"everyday": "mean_everyday",
                        "emergency": "mean_emergency"}


def size_elasticity_contrast(merged: pd.DataFrame) -> pd.DataFrame:
    """The H1 elasticities on deprivation and on plain minutes, plus the
    deprivation-vs-time Gini correlations."""
    from scipy import stats

    rows = []
    for regime, dep in DEPRIVATION_OUTCOMES.items():
        for kind, outcome in ([("deprivation", dep)]
                              + [("access", a)
                                 for a in ACCESS_OUTCOMES[regime]]):
            if outcome not in merged.columns:
                continue
            est = _clustered_loglog(merged, outcome)
            if est is None:
                continue
            rows.append({"block": "size_elasticity", "regime": regime,
                         "kind": kind, "outcome": outcome, **est,
                         "inference": INFERENCE_NOTE})
    for regime in ("everyday", "emergency"):
        g, gt = f"gini_{regime}", f"gini_t_{regime}"
        if not {g, gt} <= set(merged.columns):
            continue
        sub = merged.dropna(subset=[g, gt])
        if len(sub) < MIN_CITIES:
            continue
        rows.append({
            "block": "gini_correlation", "regime": regime,
            "kind": "deprivation_vs_time", "outcome": f"{g}~{gt}",
            "elasticity": float(stats.pearsonr(sub[g], sub[gt])[0]),
            "se": np.nan,
            "p": float(stats.spearmanr(sub[g], sub[gt])[0]),
            "r2": np.nan, "n_cities": int(len(sub)),
            "inference": "elasticity column = Pearson r; "
                         "p column = Spearman rho",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 2. the deserts: invisible to access averages
# --------------------------------------------------------------------------

def desert_contrast(merged: pd.DataFrame) -> pd.DataFrame:
    """Access-vs-deprivation ratios for the flagged emergency-desert cities,
    each against the sample median."""
    needed = {"emergency_median_time", "mean_emergency", "coverage_grade"}
    if not needed <= set(merged.columns):
        return pd.DataFrame()
    deserts = merged[merged["coverage_grade"] == "desert"]
    if deserts.empty:
        return pd.DataFrame()
    t_med = float(merged["emergency_median_time"].median())
    d_med = float(merged["mean_emergency"].median())
    out = pd.DataFrame({
        "city": deserts["city"], "country": deserts["country"],
        "emergency_median_time_min": deserts["emergency_median_time"],
        "median_time_ratio_vs_sample":
            deserts["emergency_median_time"] / t_med,
        "emergency_p90_time_min": deserts.get("emergency_p90_time"),
        "mean_emergency_deprivation": deserts["mean_emergency"],
        "deprivation_ratio_vs_sample": deserts["mean_emergency"] / d_med,
        "sample_median_time_min": t_med,
        "sample_median_deprivation": d_med,
    })
    return out.sort_values("mean_emergency_deprivation", ascending=False) \
              .reset_index(drop=True)


# --------------------------------------------------------------------------
# 3. coverage grades and the slope x grade interaction
# --------------------------------------------------------------------------

def coverage_grades(vectors: pd.DataFrame,
                    peeled: pd.DataFrame | None) -> pd.Series:
    """The severity ordering as a per-city label (see the module docstring:
    desert = main-pass outlier group, partial desert = peeled-pass smaller
    cluster, covered = the rest)."""
    from depacc.cityvector.clustering import _outlier_group

    grade = pd.Series("covered", index=vectors.index, dtype=object)
    if peeled is not None and not peeled.empty \
            and "cluster_kmeans" in peeled.columns:
        sizes = peeled["cluster_kmeans"].value_counts()
        if len(sizes) > 1:
            small = peeled.loc[peeled["cluster_kmeans"] == sizes.idxmin(),
                               "city"]
            grade[vectors["city"].isin(set(small))] = "partial desert"
    flagged = _outlier_group(vectors)
    grade[flagged.values] = "desert"
    return grade


def scaling_by_grade(merged: pd.DataFrame,
                     outcome: str = "mean_emergency") -> pd.DataFrame:
    """Within-grade size elasticities plus the country-clustered Wald test on
    the slope-x-grade interaction. The within-grade rows are plain OLS: with
    5-50 cities per grade a cluster-robust SE on a handful of countries would
    be theatre — the citable inference is the interaction row."""
    import statsmodels.api as sm

    if "coverage_grade" not in merged.columns or outcome not in merged.columns:
        return pd.DataFrame()
    df = merged.dropna(subset=[outcome, "population", "country",
                               "coverage_grade"])
    df = df[(df["population"] > 0) & (df[outcome] > 0)].reset_index(drop=True)
    if len(df) < MIN_CITIES:
        return pd.DataFrame()

    rows = []
    for grade in GRADE_ORDER:
        sub = df[df["coverage_grade"] == grade]
        if len(sub) < 3:
            continue
        fit = sm.OLS(np.log(sub[outcome].values),
                     sm.add_constant(np.log(sub["population"].values))).fit()
        rows.append({"grade": grade, "n_cities": int(len(sub)),
                     "elasticity": float(fit.params[1]),
                     "se": float(fit.bse[1]), "p": float(fit.pvalues[1]),
                     "note": "plain OLS within grade (small n)"})

    grades = [g for g in GRADE_ORDER if (df["coverage_grade"] == g).sum() >= 3]
    if len(grades) > 1:
        # ln pop is CENTRED so the grade dummies test a level shift at the
        # sample's mean city size (uncentred they would test it at a
        # population of one, which is an extrapolation, not a contrast).
        ln_pop = np.log(df["population"].values)
        ln_pop = ln_pop - ln_pop.mean()
        cols = [np.ones(len(df)), ln_pop]
        names = ["const", "ln_pop"]
        for grade in grades[1:]:
            d = (df["coverage_grade"] == grade).astype(float).values
            cols += [d, d * ln_pop]
            names += [f"grade[{grade}]", f"ln_pop:grade[{grade}]"]
        X = np.column_stack(cols)
        fit = sm.OLS(np.log(df[outcome].values), X).fit(
            cov_type="cluster", cov_kwds={"groups": df["country"].values})

        def _wald(prefix: str) -> float:
            idx = [i for i, n in enumerate(names) if n.startswith(prefix)]
            R = np.zeros((len(idx), X.shape[1]))
            for r, i in enumerate(idx):
                R[r, i] = 1.0
            return float(fit.wald_test(R, scalar=True).pvalue)

        # Both halves of the reading are reported: the grades separate the
        # LEVEL, they do not change the (absent) size gradient.
        rows.append({"grade": "grade level shift (at mean size)",
                     "n_cities": int(len(df)),
                     "elasticity": np.nan, "se": np.nan,
                     "p": _wald("grade["),
                     "note": "Wald on grade dummies at centred ln pop, "
                             "country-clustered"})
        rows.append({"grade": "interaction (slope x grade)",
                     "n_cities": int(len(df)),
                     "elasticity": np.nan, "se": np.nan,
                     "p": _wald("ln_pop:grade"),
                     "note": "Wald on interaction terms, country-clustered"})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Table 1 material
# --------------------------------------------------------------------------

DESCRIPTIVE_COLUMNS = ("mean_everyday", "mean_emergency", "gini_everyday",
                       "gini_emergency", "divergence_gap", "spearman_rho",
                       "compounding_pop_share_50", "compounding_intensity",
                       "pop_share_beyond_everyday_30",
                       "pop_share_beyond_emergency_30")


def _size_stratum(pop: float, bounds: list[float]) -> str:
    """Human label for the F.2 size stratum a city falls in."""
    def fmt(v: float) -> str:
        return f"{v/1e6:g}M" if v >= 1e6 else f"{v/1e3:g}k"

    edges = sorted(bounds)
    for lo, hi in zip(edges, edges[1:]):
        if pop < hi:
            lo_s, hi_s = fmt(lo), fmt(hi)
            # "100-250k" / "250k-1M" / "1-5M": drop the repeated unit suffix.
            if lo_s[-1] == hi_s[-1]:
                lo_s = lo_s[:-1]
            return f"{lo_s}-{hi_s}"
    return f">{fmt(edges[-1])}"


def city_descriptives(vectors: pd.DataFrame, region_of: dict[str, str],
                      bounds: list[float], decimals: int = 4,
                      per_service: pd.DataFrame | None = None
                      ) -> pd.DataFrame:
    """The per-city appendix table (Table 1 / SI): sample composition next to
    the headline indicators, largest city first.

    ``n_emergency_services`` counts how many of the two emergency services
    (ED hospital, ambulance station) OSM actually yielded for the city. It
    belongs in Table 1 rather than a footnote: the composite renormalises
    its weights over the services present (§4), so a city with one mapped
    service has an emergency surface measuring proximity to that service
    alone, and a reader comparing its level to a two-service city needs to
    know that from the table.
    """
    df = vectors.copy()
    df["region"] = df["country"].map(region_of)
    df["size_stratum"] = df["population"].map(
        lambda p: _size_stratum(float(p), bounds))
    if per_service is not None and not per_service.empty:
        counts = (per_service[per_service.regime == "emergency"]
                  .groupby("city").service.nunique())
        df["n_emergency_services"] = (df["city"].map(counts)
                                      .fillna(0).astype(int))
    keep = ["city", "name", "country", "region", "population", "size_stratum",
            *(["n_emergency_services"] if "n_emergency_services" in df else []),
            *[c for c in DESCRIPTIVE_COLUMNS if c in df.columns]]
    out = df[keep].sort_values("population", ascending=False)
    out["population"] = out["population"].round().astype("Int64")
    for col in DESCRIPTIVE_COLUMNS:
        if col in out.columns:
            out[col] = out[col].astype(float).round(decimals)
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------
# figure
# --------------------------------------------------------------------------

GRADE_STYLE = {
    "covered": ("#898781", "o"),
    "partial desert": ("#eb6834", "s"),
    "desert": ("#4a3aa7", "D"),
}


def _plot_scaling_by_grade(merged: pd.DataFrame, by_grade: pd.DataFrame,
                           figdir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from depacc.cityvector.clustering import _provenance_footer

    def _p(prefix: str) -> float | None:
        sel = by_grade[by_grade["grade"].str.startswith(prefix)]
        return float(sel["p"].iloc[0]) if not sel.empty else None

    p_level, p_inter = _p("grade level shift"), _p("interaction")
    bits = []
    if p_level is not None:
        bits.append(f"grade level shift p = {p_level:.1e}")
    if p_inter is not None:
        bits.append(f"slope-x-grade interaction p = {p_inter:.3f}")
    p_txt = "; ".join(bits) + " (country-clustered)" if bits else ""
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.2))
    for ax, regime in zip(axes, ("everyday", "emergency")):
        outcome = f"mean_{regime}"
        if outcome not in merged.columns:
            continue
        for grade in GRADE_ORDER:
            sub = merged[(merged["coverage_grade"] == grade)
                         & merged[outcome].gt(0)]
            if sub.empty:
                continue
            colour, marker = GRADE_STYLE[grade]
            ax.scatter(sub["population"], sub[outcome], s=42, marker=marker,
                       color=colour, alpha=0.85, edgecolors="none",
                       label=f"{grade} (n={len(sub)})", zorder=3)
            if len(sub) >= 3:
                b = np.polyfit(np.log(sub["population"]),
                               np.log(sub[outcome]), 1)
                xs = np.linspace(np.log(sub["population"].min()),
                                 np.log(sub["population"].max()), 20)
                ax.plot(np.exp(xs), np.exp(np.polyval(b, xs)),
                        color=colour, lw=1.8, zorder=2)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("FUA population")
        ax.set_ylabel(f"mean {regime} deprivation")
        ax.set_title(regime, fontsize=10)
        ax.legend(frameon=False, fontsize=8, loc="lower left")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.suptitle("Mean deprivation vs city size by emergency-coverage grade\n"
                 "(the k-means severity ordering: level is set by coverage "
                 f"class, not size; {p_txt})", fontsize=11)
    _provenance_footer(fig, merged)
    fig.tight_layout()
    fig.savefig(figdir / "scaling_by_coverage_grade.png", dpi=180,
                bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
# entry point (called from clustering.run_cross_city)
# --------------------------------------------------------------------------

def run_dep_vs_access(vectors: pd.DataFrame, derived: Path,
                      region_of: dict[str, str],
                      bounds: list[float] | None = None) -> None:
    """Write the deprivation-vs-access contrast tables, the coverage-graded
    scaling table and its figure, and the per-city descriptives table."""
    derived = Path(derived)
    access = access_indicators(derived, list(vectors["city"].astype(str)))
    if access.empty:
        print("NOTE: no accessibility_by_regime.csv found — "
              "deprivation-vs-access contrast skipped.")
        return
    peeled_path = derived / "cityvector_clustered_peeled.csv"
    peeled = pd.read_csv(peeled_path) if peeled_path.exists() else None
    merged = vectors.merge(access, on="city", how="left")
    merged["coverage_grade"] = coverage_grades(merged, peeled).values

    contrast = size_elasticity_contrast(merged)
    if not contrast.empty:
        contrast.to_csv(derived / "deprivation_vs_access.csv", index=False)
        show = contrast[contrast.block == "size_elasticity"]
        for r in show.itertuples():
            print(f"  dep-vs-access {r.regime:<9} {r.kind:<11} "
                  f"{r.outcome:<22} b={r.elasticity:+.3f} p={r.p:.4g} "
                  f"R2={r.r2:.3f}")

    deserts = desert_contrast(merged)
    if not deserts.empty:
        deserts.to_csv(derived / "desert_access_contrast.csv", index=False)
        print(f"  desert contrast: {len(deserts)} cities, median time "
              f"{deserts.median_time_ratio_vs_sample.min():.2f}-"
              f"{deserts.median_time_ratio_vs_sample.max():.2f}x sample vs "
              f"deprivation {deserts.deprivation_ratio_vs_sample.min():.2f}-"
              f"{deserts.deprivation_ratio_vs_sample.max():.2f}x")

    by_grade = scaling_by_grade(merged)
    if not by_grade.empty:
        by_grade.to_csv(derived / "scaling_by_grade.csv", index=False)
        print("  coverage grades: "
              + ", ".join(f"{g}={int((merged.coverage_grade == g).sum())}"
                          for g in GRADE_ORDER))
        figdir = derived / "figures"
        figdir.mkdir(parents=True, exist_ok=True)
        try:
            _plot_scaling_by_grade(merged, by_grade, figdir)
        except Exception as exc:                    # viz extra may be absent
            print(f"  NOTE: coverage-grade figure skipped ({exc})")

    per_city, pooled = service_accessibility(derived, vectors)

    if bounds:
        desc = city_descriptives(vectors, region_of, bounds,
                                 per_service=per_city)
        desc.to_csv(derived / "cities_descriptives.csv", index=False)
        print(f"  descriptives: {len(desc)} cities written to "
              "cities_descriptives.csv")
        if "n_emergency_services" in desc.columns:
            thin = desc[desc.n_emergency_services < 2]
            if not thin.empty:
                print(f"  NOTE: {len(thin)} cities have only one mapped "
                      f"emergency service: "
                      f"{', '.join(sorted(thin.city))}")

    if not pooled.empty:
        per_city.to_csv(derived / "accessibility_by_service_cities.csv",
                        index=False)
        pooled.to_csv(derived / "accessibility_by_service_pooled.csv",
                      index=False)
        print(f"  per-service accessibility: {len(pooled)} services over "
              f"{int(pooled.n_cities.max())} cities")
        for r in pooled.itertuples():
            print(f"    {r.service:<24} facilities median "
                  f"{r.n_facilities_median:>8.0f}  median time "
                  f"{r.pop_median_time_min_median:>5.1f} min")
