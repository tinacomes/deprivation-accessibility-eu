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
    scaled = scale_features(real, feature_columns(cfg), method=method)
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

    _plot_cross_city(real, derived)


def _plot_cross_city(vectors: pd.DataFrame, derived: Path) -> None:
    if len(vectors) < 2:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figdir = derived / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    cluster_colors = ["#5ac8c8", "#be64ac", "#3b4994", "#e0a04e", "#7a9e3a"]
    have = "cluster_kmeans" in vectors and vectors["cluster_kmeans"].notna().any()

    # everyday-vs-emergency inequity plane, coloured by cluster.
    fig, ax = plt.subplots(figsize=(6.5, 6))
    lim = max(vectors.gini_everyday.max(), vectors.gini_emergency.max()) * 1.15 + 1e-9
    ax.plot([0, lim], [0, lim], color="0.75", lw=1, ls="--", zorder=1)
    for _, r in vectors.iterrows():
        c = (cluster_colors[int(r.cluster_kmeans) % len(cluster_colors)]
             if have and pd.notna(r.cluster_kmeans) else "#3b4994")
        ax.scatter(r.gini_everyday, r.gini_emergency, c=c, s=45, linewidths=0, zorder=2)
        ax.annotate(r["name"], (r.gini_everyday, r.gini_emergency),
                    textcoords="offset points", xytext=(5, 3), fontsize=8, color="0.25")
    ax.set_xlabel("Gini of everyday deprivation")
    ax.set_ylabel("Gini of emergency deprivation")
    ax.set_title("Everyday-vs-emergency inequity plane"
                 + (" (colour = cluster)" if have else ""), fontsize=10)
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(figdir / "cityplane.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # divergence_gap vs city size (space-for-time trajectory).
    fig, ax = plt.subplots(figsize=(7, 5.5))
    for _, r in vectors.iterrows():
        c = (cluster_colors[int(r.cluster_kmeans) % len(cluster_colors)]
             if have and pd.notna(r.cluster_kmeans) else "#3b4994")
        ax.scatter(r.log10_population, r.divergence_gap, c=c, s=40, linewidths=0)
        ax.annotate(r["name"], (r.log10_population, r.divergence_gap),
                    textcoords="offset points", xytext=(5, 3), fontsize=8, color="0.25")
    ax.axhline(0, color="0.75", lw=1, ls="--")
    ax.set_xlabel("log10 FUA population")
    ax.set_ylabel("divergence gap (Gini emergency − everyday)")
    ax.set_title("Everyday-emergency divergence along the size gradient\n"
                 "(cross-sectional space-for-time)", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(figdir / "size_gradient.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"cross-city figures: {figdir}")
