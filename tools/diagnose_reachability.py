#!/usr/bin/env python
"""Reachability diagnostic for a city's derived outputs (Phase 0 report).

Reconciles the everyday vs emergency "unreachable" masks and splits everyday
unreachability into:

    (a) NO NETWORK PATH        — genuinely unroutable (reaches zero facilities
                                 of any service in any mode); this set is
                                 service- and mode-independent and should match
                                 the emergency-unreachable set (~the emergency
                                 no-path cells).
    (b) ROUTABLE, NO FACILITY  — reachable, but no facility of a given everyday
                                 service lies within the cutoff. NOT
                                 unreachability: a badly deprived cell.

Also reports per-service facility counts inside the FUA (a near-empty layer
means the Overpass tags are wrong). Reads ONLY the derived parquet outputs of a
completed `ingest`+`access` run — no network, no model parameters, nothing
mutated. Usage:

    python tools/diagnose_reachability.py --city hamburg [--project-root .]

The exact Hamburg split can only be produced where the derived data exists
(e.g. a CI run's data/derived cache), because raw data is gitignored and
reproduced by the ingest stage.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from depacc.config import load_config
from depacc.ingest.pipeline import derived_dir


def _pop_share(pop: pd.Series, mask: pd.Series) -> float:
    total = float(pop.sum())
    return float(pop[mask].sum()) / total if total > 0 else float("nan")


def diagnose(city: str, root: Path) -> None:
    cfg = load_config(city)
    out = derived_dir(cfg, city, root)
    if not (out / "cells.parquet").exists():
        raise SystemExit(
            f"No derived cells for '{city}' in {out}. Run the ingest+access "
            f"stages first (or point --project-root at a run's data/derived)."
        )
    cells = pd.read_parquet(out / "cells.parquet").set_index("cell_id")
    pop = cells["population"].astype(float)

    everyday = list(cfg.get("everyday_services", {}))
    emergency = list(cfg.get("emergency_services", {}))

    # Per-service facility counts (near-empty layer => wrong Overpass tags).
    print("=== facility counts inside the FUA ===")
    for service in everyday + emergency:
        fp = out / f"facilities_{service}.parquet"
        n = len(pd.read_parquet(fp)) if fp.exists() else "MISSING"
        print(f"  {service:>22}: {n}")

    # Shared routability probe: origins present in ANY OD matrix (any service,
    # any mode) — identical to the deprivation pipeline's definition.
    od_files = sorted(out.glob("od_*.parquet"))
    routable_ids: set = set()
    per_service_origins: dict[str, set] = {}
    for p in od_files:
        origins = set(pd.read_parquet(p, columns=["origin"])["origin"].unique().tolist())
        routable_ids |= origins
        # od_<service>_<mode>.parquet -> service is the middle token(s)
        stem = p.stem[len("od_"):]
        service = stem.rsplit("_", 1)[0]
        per_service_origins.setdefault(service, set()).update(origins)
    routable = cells.index.isin(routable_ids)
    routable = pd.Series(routable, index=cells.index)
    no_path = ~routable

    def reach_for(services: list[str]) -> pd.Series:
        reached: set = set()
        for s in services:
            reached |= per_service_origins.get(s, set())
        return pd.Series(cells.index.isin(reached), index=cells.index)

    print("\n=== shared no-network-path mask (both regimes) ===")
    print(f"  cells: {len(cells)}   no_path: {int(no_path.sum())} "
          f"({_pop_share(pop, no_path):.3%} pop)")

    # Emergency: legacy 'any-service-unreachable' mask, for comparison.
    em_reach_any = reach_for(emergency)
    em_unreach_any = ~em_reach_any
    print("\n=== emergency ===")
    print(f"  unreachable (any emergency service out of range): "
          f"{int(em_unreach_any.sum())} ({_pop_share(pop, em_unreach_any):.3%} pop)")
    print(f"  of which genuinely no_path: {int((em_unreach_any & no_path).sum())}")

    # Everyday: split (a) no_path vs (b) routable-but-service-far.
    ev_reach_any = reach_for(everyday)
    ev_unreach_any = ~ev_reach_any            # legacy any()-style everyday mask
    a_no_path = ev_unreach_any & no_path
    b_service_far = ev_unreach_any & routable
    print("\n=== everyday ===")
    print(f"  legacy 'any-service-unreachable' mask: {int(ev_unreach_any.sum())} "
          f"({_pop_share(pop, ev_unreach_any):.3%} pop)")
    print(f"    (a) no network path      : {int(a_no_path.sum())} "
          f"({_pop_share(pop, a_no_path):.3%} pop)   <- should ≈ emergency no_path")
    print(f"    (b) routable, no facility: {int(b_service_far.sum())} "
          f"({_pop_share(pop, b_service_far):.3%} pop)   <- badly deprived, keep on map")
    print("\n  per-service 'no facility in reach' among routable cells:")
    for s in everyday:
        far = routable & ~reach_for([s])
        print(f"    {s:>22}: {int(far.sum())} ({_pop_share(pop, far):.3%} pop)")

    print("\n=== reconciliation ===")
    print("  Expectation: everyday (a) ≈ emergency no_path (routability is "
          "service/mode-independent).")
    print("  If (b) >> (a), the everyday 'unreachable' mask was dominated by "
          "reachable-but-far cells — the Phase 1 finite-fill case, NOT masking.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", required=True)
    ap.add_argument("--project-root", default=".")
    args = ap.parse_args()
    diagnose(args.city, Path(args.project_root))


if __name__ == "__main__":
    main()
