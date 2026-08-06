"""Cross-city clustering (guarded) and the size-gradient trajectory read.

Clustering accepts ONLY a ScaledFeatures token, so a raw cross-city matrix
cannot reach k-means/agglomerative through the signature. k is chosen by
silhouette; a bootstrap over cities reports label stability (adjusted Rand).
All inference is cross-sectional space-for-time.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from depacc.cityvector.scaling_features import ScaledFeatures, scale_features

MIN_CITIES = 5

# Features holding a population share beyond a travel-time threshold. These are
# zero-inflated: in most cities essentially NOBODY lives beyond the outer
# emergency thresholds (67-city IQR of the beyond-60-min share: 0.002), so
# robust median/IQR scaling turns the few cities with real tails (8-20 % of
# population) into 30-sigma-equivalent outliers, and the k=2 silhouette (0.84)
# becomes an outlier-separation artefact of the scaler. log1p on the percentage
# keeps zero at zero and orders tails honestly; the separation that survives it
# (silhouette 0.65 on the full sample) is a data property, not a scaler
# property.
TAIL_SHARE_PREFIX = "pop_share_beyond_"


def declump_tail_shares(vectors: pd.DataFrame,
                        feature_cols: list[str]) -> pd.DataFrame:
    """log1p-open the beyond-threshold share features (see TAIL_SHARE_PREFIX)."""
    out = vectors.copy()
    for c in feature_cols:
        if c.startswith(TAIL_SHARE_PREFIX) and c in out.columns:
            out[c] = np.log1p(out[c].astype(float) * 100.0)
    return out


def _require_scaled(scaled) -> None:
    if not isinstance(scaled, ScaledFeatures):
        raise TypeError(
            "clustering requires a ScaledFeatures token from scale_features(); "
            "a raw/unscaled matrix must not reach the clustering functions"
        )


def choose_k_and_cluster(scaled: ScaledFeatures, k_range=(2, 6),
                         bootstrap: int = 50, random_state: int = 0) -> dict:
    """k-means (k by silhouette) + agglomerative on the scaled matrix, with a
    bootstrap stability (ARI) check. Returns labels + diagnostics."""
    _require_scaled(scaled)
    from sklearn.cluster import AgglomerativeClustering, KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    X = scaled.matrix
    n = X.shape[0]
    lo, hi = k_range
    hi = min(hi, n - 1)
    if n < MIN_CITIES or hi < lo:
        return {"labels_kmeans": [np.nan] * n, "labels_ward": [np.nan] * n,
                "k": None, "silhouette": None, "stability_ari": None,
                "note": f"only {n} cities; clustering skipped (need >= {MIN_CITIES})"}

    best_k, best_sil, best_labels = None, -1.0, None
    for k in range(lo, hi + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit_predict(X)
        sil = silhouette_score(X, labels) if len(set(labels)) > 1 else -1.0
        if sil > best_sil:
            best_k, best_sil, best_labels = k, sil, labels

    ward = AgglomerativeClustering(n_clusters=best_k, linkage="ward").fit_predict(X)

    # Bootstrap stability: recluster resampled cities, ARI vs full-sample labels.
    rng = np.random.default_rng(random_state)
    aris = []
    for _ in range(bootstrap):
        idx = rng.choice(n, size=n, replace=True)
        uniq = np.unique(idx)
        if len(uniq) < best_k + 1:
            continue
        bl = KMeans(n_clusters=best_k, n_init=5, random_state=random_state).fit_predict(X[uniq])
        aris.append(adjusted_rand_score(best_labels[uniq], bl))
    return {
        "labels_kmeans": best_labels.tolist(),
        "labels_ward": ward.tolist(),
        "k": int(best_k),
        "silhouette": float(best_sil),
        "stability_ari": float(np.mean(aris)) if aris else None,
    }


def size_gradient(vectors: pd.DataFrame,
                  outcomes=("divergence_gap", "spearman_rho",
                            "compounding_pop_share_50")) -> pd.DataFrame:
    """OLS of each divergence outcome on log10 population (HC1). Cross-sectional
    space-for-time trajectory read."""
    import statsmodels.api as sm

    rows = []
    for outcome in outcomes:
        if outcome not in vectors.columns:
            continue
        df = vectors[["log10_population", outcome]].replace(
            [np.inf, -np.inf], np.nan).dropna()
        # A non-finite or zero-variance regressor makes statsmodels raise
        # MissingDataError, which is not a ValueError and would abort the whole
        # cross stage — the pilot's most valuable output — over one outcome.
        if len(df) < 4 or df["log10_population"].std(ddof=0) == 0:
            continue
        X = sm.add_constant(df["log10_population"])
        fit = sm.OLS(df[outcome], X).fit(cov_type="HC1")
        rows.append({
            "outcome": outcome,
            "slope_per_log10_pop": fit.params["log10_population"],
            "se": fit.bse["log10_population"],
            "p": fit.pvalues["log10_population"],
            "n_cities": len(df),
            "r2": fit.rsquared,
            "inference": "cross-sectional space-for-time",
        })
    return pd.DataFrame(rows)


def run_cross_city(cfg: dict, root: Path, n_clusters: int | None = None) -> None:
    from depacc.cityvector.features import build_city_vectors, feature_columns

    derived = root / cfg["output"]["root"]
    vectors = build_city_vectors(cfg, root)
    if vectors.empty:
        print("NOTE: no city summaries yet (cityplane.csv absent/empty) — "
              "cross-city analysis skipped.")
        return
    real = vectors[~vectors.get("synthetic", False).astype(bool)] \
        if "synthetic" in vectors else vectors
    if len(real) < len(vectors):
        print(f"NOTE: {len(vectors) - len(real)} synthetic fixture(s) excluded")
    real = real.reset_index(drop=True)

    method = cfg.get("cityvector", {}).get("cross_city_scaler", "robust")
    ccfg = cfg.get("cityvector", {}).get("clustering", {})
    # The CSVs keep the raw shares; only the clustering distances see the
    # log1p-opened tails (see declump_tail_shares).
    scaled = scale_features(
        declump_tail_shares(real, feature_columns(cfg)),
        feature_columns(cfg), method=method,
        max_missing_share=float(cfg.get("cityvector", {})
                                .get("max_missing_share", 0.25)),
    )
    result = choose_k_and_cluster(
        scaled,
        k_range=tuple(ccfg.get("k_range", [2, 6])),
        bootstrap=int(ccfg.get("bootstrap", 50)),
        random_state=int(ccfg.get("random_state", 0)),
    )
    real["cluster_kmeans"] = result["labels_kmeans"]
    real["cluster_ward"] = result["labels_ward"]
    real.to_csv(derived / "cityvector_clustered.csv", index=False)
    if result.get("k"):
        print(f"clusters: k={result['k']} silhouette={result['silhouette']:.3f} "
              f"stability_ARI={result['stability_ari']}")
    else:
        print(result.get("note", "clustering skipped"))

    grad = size_gradient(real)
    if not grad.empty:
        grad.to_csv(derived / "size_gradient.csv", index=False)
        print(grad.to_string(index=False))

    # PNAS-style scaling regressions (existing module).
    from depacc.cityvector.scaling import regime_slope_difference, scaling_table

    tables = [scaling_table(real)]
    if real.country.nunique() > 1:
        tables.append(scaling_table(real, country_fe=True))
    scaling = pd.concat([t for t in tables if not t.empty], ignore_index=True) \
        if any(not t.empty for t in tables) else pd.DataFrame()
    if not scaling.empty:
        scaling.to_csv(derived / "scaling.csv", index=False)
    diffs = pd.concat([regime_slope_difference(real, m) for m in ("gini", "mean")],
                      ignore_index=True)
    if not diffs.empty:
        diffs.to_csv(derived / "regime_slope_difference.csv", index=False)

    _plot_cross_city(cfg, real, derived)


# Fixed macro-region colour order (validated all-pairs incl. CVD; the aqua
# slot's sub-3:1 surface contrast is relieved by the direct city labels).
# Marker shape is the secondary encoding so region identity never rides on
# colour alone. Regions outside the mapping fall back to grey/circle.
REGION_STYLE = {
    "North": ("#2a78d6", "o"),
    "West": ("#eb6834", "s"),
    "South": ("#1baf7a", "^"),
    "CEE": ("#4a3aa7", "D"),
}
FALLBACK_STYLE = ("#898781", "o")


def _region_lookup(cfg: dict) -> dict[str, str]:
    regions = (cfg.get("city_definition", {})
               .get("region_strata", {}) or {}).get("regions", {}) or {}
    return {cc: region for region, ccs in regions.items() for cc in ccs}


def _outlier_group(vectors: pd.DataFrame) -> pd.Series:
    """The smallest k-means cluster, when it is small enough to be a flagged
    GROUP rather than a partition (< a quarter of the sample). On the full
    sample this is the five emergency-desert capitals; the ring on the plots
    marks them without pretending the sample splits into two city types."""
    if "cluster_kmeans" not in vectors or vectors["cluster_kmeans"].isna().all():
        return pd.Series(False, index=vectors.index)
    sizes = vectors["cluster_kmeans"].value_counts()
    if len(sizes) < 2 or sizes.min() >= len(vectors) / 4:
        return pd.Series(False, index=vectors.index)
    return vectors["cluster_kmeans"] == sizes.idxmin()


def _label_set(vectors: pd.DataFrame, x: str, y: str,
               flagged: pd.Series, n_extreme: int = 2,
               n_pop: int = 3) -> set[int]:
    """Label only what a reader will ask about: the flagged group, the axis
    extremes and the largest cities — not all 67 names on top of each other."""
    idx = set(vectors.index[flagged])
    for col in (x, y):
        s = vectors[col].dropna().sort_values()
        idx.update(s.index[:n_extreme]); idx.update(s.index[-n_extreme:])
    idx.update(vectors["population"].nlargest(n_pop).index)
    return idx


def _region_scatter(ax, vectors: pd.DataFrame, x: str, y: str,
                    region_of: dict[str, str]) -> None:
    flagged = _outlier_group(vectors)
    labels = _label_set(vectors, x, y, flagged)
    for region, (colour, marker) in {**REGION_STYLE, None: FALLBACK_STYLE}.items():
        sel = (vectors.country.map(region_of) == region if region
               else ~vectors.country.map(region_of).isin(REGION_STYLE))
        if not sel.any():
            continue
        ax.scatter(vectors.loc[sel, x], vectors.loc[sel, y], c=colour,
                   marker=marker, s=42, linewidths=0, zorder=2,
                   label=region or "other")
    if flagged.any():
        ax.scatter(vectors.loc[flagged, x], vectors.loc[flagged, y],
                   facecolors="none", edgecolors="#0b0b0b", marker="o", s=150,
                   linewidths=1.2, zorder=3, label="emergency-desert group")
    for i in labels:
        r = vectors.loc[i]
        ax.annotate(r["name"], (r[x], r[y]), textcoords="offset points",
                    xytext=(5, 3), fontsize=7.5, color="0.25", zorder=4)


def _plot_cross_city(cfg: dict, vectors: pd.DataFrame, derived: Path) -> None:
    if len(vectors) < 2:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figdir = derived / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    region_of = _region_lookup(cfg)

    # Everyday-vs-emergency inequity plane. Colour = macro-region: the ANOVA
    # puts the regional contrasts at Cohen f 0.51-0.74, so region is the
    # pattern this plane actually shows; the k-means partition (62-vs-5) is an
    # outlier group, drawn as a ring, not as the colour dimension.
    fig, ax = plt.subplots(figsize=(6.8, 6.2))
    lim = max(vectors.gini_everyday.max(), vectors.gini_emergency.max()) * 1.15 + 1e-9
    ax.plot([0, lim], [0, lim], color="0.75", lw=1, ls="--", zorder=1)
    _region_scatter(ax, vectors, "gini_everyday", "gini_emergency", region_of)
    ax.set_xlabel("Gini of everyday deprivation")
    ax.set_ylabel("Gini of emergency deprivation")
    ax.set_title("Everyday-vs-emergency inequity plane (colour = macro-region)",
                 fontsize=10)
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(figdir / "cityplane.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # divergence_gap vs city size (space-for-time trajectory), with the fitted
    # slope drawn so the weak-but-directional reading (R^2 ~ 0.06) is explicit.
    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    _region_scatter(ax, vectors, "log10_population", "divergence_gap", region_of)
    ax.axhline(0, color="0.75", lw=1, ls="--")
    df = vectors[["log10_population", "divergence_gap"]].dropna()
    if len(df) >= 4:
        b, a = np.polyfit(df.log10_population, df.divergence_gap, 1)
        xs = np.linspace(df.log10_population.min(), df.log10_population.max(), 2)
        ax.plot(xs, a + b * xs, color="#52514e", lw=2, zorder=1)
        r2 = np.corrcoef(df.log10_population, df.divergence_gap)[0, 1] ** 2
        ax.annotate(f"slope {b:+.3f} per decade of population, R² = {r2:.02f}",
                    (0.02, 0.02), xycoords="axes fraction", fontsize=8,
                    color="#52514e")
    ax.set_xlabel("log10 FUA population")
    ax.set_ylabel("divergence gap (Gini emergency − everyday)")
    ax.set_title("Everyday-emergency divergence along the size gradient\n"
                 "(cross-sectional space-for-time)", fontsize=10)
    # Outside the axes: every in-plot corner of this dense scatter has data.
    ax.legend(frameon=False, fontsize=8, loc="upper left",
              bbox_to_anchor=(1.01, 1.0))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(figdir / "size_gradient.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # The headline scaling result as its own panel: mean deprivation vs
    # population, log-log, both regimes. This is where the strong effect lives
    # (everyday elasticity ~ -0.20 at p ~ 1e-15 vs a flat emergency slope);
    # the plane and gradient plots above are deliberately weaker views.
    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    series = [("mean_everyday", "everyday", "#2a78d6", "o"),
              ("mean_emergency", "emergency", "#eb6834", "s")]
    for col, label, colour, marker in series:
        df = vectors[["population", col]].dropna()
        df = df[(df.population > 0) & (df[col] > 0)]
        if len(df) < 4:
            continue
        ax.scatter(df.population, df[col], c=colour, marker=marker, s=34,
                   linewidths=0, alpha=0.85, zorder=2)
        b, a = np.polyfit(np.log(df.population), np.log(df[col]), 1)
        xs = np.linspace(np.log(df.population.min()), np.log(df.population.max()), 2)
        ax.plot(np.exp(xs), np.exp(a + b * xs), color=colour, lw=2, zorder=3)
        # Ink, not series colour, for the text (position at the line's end
        # carries identity); the mark/line already wears the colour.
        x_end = df.population.max()
        ax.annotate(f"{label}: elasticity {b:+.2f}",
                    (x_end, np.exp(a + b * np.log(x_end))),
                    textcoords="offset points", xytext=(6, -2), fontsize=8.5,
                    color="#52514e")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("FUA population")
    ax.set_ylabel("mean deprivation (population-weighted)")
    ax.set_title("Scaling of mean deprivation with city size, by regime\n"
                 "(log-log; cross-sectional space-for-time)", fontsize=10)
    ax.legend([plt.Line2D([], [], color=c, marker=m, ls="-", lw=2)
               for _, _, c, m in series], [s[1] for s in series],
              frameon=False, fontsize=8, loc="lower left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, lw=0.4, alpha=0.35, which="both"); ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(figdir / "scaling_elasticity.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    _plot_region_strips(vectors, region_of, figdir)
    _plot_rho_ranked(vectors, region_of, figdir)
    print(f"cross-city figures: {figdir}")


# The four outcomes whose regional contrasts the ANOVA flags (Cohen f
# 0.51-0.74 on the full sample) — the strip panel is that test, visualized:
# separated medians over overlapping clouds, i.e. regional GRADIENTS, not
# regional clusters (k-means vs region ARI ~ 0.07).
STRIP_PANELS = (
    ("spearman_rho", "coupling ρ (everyday vs emergency ranks)"),
    ("gini_everyday", "Gini of everyday deprivation"),
    ("gini_emergency", "Gini of emergency deprivation"),
    ("divergence_gap", "divergence gap (em − ev Gini)"),
)


def _plot_region_strips(vectors: pd.DataFrame, region_of: dict[str, str],
                        figdir: Path) -> None:
    import matplotlib.pyplot as plt

    regions = [r for r in REGION_STYLE if
               (vectors.country.map(region_of) == r).any()]
    if len(regions) < 2:
        return
    rng = np.random.default_rng(0)   # deterministic jitter
    fig, axes = plt.subplots(1, len(STRIP_PANELS),
                             figsize=(2.9 * len(STRIP_PANELS), 3.6))
    for ax, (col, title) in zip(np.atleast_1d(axes), STRIP_PANELS):
        for i, region in enumerate(regions):
            colour, marker = REGION_STYLE[region]
            vals = vectors.loc[vectors.country.map(region_of) == region,
                               col].dropna()
            ax.scatter(i + rng.uniform(-0.16, 0.16, len(vals)), vals,
                       c=colour, marker=marker, s=26, alpha=0.85,
                       linewidths=0, zorder=2)
            ax.hlines(vals.median(), i - 0.28, i + 0.28, color="#0b0b0b",
                      lw=2, zorder=3)
        if col == "divergence_gap":
            ax.axhline(0, color="0.8", lw=0.8, ls="--", zorder=1)
        ax.set_xticks(range(len(regions)), regions, fontsize=8)
        ax.set_title(title, fontsize=8.5)
        ax.tick_params(labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, axis="y", lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.suptitle("Deprivation structure by macro-region (bar = regional median)",
                 fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(figdir / "region_strips.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_rho_ranked(vectors: pd.DataFrame, region_of: dict[str, str],
                     figdir: Path) -> None:
    """Every city ordered by its everyday-emergency coupling ρ — the
    compounding question (do the same areas lose twice?) as one readable
    column, with the regional patterning legible from the colours."""
    import matplotlib.pyplot as plt

    s = vectors.dropna(subset=["spearman_rho"]) \
        .sort_values("spearman_rho").reset_index(drop=True)
    if len(s) < 3:
        return
    flagged = _outlier_group(vectors)
    flagged_cities = set(vectors.loc[flagged, "city"])
    fig, ax = plt.subplots(figsize=(6.5, max(4.0, 0.17 * len(s))))
    for region in [r for r in REGION_STYLE
                   if (s.country.map(region_of) == r).any()]:
        colour, marker = REGION_STYLE[region]
        sel = s.country.map(region_of) == region
        ax.scatter(s.loc[sel, "spearman_rho"], s.index[sel], c=colour,
                   marker=marker, s=30, linewidths=0, zorder=2, label=region)
    other = ~s.country.map(region_of).isin(REGION_STYLE)
    if other.any():
        ax.scatter(s.loc[other, "spearman_rho"], s.index[other],
                   c=FALLBACK_STYLE[0], marker=FALLBACK_STYLE[1], s=30,
                   linewidths=0, zorder=2, label="other")
    des = s.city.isin(flagged_cities)
    if des.any():
        ax.scatter(s.loc[des, "spearman_rho"], s.index[des],
                   facecolors="none", edgecolors="#0b0b0b", s=110,
                   linewidths=1.1, zorder=3, label="emergency-desert group")
    ax.set_yticks(s.index, s["name"], fontsize=6.5)
    ax.set_xlabel("Spearman ρ between everyday and emergency deprivation",
                  fontsize=9)
    ax.set_title("Compounding: does the same population carry both "
                 "deprivations?\n(ρ ≈ 0: unrelated maps · high ρ: the same "
                 "areas lose twice)", fontsize=9.5)
    ax.axvline(0, color="0.8", lw=0.8, ls="--", zorder=1)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(True, axis="x", lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    ax.margins(y=0.01)
    fig.tight_layout()
    fig.savefig(figdir / "rho_ranked.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
