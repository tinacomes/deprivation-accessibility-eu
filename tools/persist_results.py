"""Accumulate per-city summaries across workflow runs via the depacc-results
branch.

The results branch is an orphan branch holding only small CSV summaries and
cross-city figures:

    cities/<city>/cityplane_row.csv        one-row city summary
    cities/<city>/typology_summary_*.csv   compounding population shares (per
                                           percentile threshold)
    cities/<city>/equity_indices.csv       weighted mean / Gini / CI
    cities/<city>/equity_regressions.csv   density + SES gradients
    cities/<city>/equity_vulnerability.csv stratified deprivation + HH share
                                           within 65+/under-18/low-rent strata
    cities/<city>/accessibility_by_*.csv   per-service / per-regime travel-time
                                           accessibility indicators
    cross/                                 union cityplane, cityvector,
                                           scaling, size gradient, figures
    sensitivity/                           per-city deprivation-sensitivity
                                           tables + cross-city rank agreement,
                                           flip cells, typology-share envelope

Two commands, both idempotent:

  import  copy previously persisted cities into data/derived (never
          overwriting cities computed in the current run) and rebuild the
          union cityplane.csv — run BEFORE `depacc cross`, so clustering and
          the scaling regressions always see every city ever computed.
  export  copy the current run's per-city summaries (synthetic fixtures are
          skipped) and the cross outputs into the results checkout — run
          after `depacc cross`, then commit + push.

Raw data and heavy parquet surfaces are never persisted (reproducible via
ingest/access; DVC covers heavy artefacts).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

# Fixed per-city summary file names copied into cities/<city>/.
SUMMARY_FILES = (
    "cityplane_row.csv",
    "equity_indices.csv",
    "equity_regressions.csv",
    "equity_vulnerability.csv",
    # Per-covariate support behind every gradient in equity_regressions.csv.
    # A coefficient without its n is not reviewable, and both of Hamburg's SES
    # failures (a covariate on 0.2 % of cells, one on 2.6 % supplying the
    # largest everyday gradient) were invisible until this table existed.
    "equity_ses_coverage.csv",
    "accessibility_by_service.csv",
    "accessibility_by_regime.csv",
)
# Per-city summaries whose name carries a variable suffix (one file per
# percentile threshold, e.g. typology_summary_50.csv / typology_summary_75.csv).
SUMMARY_GLOBS = (
    "typology_summary_*.csv",
)
# E.5 face-validation evidence: the headline maps the validation pages
# annotate (percentile surfaces + the co-location map), NOT the whole
# figures/ directory — depacc-results stays a summaries branch.
FIGURE_GLOBS = (
    "figures/percentile_*.png",
    "figures/compounding_map_*.png",
    "figures/compounding_classes_*.png",
)
CROSS_FILES = (
    "cityplane.csv",
    "cityvector.csv",
    "cityvector_clustered.csv",
    # Second clustering pass with the flagged outlier group removed
    # (clustering.py peeled_clustering): does any typology remain among
    # ordinary cities once the emergency-desert capitals stop absorbing
    # the silhouette criterion?
    "cityvector_clustered_peeled.csv",
    "cluster_null_peeled.csv",
    # Cross-city vulnerability synthesis (equity/vulnerability_cross.py):
    # the census-harmonised strata pooled over all cities.
    "vulnerability.csv",
    "vulnerability_summary.csv",
    "scaling.csv",
    "size_gradient.csv",
    "regime_slope_difference.csv",
    # Country-clustered inference (cityvector/inference.py): the citable
    # p-values — permutation-over-countries for the regional contrasts,
    # wild-cluster-bootstrap scaling, and the emergency TOST.
    "inference_regional.csv",
    "inference_scaling_clustered.csv",
    "inference_equivalence.csv",
    "inference_regime_paired.csv",
    "inference_influence.csv",
    "cluster_null.csv",
    # Deprivation-vs-access contrast + Table-1 material
    # (cityvector/dep_vs_access.py, run by `depacc cross`).
    "deprivation_vs_access.csv",
    "desert_access_contrast.csv",
    "scaling_by_grade.csv",
    "cities_descriptives.csv",
    "accessibility_by_service_pooled.csv",
    "accessibility_by_service_cities.csv",
)
# Robustness-harness outputs (data/derived/sensitivity/*), passed through
# verbatim into results/sensitivity/. The per-city deprivation-sensitivity
# table carries a <city> prefix; the rest are cross-city rollups.
SENSITIVITY_FILES = (
    "rank_agreement.csv",
    "flip_cells.csv",
    "typology_share_envelope.csv",
    # Cross-city Gini claims under every deprivation parameterisation
    # (cityvector/spec_curve.py).
    "specification_curve.csv",
    "specification_curve.png",
    # Per-city envelope of every target per sweep axis + the cost curves
    # themselves (harness deprivation_sensitivity_summary /
    # viz/deprivation_curves) — the deprivation layer's own evidence.
    "deprivation_sensitivity_summary.csv",
    "deprivation_curves.png",
)
# Workstream E outputs, passed through verbatim (see _export_validation).
VALIDATION_GLOBS = (
    "*_engine_check.csv",
    "*_engine_scatter.png",
    "*_engine_qq.csv",
    "*_engine_qq.png",
)
SENSITIVITY_GLOBS = (
    "*_deprivation_sensitivity.csv",
    # Layer-3 accessibility sweep (depacc sensitivity --layer access): per-city
    # variant table, the Hamburg-style acceptance table, and the flip-cell map.
    "*_access_sensitivity.csv",
    "*_access_acceptance.csv",
    "*_access_flip_cells.png",
)


def _is_synthetic(city_dir: Path) -> bool:
    row = city_dir / "cityplane_row.csv"
    if not row.exists():
        return False
    df = pd.read_csv(row)
    return bool(df.iloc[0].get("synthetic", False)) if len(df) else False


def rebuild_cityplane(derived: Path) -> None:
    """Union cityplane.csv from per-city row files (authoritative) plus any
    rows already in cityplane.csv (back-compat), deduplicated by city."""
    frames = [pd.read_csv(p) for p in sorted(derived.glob("*/cityplane_row.csv"))]
    plane_path = derived / "cityplane.csv"
    if plane_path.exists():
        frames.append(pd.read_csv(plane_path))
    if not frames:
        return
    plane = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="city", keep="first")
        .sort_values("population", ascending=False)
    )
    plane.to_csv(plane_path, index=False)
    print(f"cityplane.csv union: {len(plane)} cities")


def cmd_import(results: Path, derived: Path) -> None:
    derived.mkdir(parents=True, exist_ok=True)
    imported = 0
    cities = results / "cities"
    if cities.exists():
        for cdir in sorted(cities.iterdir()):
            dest = derived / cdir.name
            if dest.exists():
                # Freshly computed files always win — but a budget-stopped
                # resume round stages a PARTIAL dir (ingest/access progress,
                # no cityplane_row.csv yet), and letting it shadow the whole
                # persisted city silently drops the city from the cross
                # union (run 31181146117 lost paris this way: 66-row
                # cityplane, every cross/inference table missing the largest
                # city, no error anywhere). Fill in per-file: anything the
                # staged dir already has is kept, anything persisted that it
                # lacks is restored.
                filled = 0
                for src in cdir.rglob("*"):
                    if src.is_dir():
                        continue
                    tgt = dest / src.relative_to(cdir)
                    if not tgt.exists():
                        tgt.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, tgt)
                        filled += 1
                if filled:
                    print(f"  {cdir.name}: staged dir is partial — restored "
                          f"{filled} persisted file(s) so the city stays in "
                          f"the cross union")
                continue
            shutil.copytree(cdir, dest)
            imported += 1
    print(f"imported {imported} previously persisted cities")
    # Per-city VARIANT tables too: the specification curve is cross-city and
    # needs every persisted city's table, but a run's own sweep only rebuilds
    # tables for cities with staged surfaces. Fresh tables always win.
    sens_src = results / "sensitivity"
    if sens_src.exists():
        sens_dst = derived / "sensitivity"
        sens_dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for src in sorted(sens_src.glob("*_deprivation_sensitivity.csv")):
            if not (sens_dst / src.name).exists():
                shutil.copy2(src, sens_dst / src.name)
                n += 1
        print(f"imported {n} previously persisted variant table(s)")
    rebuild_cityplane(derived)


def _export_sensitivity(results: Path, derived: Path) -> None:
    """Pass the robustness-harness outputs (data/derived/sensitivity/*) through
    to results/sensitivity/ verbatim. No-op when the sweep has not been run."""
    src_dir = derived / "sensitivity"
    if not src_dir.exists():
        return
    dest_dir = results / "sensitivity"
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in SENSITIVITY_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, dest_dir / name)
            copied += 1
    for pattern in SENSITIVITY_GLOBS:
        for src in sorted(src_dir.glob(pattern)):
            shutil.copy2(src, dest_dir / src.name)
            copied += 1
    print(f"exported {copied} sensitivity file(s) to {dest_dir}")


def _export_validation(results: Path, derived: Path) -> None:
    """Pass the validation outputs (data/derived/validation/*) through verbatim.

    Workstream E's artefacts — the routing-engine cross-check first — belong on
    the results branch for the same reason the sensitivity tables do: they are
    small, reusable and the thing a reader asks for when they want to know how
    much the Tier-1 friction fast path costs. No-op when no check has been run.
    """
    src_dir = derived / "validation"
    if not src_dir.exists():
        return
    dest_dir = results / "validation"
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pattern in VALIDATION_GLOBS:
        for src in sorted(src_dir.glob(pattern)):
            shutil.copy2(src, dest_dir / src.name)
            copied += 1
    print(f"exported {copied} validation file(s) to {dest_dir}")


def cmd_export(results: Path, derived: Path) -> None:
    exported = 0
    (results / "cities").mkdir(parents=True, exist_ok=True)
    for cdir in sorted(p for p in derived.iterdir() if p.is_dir() and p.name != "figures"):
        if not (cdir / "cityplane_row.csv").exists():
            continue  # incomplete run (e.g. ingest/access only)
        if _is_synthetic(cdir):
            print(f"skipping synthetic fixture '{cdir.name}'")
            continue
        dest = results / "cities" / cdir.name
        dest.mkdir(parents=True, exist_ok=True)
        for name in SUMMARY_FILES:
            src = cdir / name
            if src.exists():
                shutil.copy2(src, dest / name)
        for pattern in SUMMARY_GLOBS:
            for src in sorted(cdir.glob(pattern)):
                shutil.copy2(src, dest / src.name)
        for pattern in FIGURE_GLOBS:
            for src in sorted(cdir.glob(pattern)):
                (dest / "figures").mkdir(exist_ok=True)
                shutil.copy2(src, dest / "figures" / src.name)
        exported += 1
    _export_sensitivity(results, derived)
    _export_validation(results, derived)
    cross = results / "cross"
    cross.mkdir(exist_ok=True)
    for name in CROSS_FILES:
        src = derived / name
        if src.exists():
            shutil.copy2(src, cross / name)
    figs = derived / "figures"
    if figs.exists():
        shutil.copytree(figs, cross / "figures", dirs_exist_ok=True)
    readme = results / "README.md"
    if not readme.exists():
        readme.write_text(
            "# depacc results (auto-generated)\n\n"
            "Small per-city summaries + cross-city outputs accumulated by the "
            "depacc workflows (see tools/persist_results.py on main). "
            "Raw data and cell-level surfaces "
            "are reproducible via the pipeline and are never committed here.\n"
        )
    print(f"exported {exported} cities + cross outputs to {results}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["import", "export"])
    ap.add_argument("--derived", type=Path, required=True,
                    help="data/derived of the current run")
    ap.add_argument("--results", type=Path, required=True,
                    help="checkout (worktree) of the depacc-results branch")
    args = ap.parse_args()
    if args.command == "import":
        cmd_import(args.results, args.derived)
    else:
        cmd_export(args.results, args.derived)


if __name__ == "__main__":
    main()
