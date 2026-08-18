#!/usr/bin/env python3
"""Is H4's partition robust to the clustering FEATURE SET, not just its data?

The published clustering (methods §4.4) runs on the feature list fixed in
``cityvector.access_thresholds_min`` — emergency level shares at 30/45/60
minutes — a specification chosen before the EMS benchmarks (8/15 min)
entered the study. When the benchmarks arrived, the new 8/15-min shares
were added to the *reporting* tables only, so the re-anchor run stayed a
controlled experiment (one change at a time: the anchor, whose invariance
is checkable, not the anchor AND the model). That control is only honest
if the feature-set choice is then tested rather than frozen by fiat —
which is this script.

It re-runs the full clustering pipeline — scaling, silhouette-selected k,
bootstrap stability, Gaussian null, the peeled second pass — on the
EXTENDED feature set (emergency shares at 8/15/30/45/60, pulled from each
city's ``accessibility_by_regime.csv``) and reports the agreement with the
published partition. Both diagnostics tables are written either way; if
the partitions disagree, that is a finding to report, not to suppress.

Note the direction of the mechanical bias, so the outcome is read
honestly: the added shares are *nested* versions of the tails the desert
group already separates on, so including them up-weights the
emergency-tail axis in the k-means distance — it would, if anything,
STRENGTHEN the published 62/5 split. The published specification is the
conservative one for H4; this check verifies that claim instead of
resting on it.

    python tools/cluster_feature_robustness.py --derived data/derived

Expects the per-city dirs + cityvector_clustered(_peeled).csv of a staged
``depacc-results`` state produced AFTER the re-anchor run (earlier states
lack the 8/15-min columns). Writes
``cluster_feature_robustness.csv`` next to them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXTRA = ("pop_share_beyond_emergency_8", "pop_share_beyond_emergency_15")


def extended_vectors(derived: Path) -> pd.DataFrame | None:
    """The published feature frame + the 8/15-min emergency shares read from
    each city's accessibility_by_regime.csv (emergency regime row)."""
    vec_path = derived / "cityvector_clustered.csv"
    if not vec_path.exists():
        print(f"missing {vec_path}", file=sys.stderr)
        return None
    vectors = pd.read_csv(vec_path)
    shares = {}
    for city in vectors["city"].astype(str):
        path = derived / city / "accessibility_by_regime.csv"
        if not path.exists():
            continue
        table = pd.read_csv(path)
        row = table[table["regime"].astype(str) == "emergency"]
        if row.empty:
            continue
        rec = {}
        for minutes, col in ((8, "pop_share_beyond_8min"),
                             (15, "pop_share_beyond_15min")):
            if col in row.columns and pd.notna(row[col].iloc[0]):
                rec[f"pop_share_beyond_emergency_{minutes}"] = float(
                    row[col].iloc[0])
        if len(rec) == len(EXTRA):
            shares[city] = rec
    if not shares:
        print("no 8/15-min emergency shares found — this state predates the "
              "re-anchor run; nothing to test yet", file=sys.stderr)
        return None
    missing = set(vectors["city"].astype(str)) - set(shares)
    if missing:
        print(f"NOTE: {len(missing)} cities lack the 8/15-min shares "
              f"({sorted(missing)[:5]}...); they would be imputed at the "
              "sample centre — refusing, the test must cover the sample",
              file=sys.stderr)
        return None
    extra = pd.DataFrame.from_dict(shares, orient="index").rename_axis("city")
    return vectors.merge(extra.reset_index(), on="city", how="left")


def run(derived: Path) -> int:
    from sklearn.metrics import adjusted_rand_score

    from depacc.config import load_config
    from depacc.cityvector.clustering import (
        _region_lookup,
        choose_k_and_cluster,
        declump_tail_shares,
        peeled_clustering,
        silhouette_null,
    )
    from depacc.cityvector.features import feature_columns
    from depacc.cityvector.scaling_features import scale_features

    cfg = load_config()
    vectors = extended_vectors(derived)
    if vectors is None:
        return 2
    published = vectors["cluster_kmeans"].to_numpy()
    cols = feature_columns(cfg) + [c for c in EXTRA if c in vectors.columns]

    ccfg = cfg.get("cityvector", {}).get("clustering", {})
    method = cfg.get("cityvector", {}).get("cross_city_scaler", "robust")
    kw = dict(k_range=tuple(ccfg.get("k_range", [2, 6])),
              bootstrap=int(ccfg.get("bootstrap", 50)),
              random_state=int(ccfg.get("random_state", 0)))
    scaled = scale_features(
        declump_tail_shares(vectors, cols), cols, method=method,
        max_missing_share=float(cfg.get("cityvector", {})
                                .get("max_missing_share", 0.25)))
    result = choose_k_and_cluster(scaled, **kw)
    labels = np.asarray(result["labels_kmeans"])
    ari = adjusted_rand_score(published, labels)
    null = silhouette_null(scaled, result["silhouette"],
                           k_range=kw["k_range"],
                           random_state=kw["random_state"]) or {}

    sizes = pd.Series(labels).value_counts().sort_values()
    small = set(vectors.loc[labels == sizes.index[0], "city"]) \
        if len(sizes) > 1 else set()
    published_small = set(
        vectors.loc[published == pd.Series(published).value_counts().idxmin(),
                    "city"])

    row = {
        "feature_set": "extended (+emergency 8/15-min shares)",
        "n_features": len(scaled.feature_names),
        "k": result.get("k"),
        "silhouette": result.get("silhouette"),
        "stability_ari": result.get("stability_ari"),
        "p_null_gaussian": null.get("p_null_gaussian"),
        "ari_vs_published": float(ari),
        "small_group": ";".join(sorted(small)),
        "small_group_matches_published": small == published_small,
    }

    peel = peeled_clustering(
        vectors.assign(cluster_kmeans=labels), cols, method=method,
        max_missing_share=float(cfg.get("cityvector", {})
                                .get("max_missing_share", 0.25)),
        region_of=_region_lookup(cfg), **kw)
    if peel is not None:
        peeled_df, diag = peel
        pub_peel_path = derived / "cityvector_clustered_peeled.csv"
        if pub_peel_path.exists():
            pub = pd.read_csv(pub_peel_path)[["city", "cluster_kmeans"]] \
                .rename(columns={"cluster_kmeans": "published"})
            joined = peeled_df.merge(pub, on="city", how="inner")
            row["peeled_ari_vs_published"] = float(adjusted_rand_score(
                joined["published"], joined["cluster_kmeans"]))
        row["peeled_k"] = diag.get("k")
        row["peeled_silhouette"] = diag.get("silhouette")
        row["peeled_small_n"] = int(
            pd.Series(peeled_df["cluster_kmeans"]).value_counts().min())

    out = pd.DataFrame([row])
    out_path = derived / "cluster_feature_robustness.csv"
    out.to_csv(out_path, index=False)
    print(out.T.to_string(header=False))
    print(f"\nwritten: {out_path}")
    agree = row["small_group_matches_published"] and ari > 0.8
    print("VERDICT: partition robust to the feature set" if agree else
          "VERDICT: partition CHANGES with the feature set — report both "
          "specifications, do not pick silently")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--derived", type=Path, default=Path("data/derived"))
    return run(ap.parse_args().derived)


if __name__ == "__main__":
    raise SystemExit(main())
