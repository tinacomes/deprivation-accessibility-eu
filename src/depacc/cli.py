"""Command-line interface.

    depacc run --city hamburg                 # full pipeline for one city
    depacc run --city hamburg --stage access  # a single stage
    depacc validate --city hamburg            # config sanity check
    depacc engine-check --city hamburg        # E.1: friction vs r5 cross-check

Stages run in order: ingest -> access -> deprivation -> divergence -> equity
-> viz. Heavy dependencies (geopandas, r5py, ...) are imported inside each
stage, so the CLI and unit-testable mathematics only need the core install.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from depacc.config import load_config

STAGES = ("ingest", "access", "deprivation", "divergence", "equity", "viz")

# Marker output of each stage, used to decide whether it still needs running
# when a later stage is dispatched on its own (e.g. on a fresh GitHub runner
# whose per-city cache missed). This makes any single-stage dispatch
# self-sufficient: prerequisites are (re)run automatically, and completed
# ones are skipped.
def _stage_done(stage: str, out: "Path") -> bool:
    if stage == "ingest":
        return (out / "cells.parquet").exists()
    if stage == "access":
        return any(out.glob("od_*.parquet"))
    if stage == "deprivation":
        return (out / "surfaces.parquet").exists()
    if stage == "divergence":
        return (out / "typology.parquet").exists()
    if stage == "equity":
        return (out / "equity_indices.csv").exists()
    if stage == "viz":
        return (out / "figures").exists()
    return False


def _stages_to_run(target: str, out: "Path") -> list[str]:
    """Prerequisite stages whose outputs are missing, in order, then the
    requested stage itself (always re-run)."""
    order = list(STAGES)
    prior = order[: order.index(target)]
    return [s for s in prior if not _stage_done(s, out)] + [target]


def _run_stage(stage: str, cfg: dict, city: str, project_root: Path) -> None:
    if stage == "ingest":
        from depacc.ingest.pipeline import run_ingest

        run_ingest(cfg, city, project_root)
    elif stage == "access":
        from depacc.access.matrices import run_access

        run_access(cfg, city, project_root)
    elif stage == "deprivation":
        from depacc.deprivation.pipeline import run_deprivation

        run_deprivation(cfg, city, project_root)
    elif stage == "divergence":
        from depacc.divergence.pipeline import run_divergence

        run_divergence(cfg, city, project_root)
    elif stage == "equity":
        from depacc.equity.pipeline import run_equity

        run_equity(cfg, city, project_root)
    elif stage == "viz":
        from depacc.viz.pipeline import run_viz

        run_viz(cfg, city, project_root)
    else:  # pragma: no cover - argparse restricts choices
        raise ValueError(f"Unknown stage {stage}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="depacc", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the pipeline for one city")
    run.add_argument("--city", required=True, help="city id (config/cities/<id>.yaml)")
    run.add_argument("--stage", choices=STAGES + ("all",), default="all")
    run.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="subproject root (default: the installed package's repo checkout)",
    )

    val = sub.add_parser("validate", help="load + validate config for a city")
    val.add_argument("--city", required=True)

    make = sub.add_parser(
        "make-city", help="generate a minimal Tier-1 fast-path city config "
                          "(friction engine + Overpass facilities)")
    make.add_argument("--fua-code", required=True, help="URAU 2021 FUA code (ends in F, e.g. DE002F); find codes with `depacc list-fuas`")
    make.add_argument("--name", required=True)
    make.add_argument("--country", required=True, help="two-letter code, e.g. SE")
    make.add_argument("--city-id", default=None,
                      help="config id/slug (default: name, lowercased)")

    cross = sub.add_parser(
        "cross", help="cross-city cityvector clustering, PNAS-style scaling "
                      "regressions + size-gradient read over cityplane.csv")
    cross.add_argument("--n-clusters", type=int, default=3)
    cross.add_argument(
        "--project-root", type=Path,
        default=Path(__file__).resolve().parents[2])

    sens = sub.add_parser(
        "sensitivity", help="robustness sweep over the stable rank targets. "
                            "--layer deprivation: curvature/form (Layers 1/2); "
                            "--layer access: accessibility knobs (Layer 3) from "
                            "cached OD — no re-routing")
    sens.add_argument("--layer", choices=("deprivation", "access", "all"),
                      default="deprivation",
                      help="which sensitivity layer to run (default: deprivation)")
    sens.add_argument("--city", default=None,
                      help="restrict to one city (default: all in cityplane.csv). "
                           "Layer 3 accepts a single --city without cityplane.csv.")
    sens.add_argument("--grid", type=Path, default=None,
                      help="sweep grid YAML (default: config/sensitivity.yaml)")
    sens.add_argument("--project-root", type=Path,
                      default=Path(__file__).resolve().parents[2])

    eng = sub.add_parser(
        "engine-check", help="Workstream E.1: re-route one city under an "
                             "alternative routing engine, holding cells, "
                             "facilities and every model parameter fixed, and "
                             "report how far the travel times, the city-row "
                             "indicators and the typology move")
    eng.add_argument("--city", required=True)
    eng.add_argument("--engine", default="r5",
                     help="alternative engine to compare against the city's "
                          "configured one (default: r5)")
    eng.add_argument("--modes", nargs="+", default=None,
                     help="override routing.modes for the alternative run "
                          "(e.g. --modes walk car transit)")
    eng.add_argument("--threshold", type=float, default=0.5,
                     help="typology percentile cut for the flip share (default 0.5)")
    eng.add_argument("--no-reuse", action="store_true",
                     help="re-route even if the alternative surfaces are cached")
    eng.add_argument("--project-root", type=Path,
                     default=Path(__file__).resolve().parents[2])

    pre = sub.add_parser(
        "prefetch", help="download the raw sources that are national or "
                         "continental (census grid, national SES grids, URAU "
                         "boundaries, GHS-POP tiles) ONCE for a set of cities — "
                         "run before a many-city batch fans out")
    pre.add_argument("--city", action="append", default=None,
                     help="city id; repeatable. Default: every config in "
                          "config/cities/")
    pre.add_argument("--all-cities", action="store_true",
                     help="explicitly prefetch for every configured city")
    pre.add_argument("--project-root", type=Path,
                     default=Path(__file__).resolve().parents[2])

    lf = sub.add_parser(
        "list-fuas", help="list Functional Urban Areas (codes + names) from "
                          "the Eurostat URAU layer, for choosing cities")
    lf.add_argument("--country", action="append", default=None,
                    help="two-letter code; repeatable (e.g. --country DE --country NL)")
    lf.add_argument("--project-root", type=Path,
                    default=Path(__file__).resolve().parents[2])

    args = parser.parse_args(argv)

    if args.command == "prefetch":
        from depacc.ingest.prefetch import configured_cities, prefetch_shared

        cities = args.city or configured_cities()
        print(f"prefetching shared sources for {len(cities)} city config(s): "
              f"{cities}", flush=True)
        prefetch_shared(cities, args.project_root)
        return 0

    if args.command == "list-fuas":
        from depacc.ingest.fua_sample import list_fuas

        cfg = load_config()
        fuas = list_fuas(cfg, args.project_root)
        if args.country:
            fuas = fuas[fuas.country.isin([c.upper() for c in args.country])]
        has_pop = fuas.population.notna().any()
        fuas = fuas.sort_values(
            ["country", "population" if has_pop else "name"],
            ascending=[True, not has_pop],
        )
        out_csv = args.project_root / cfg["output"]["root"] / "fua_list.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        fuas.to_csv(out_csv, index=False)
        print(fuas.to_string(index=False))
        print(f"\n{len(fuas)} FUAs (also written to {out_csv}).\n"
              f"Use a code with: depacc make-city --fua-code CODE --name NAME "
              f"--country CC, or the batch workflow's make_cities input: "
              f"\"CODE,NAME,CC; ...\"")
        return 0

    if args.command == "make-city":
        from depacc.config import CONFIG_DIR

        city_id = args.city_id or "".join(
            ch for ch in args.name.lower().replace(" ", "_") if ch.isalnum() or ch == "_")
        path = CONFIG_DIR / "cities" / f"{city_id}.yaml"
        if path.exists():
            print(f"{path} already exists; not overwriting")
            return 1
        path.write_text(
            f"# Tier-1 fast-path city (generated by `depacc make-city`).\n"
            f"# Facilities via Overpass, travel times via the Weiss et al.\n"
            f"# friction surfaces — no .pbf, no GTFS, no Java.\n"
            f"city:\n"
            f"  id: \"{city_id}\"\n"
            f"  name: \"{args.name}\"\n"
            f"  country: \"{args.country.upper()}\"\n"
            f"  tier: 1\n"
            f"  fua_code: \"{args.fua_code}\"\n"
            f"sources:\n"
            f"  facilities: \"overpass\"\n"
            f"routing:\n"
            f"  engine: \"friction\"\n"
            f"  modes: [\"walk\", \"car\"]\n"
        )
        print(f"wrote {path}; run: depacc run --city {city_id}")
        return 0

    if args.command == "cross":
        from depacc.cityvector.clustering import run_cross_city

        run_cross_city(load_config(), args.project_root, n_clusters=args.n_clusters)
        return 0

    if args.command == "sensitivity":
        import yaml

        from depacc.config import CONFIG_DIR

        grid_path = args.grid or (CONFIG_DIR / "sensitivity.yaml")
        grid = (yaml.safe_load(open(grid_path)) or {}).get("sensitivity", {})
        if args.layer in ("deprivation", "all"):
            from depacc.sensitivity import run_sensitivity

            run_sensitivity(load_config(), grid, args.project_root)
        if args.layer in ("access", "all"):
            from depacc.sensitivity import run_access_sensitivity

            run_access_sensitivity(load_config(), grid, args.project_root,
                                   city=args.city)
        return 0

    cfg = load_config(args.city)

    if args.command == "engine-check":
        from depacc.access.matrices import RoutingBudgetExhausted
        from depacc.quality.engine_check import run_engine_check

        try:
            run_engine_check(cfg, args.city, args.project_root,
                             engine=args.engine, modes=args.modes,
                             threshold=args.threshold, reuse=not args.no_reuse)
        except RoutingBudgetExhausted as exc:
            return _report_budget_exhausted(exc)
        return 0

    if args.command == "validate":
        print(f"Config for '{args.city}' loaded OK "
              f"({len(cfg)} top-level sections: {sorted(cfg)})")
        return 0

    if args.stage == "all":
        stages = list(STAGES)
    else:
        out = args.project_root / cfg["output"]["root"] / args.city
        stages = _stages_to_run(args.stage, out)
        if stages != [args.stage]:
            print(f"auto-running missing prerequisites before "
                  f"'{args.stage}': {stages}", flush=True)
    for stage in stages:
        print(f"=== stage: {stage} ===", flush=True)
        try:
            _run_stage(stage, cfg, args.city, args.project_root)
        except _budget_exhausted() as exc:
            # Stop the pipeline here: every later stage would read a
            # half-routed city and report its unrouted cells as deprived.
            return _report_budget_exhausted(exc)
    return 0


def _budget_exhausted() -> type[Exception]:
    from depacc.access.matrices import RoutingBudgetExhausted

    return RoutingBudgetExhausted


#: Exit code for "stopped on budget, nothing is wrong, re-dispatch to resume".
#: Distinct from 1 so CI can tell a resumable stop from a real failure.
BUDGET_EXIT_CODE = 2


def _report_budget_exhausted(exc: Exception) -> int:
    print(f"\n{exc}", file=sys.stderr)
    print("Nothing was lost: finished matrices and finished origin chunks are "
          "on disk under data/derived/. Re-run the same command (or "
          "re-dispatch the workflow, which restores the per-city derived "
          "cache) to continue from here.", file=sys.stderr)
    return BUDGET_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
