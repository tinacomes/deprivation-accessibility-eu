"""Accumulate per-city summaries across workflow runs via the depacc-results
branch.

The results branch is an orphan branch holding only small CSV summaries and
cross-city figures:

    cities/<city>/cityplane_row.csv        one-row city summary
    cities/<city>/typology_summary_*.csv   compounding population shares (per
                                           percentile threshold)
    cities/<city>/equity_indices.csv       weighted mean / Gini / CI
    cities/<city>/equity_regressions.csv   density + SES gradients
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
    "accessibility_by_service.csv",
    "accessibility_by_regime.csv",
)
# Per-city summaries whose name carries a variable suffix (one file per
# percentile threshold, e.g. typology_summary_50.csv / typology_summary_75.csv).
SUMMARY_GLOBS = (
    "typology_summary_*.csv",
)
CROSS_FILES = (
    "cityplane.csv",
    "cityvector.csv",
    "cityvector_clustered.csv",
    "scaling.csv",
    "size_gradient.csv",
    "regime_slope_difference.csv",
)
# Robustness-harness outputs (data/derived/sensitivity/*), passed through
# verbatim into results/sensitivity/. The per-city deprivation-sensitivity
# table carries a <city> prefix; the rest are cross-city rollups.
SENSITIVITY_FILES = (
    "rank_agreement.csv",
    "flip_cells.csv",
    "typology_share_envelope.csv",
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
                continue  # freshly computed this run — always wins
            shutil.copytree(cdir, dest)
            imported += 1
    print(f"imported {imported} previously persisted cities")
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
        exported += 1
    _export_sensitivity(results, derived)
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
