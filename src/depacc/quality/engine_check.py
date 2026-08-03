"""Workstream E.1 — routing-engine cross-check.

Tier-1 runs the **friction** fast path: least-cost paths over the Weiss et al.
1 km walking / motorised surfaces. It is what makes a 48-city sample affordable,
and nothing has ever quantified how wrong it is. This module runs one city a
second time under an alternative engine (r5 over the real OSM street network),
holding *everything else fixed*, and reports the disagreement.

Run 30160444058 turned this from a validation nicety into a blocker. Two facts
from it:

* The friction **car** surface gives 99.0 % of Hamburg's cells a zero-minute pair
  for everyday services, and 68.9 % of the population sits at ``t_eff = 0`` for at
  least one everyday service even at baseline. A 1 km pixel containing a facility
  is a zero-minute trip for every cell inside it. That degeneracy killed the
  Layer-3 walk+car variant outright — the axis the plan expected to dominate the
  accessibility sweep cannot be evaluated at all on this engine.
* The **emergency regime is car-only**. Its whole distribution — median 3.9 min to
  an ED, p90 14.4, ``gini_emergency`` 0.62, an axis of the central city-plane
  result — is computed on that same quantised surface. With 27 EDs over a
  6135 km² FUA the zero-floor does not bite the way it does for supermarkets, but
  nothing bounds the error either.

**What is held fixed.** The comparison isolates the ROUTING ENGINE and nothing
else. The shadow run reuses the baseline's `cells.parquet` and — importantly —
its `facilities_*.parquet` verbatim, never re-extracting them. Hamburg's friction
config takes facilities from Overpass while an r5 config would take them from the
.pbf, and letting that vary would confound engine disagreement with facility-set
disagreement, which is Workstream E.2's separate question. Only the OD matrices
and everything downstream of them are recomputed.

Outputs (under ``<derived>/validation/``):
    <city>_engine_check.csv      per-quantity base vs alt, delta, rank agreement
    <city>_engine_scatter.png    cell-level travel time, friction vs alternative
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from depacc.divergence.colocation import weighted_spearman
from depacc.divergence.typology import class_shares, classify
from depacc.equity.indices import weighted_gini
from depacc.ingest.pipeline import derived_dir
from depacc.sensitivity.harness import flip_cells
from depacc.standardize import RegimeSurface, to_percentile

#: Ingest artefacts the shadow run inherits verbatim. Facilities are on this list
#: on purpose — see the module docstring.
_INHERITED = ("cells.parquet", "fua_boundary.parquet",
              # Reused when the baseline already fetched them; re-derived by
              # ensure_network() when the friction path never did.
              "network_pbf_path.txt", "gtfs_paths.txt")
_INHERITED_GLOBS = ("facilities_*.parquet",)


def shadow_city_id(city: str, engine: str) -> str:
    """Derived-dir id for the shadow run, NESTED inside the city's own directory.

    ``hamburg/engine_r5`` rather than a sibling ``hamburg__engine_r5``:
    ``tools/persist_results.py`` walks ``data/derived/*`` and treats each entry as
    a city, so a sibling would be published to ``depacc-results`` as a phantom
    city. Nested, it is invisible to that walk and travels in the same per-city
    derived cache as everything else it is compared against.
    """
    return f"{city}/engine_{engine}"


def shadow_config(cfg: dict, engine: str, modes: list[str] | None = None,
                  reverse_modes: list[str] | None = None) -> dict:
    """The city's config with the routing engine (and optionally the mode set
    and the reverse-routed modes) overridden. Everything else — services,
    cutoffs, softmin, catchment, deprivation functions, unreachable policy — is
    untouched, which is what makes the difference attributable to the engine.

    ``reverse_modes`` is a COST control, not a model parameter: it changes which
    direction R5 searches, not what is being measured. It belongs on the shadow
    only — the friction baseline routes over a raster and has no direction.
    """
    alt = copy.deepcopy(cfg)
    alt["routing"]["engine"] = engine
    if modes:
        alt["routing"]["modes"] = list(modes)
    if reverse_modes is not None:
        alt["routing"]["reverse_direction"] = list(reverse_modes)
    return alt


def prepare_shadow(cfg: dict, city: str, root: Path, engine: str,
                   modes: list[str] | None = None,
                   reverse_modes: list[str] | None = None,
                   ) -> tuple[dict, Path, Path]:
    """Create the shadow derived dir and populate it with the inherited ingest
    artefacts. Returns ``(alt_cfg, base_out, alt_out)``."""
    base_out = derived_dir(cfg, city, root)
    if not (base_out / "cells.parquet").exists():
        raise RuntimeError(
            f"no cells.parquet in {base_out} — run the baseline pipeline for "
            f"'{city}' before the engine check")
    alt_cfg = shadow_config(cfg, engine, modes, reverse_modes)
    alt_out = derived_dir(alt_cfg, shadow_city_id(city, engine), root)

    copied = []
    for name in _INHERITED:
        src = base_out / name
        if src.exists():
            shutil.copy2(src, alt_out / name)
            copied.append(name)
    for pattern in _INHERITED_GLOBS:
        for src in sorted(base_out.glob(pattern)):
            shutil.copy2(src, alt_out / src.name)
            copied.append(src.name)
    print(f"engine-check[{engine}]: inherited {len(copied)} ingest artefact(s) "
          f"from the baseline run (facilities included — this compares engines, "
          f"not facility sources)")
    return alt_cfg, base_out, alt_out


def ensure_network(alt_cfg: dict, city: str, root: Path, alt_out: Path) -> None:
    """Make sure the alternative engine's network inputs exist.

    The friction path never downloads a street network (``ingest/pipeline.py``
    only fetches the .pbf when facilities come from it), so a friction-configured
    city has no ``network_pbf_path.txt``. Fetch, clip and merge it here — WITHOUT
    re-extracting facilities, which the shadow run inherits.
    """
    if alt_cfg["routing"].get("engine") != "r5":
        return
    if alt_cfg.get("city", {}).get("synthetic"):
        return   # the demo fixture routes analytically; there is no network

    from depacc.ingest.pipeline import network_marker_valid

    if not network_marker_valid(alt_out / "network_pbf_path.txt"):
        import geopandas as gpd

        from depacc.ingest.osm import clip_pbf, fetch_pbfs, merge_pbfs

        fua = gpd.read_parquet(alt_out / "fua_boundary.parquet")
        pbfs = fetch_pbfs(alt_cfg, root)
        pad = 0.1
        minx, miny, maxx, maxy = fua.to_crs("EPSG:4326").total_bounds
        bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)
        raw_osm = root / alt_cfg["output"]["raw_root"] / "osm"
        clipped = [
            clip_pbf(p, bbox,
                     raw_osm / f"{p.name.removesuffix('.osm.pbf')}_{city}_clip.osm.pbf")
            for p in pbfs
        ]
        network_pbf = merge_pbfs(clipped, raw_osm / f"{city}_merged.osm.pbf")
        (alt_out / "network_pbf_path.txt").write_text(str(network_pbf))
        print(f"engine-check: street network ready ({network_pbf.name})")

    from depacc.ingest.pipeline import gtfs_list_valid

    if "transit" in (alt_cfg["routing"].get("modes") or []) \
            and not gtfs_list_valid(alt_out / "gtfs_paths.txt"):
        import geopandas as gpd

        from depacc.ingest.gtfs import fetch_gtfs

        fua = gpd.read_parquet(alt_out / "fua_boundary.parquet")
        feeds = fetch_gtfs(alt_cfg, root, fua)
        (alt_out / "gtfs_paths.txt").write_text("\n".join(map(str, feeds)))
        print(f"engine-check: GTFS feeds {[p.name for p in feeds]}")


def run_alternative(alt_cfg: dict, city: str, root: Path, engine: str):
    """Route and build the deprivation surfaces under the alternative engine.

    Deliberately calls the SAME ``run_access`` / ``run_deprivation`` the
    pipeline uses: a re-implementation would be one more place for the two paths
    to diverge, which is the mistake the Layer-3 sweep already made once.
    Divergence/equity are NOT run — the shadow must never reach ``cityplane.csv``
    or the cross-city tables.

    Propagates ``RoutingBudgetExhausted`` when the routing budget ran out: the
    surfaces must NOT be built on a partly-routed city, because every unrouted
    cell would come out looking service-deprived.
    """
    from depacc.access.matrices import run_access
    from depacc.deprivation.pipeline import run_deprivation

    shadow = shadow_city_id(city, engine)
    progress = run_access(alt_cfg, shadow, root)
    run_deprivation(alt_cfg, shadow, root)
    return progress


def write_asymmetry_report(val_dir: Path, city: str, engine: str,
                           asymmetry: dict) -> Path | None:
    """Persist the measured cost of reverse routing, if any was done.

    Reverse routing trades an exactness assumption (a symmetric network) for
    orders of magnitude of speed. That trade has to be auditable, so the
    measured error ships next to the comparison it enabled rather than living
    only in a log line.
    """
    if not asymmetry:
        return None
    val_dir.mkdir(parents=True, exist_ok=True)
    rows = [{"city": city, "alt_engine": engine, "matrix": label, **stats}
            for label, stats in sorted(asymmetry.items())]
    path = val_dir / f"{city}_engine_reverse_asymmetry.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"engine-check: reverse-routing asymmetry -> {path}")
    return path


def write_progress_manifest(val_dir: Path, city: str, engine: str,
                            exc: "RoutingBudgetExhausted") -> Path:
    """Record what an interrupted cross-check finished and what it still owes.

    Written into the validation directory the workflow uploads, so a run that
    was cut short reports its state as an artefact instead of as an empty
    upload with a "No files were found" warning — which is exactly how run
    30164334307 presented a five-hour timeout.
    """
    val_dir.mkdir(parents=True, exist_ok=True)
    rows = ([{"city": city, "alt_engine": engine, "matrix": m, "status": "done"}
             for m in exc.done]
            + [{"city": city, "alt_engine": engine, "matrix": m, "status": "pending"}
               for m in exc.pending])
    path = val_dir / f"{city}_engine_check_progress.csv"
    pd.DataFrame(rows, columns=["city", "alt_engine", "matrix", "status"]) \
        .to_csv(path, index=False)
    print(f"engine-check: INCOMPLETE after {exc.elapsed_min:.1f} min — "
          f"{len(exc.done)} matrix/matrices done, {len(exc.pending)} pending. "
          f"Progress is checkpointed in the per-city derived cache; "
          f"re-dispatch the workflow to resume. Manifest -> {path}")
    return path


# --------------------------------------------------------------------------- #
# Comparison                                                                   #
# --------------------------------------------------------------------------- #
def _weighted_rank_agreement(a: np.ndarray, b: np.ndarray,
                             pop: np.ndarray) -> float:
    """Population-weighted Spearman of two same-city quantities, via the audited
    percentile path (percentiles are the weighted ranks)."""
    mask = np.isfinite(a) & np.isfinite(b) & np.isfinite(pop) & (pop > 0)
    if mask.sum() < 2:
        return float("nan")
    sa = to_percentile(RegimeSurface(a[mask], pop[mask], "everyday", "cmp", "raw"))
    sb = to_percentile(RegimeSurface(b[mask], pop[mask], "everyday", "cmp", "raw"))
    return weighted_spearman(sa, sb)


def _weighted_median(v: np.ndarray, w: np.ndarray) -> float:
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        return float("nan")
    vv, ww = v[mask], w[mask]
    order = np.argsort(vv)
    vv, ww = vv[order], ww[order]
    cum = np.cumsum(ww) - 0.5 * ww
    return float(np.interp(0.5 * ww.sum(), cum, vv))


def _row(scope: str, item: str, base, alt, *, spearman=np.nan, n=np.nan,
         spearman_uncapped=np.nan, n_uncapped=np.nan) -> dict:
    base_f, alt_f = float(base), float(alt)
    delta = alt_f - base_f
    return {
        "scope": scope, "item": item,
        "base": base_f, "alt": alt_f, "delta": delta,
        "rel_delta": delta / base_f if base_f not in (0.0,) and np.isfinite(base_f)
        else np.nan,
        "spearman": spearman, "n": n,
        "spearman_uncapped": spearman_uncapped, "n_uncapped": n_uncapped,
    }


def _finite_fill_min(cfg: dict) -> float:
    """The constant a reachable-but-service-deprived cell's time is filled
    with (mirrors depacc.deprivation.pipeline). +inf when the config carries
    no fill at all — then no cell is treated as capped."""
    fill = ((cfg.get("unreachable") or {}).get("finite_fill_min")
            or (cfg.get("routing") or {}).get("max_time_min"))
    return float(fill) if fill else float("inf")


def _capped_mask(frame: pd.DataFrame, item: str, cfg: dict,
                 fill: float) -> np.ndarray:
    """Cells whose ``t_regime_<item>`` CONTAINS the finite fill.

    Run 30275890587 showed why this matters: every everyday p90 row read
    ``120.0 -> 120.0, delta 0`` (the fill, not agreement), the everyday scatter
    was a lattice at multiples of fill/5, and the everyday ρ = 0.867 was
    substantially a measure of the two engines agreeing on HOW MANY services
    are out of reach rather than on travel time. For a per-service item a cell
    is capped when its own time is the fill; for a regime composite (a weighted
    mean over its services' times) when ANY component service is capped, since
    one filled component already shifts the composite by ~fill/n_services.
    """
    if item in ("everyday", "emergency"):
        services = list(cfg.get(f"{item}_services", {}) or {})
        cols = [f"t_regime_{s}" for s in services
                if f"t_regime_{s}" in frame.columns]
        if not cols:
            return np.zeros(len(frame), dtype=bool)
        vals = frame[cols].to_numpy(float)
        with np.errstate(invalid="ignore"):
            return np.any(vals >= fill - 1e-9, axis=1)
    col = f"t_regime_{item}"
    if col not in frame.columns:
        return np.zeros(len(frame), dtype=bool)
    with np.errstate(invalid="ignore"):
        return frame[col].to_numpy(float) >= fill - 1e-9


def compare_engines(base_out: Path, alt_out: Path, cfg: dict, city: str,
                    alt_engine: str, threshold: float = 0.5) -> pd.DataFrame:
    """Base vs alternative engine on one city's surfaces.

    Three families of row:

    * ``travel_time`` — per regime and per service, the pop-weighted median and
      p90 over the cells BOTH engines reached, plus the population-weighted
      Spearman between them. The Spearman is the number that matters for this
      project: every headline output is rank-based, so an engine that shifts
      all times by a constant costs nothing while one that REORDERS cells
      invalidates the typology.
    * ``coverage`` — the population share each engine reaches at all, which the
      paired travel-time rows deliberately hold constant.
    * ``indicator`` — the city-row scalars (both Ginis, ρ, HH share) recomputed
      identically on each engine's surfaces.
    * ``typology`` — the population share whose co-location class changes.
    """
    base = pd.read_parquet(base_out / "surfaces.parquet")
    alt = pd.read_parquet(alt_out / "surfaces.parquet")
    alt = alt.reindex(base.index)
    pop = base["population"].to_numpy(float)
    rows: list[dict] = []

    services = [c[len("t_regime_"):] for c in base.columns
                if c.startswith("t_regime_")]
    for item in sorted(services, key=lambda s: (s not in ("everyday", "emergency"), s)):
        col = f"t_regime_{item}"
        if col not in alt.columns:
            print(f"  engine-check: '{col}' absent under {alt_engine}; skipped")
            continue
        a, b = base[col].to_numpy(float), alt[col].to_numpy(float)
        pos = pop > 0
        both = np.isfinite(a) & np.isfinite(b) & pos
        # PAIRED comparison: both summaries run on the cells BOTH engines
        # reached. Summarising each engine over its own reachable set would mix
        # a level difference with a composition difference — an engine that
        # drops the far periphery would look faster for that reason alone.
        # The composition difference is not discarded, it is reported
        # separately as the coverage rows below.
        # One rank agreement per ITEM, repeated on both of its rows: it is a
        # property of the cell-level series, not of the summary statistic, and a
        # blank on the p90 row reads as "not computed" rather than "same number".
        rho = _weighted_rank_agreement(a, b, pop)
        # ...and once more with every fill-capped cell removed FROM BOTH
        # engines: `spearman` on a capped series partly measures agreement on
        # who is cut off, `spearman_uncapped` measures agreement on travel time
        # where both engines actually route. Read them together — a large gap
        # says the headline ρ leans on the cap.
        fill = _finite_fill_min(cfg)
        uncapped = both & ~_capped_mask(base, item, cfg, fill) \
            & ~_capped_mask(alt, item, cfg, fill)
        rho_unc = _weighted_rank_agreement(
            np.where(uncapped, a, np.nan), np.where(uncapped, b, np.nan), pop)
        rows.append(_row("travel_time", f"{item}_median_min",
                         _weighted_median(a[both], pop[both]),
                         _weighted_median(b[both], pop[both]),
                         spearman=rho, n=int(both.sum()),
                         spearman_uncapped=rho_unc, n_uncapped=int(uncapped.sum())))
        rows.append(_row("travel_time", f"{item}_p90_min",
                         np.nanpercentile(a[both], 90) if both.any() else np.nan,
                         np.nanpercentile(b[both], 90) if both.any() else np.nan,
                         spearman=rho, n=int(both.sum()),
                         spearman_uncapped=rho_unc, n_uncapped=int(uncapped.sum())))
        # Who each engine can reach at all, before the pairing throws the
        # disagreement away. A large gap here means the paired rows above speak
        # for a shrinking slice of the city and must be read with that in mind.
        pop_total = pop[pos].sum()
        rows.append(_row("coverage", f"{item}_reachable_pop_share",
                         pop[np.isfinite(a) & pos].sum() / pop_total
                         if pop_total > 0 else np.nan,
                         pop[np.isfinite(b) & pos].sum() / pop_total
                         if pop_total > 0 else np.nan,
                         n=int(both.sum())))

    surfaces = {}
    for regime in ("everyday", "emergency"):
        col = f"deprivation_{regime}"
        if col not in base.columns or col not in alt.columns:
            continue
        sb = RegimeSurface(base[col].to_numpy(float), pop, regime, city, "raw")
        sa = RegimeSurface(alt[col].to_numpy(float), pop, regime, city, "raw")
        surfaces[regime] = (sb, sa)
        rows.append(_row("indicator", f"gini_{regime}",
                         weighted_gini(sb.values, pop),
                         weighted_gini(sa.values, pop)))

    if {"everyday", "emergency"} <= surfaces.keys():
        pcts = {r: (to_percentile(sb), to_percentile(sa))
                for r, (sb, sa) in surfaces.items()}
        rho_b = weighted_spearman(pcts["everyday"][0], pcts["emergency"][0])
        rho_a = weighted_spearman(pcts["everyday"][1], pcts["emergency"][1])
        rows.append(_row("indicator", "spearman_rho", rho_b, rho_a))

        lab_b = classify(pcts["everyday"][0].values, pcts["emergency"][0].values,
                         threshold)
        lab_a = classify(pcts["everyday"][1].values, pcts["emergency"][1].values,
                         threshold)
        sh_b = class_shares(lab_b, pop)["population_share"].to_dict()
        sh_a = class_shares(lab_a, pop)["population_share"].to_dict()
        for cls in ("LL", "LH", "HL", "HH"):
            rows.append(_row("indicator", f"share_{cls}_{int(threshold * 100)}",
                             sh_b.get(cls, np.nan), sh_a.get(cls, np.nan)))
        fc = flip_cells(lab_b, [lab_a], pop)
        rows.append(_row("typology", f"flip_pop_share_{int(threshold * 100)}",
                         0.0, fc["sensitive_pop_share"]))

    table = pd.DataFrame(rows)
    table.insert(0, "alt_engine", alt_engine)
    table.insert(0, "base_engine", cfg["routing"].get("engine", "r5"))
    table.insert(0, "city", city)
    return table


# --------------------------------------------------------------------------- #
# Figure                                                                       #
# --------------------------------------------------------------------------- #
def _scatter(base_out: Path, alt_out: Path, cfg: dict, city: str,
             alt_engine: str, table: pd.DataFrame, out_png: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover - viz extra not installed
        print("  matplotlib not installed; skipping engine scatter")
        return
    from depacc.viz.pipeline import _watermark

    base = pd.read_parquet(base_out / "surfaces.parquet")
    alt = pd.read_parquet(alt_out / "surfaces.parquet").reindex(base.index)
    base_engine = cfg["routing"].get("engine", "r5")
    name = cfg["city"].get("name", city)

    regimes = [r for r in ("everyday", "emergency")
               if f"t_regime_{r}" in base.columns and f"t_regime_{r}" in alt.columns]
    if not regimes:
        return
    fig, axes = plt.subplots(1, len(regimes), figsize=(5.6 * len(regimes), 5.2),
                             squeeze=False)
    for ax, regime in zip(axes[0], regimes):
        a = base[f"t_regime_{regime}"].to_numpy(float)
        b = alt[f"t_regime_{regime}"].to_numpy(float)
        m = np.isfinite(a) & np.isfinite(b)
        hb = ax.hexbin(a[m], b[m], gridsize=60, bins="log", mincnt=1,
                       cmap="viridis", linewidths=0)
        hi = float(np.nanpercentile(np.concatenate([a[m], b[m]]), 99.5)) if m.any() else 1.0
        ax.plot([0, hi], [0, hi], color="#d1495b", lw=1.2, ls="--", label="1:1")
        ax.set_xlim(0, hi)
        ax.set_ylim(0, hi)
        rho = table.query("item == @regime + '_median_min'")["spearman"]
        rho_txt = f"ρ = {float(rho.iloc[0]):.3f}" if len(rho) and np.isfinite(rho.iloc[0]) else ""
        ax.set_title(f"{regime} — {rho_txt}", fontsize=10)
        ax.set_xlabel(f"{base_engine} t_regime (min)")
        ax.set_ylabel(f"{alt_engine} t_regime (min)")
        ax.legend(frameon=False, fontsize=8, loc="lower right")
        fig.colorbar(hb, ax=ax, label="cells (log)")
    fig.suptitle(f"{name}: routing-engine cross-check, {base_engine} vs {alt_engine}",
                 fontsize=12)
    _watermark(fig, cfg)
    fig.tight_layout()
    fig.savefig(out_png, dpi=180, bbox_inches="tight")
    plt.close(fig)


def qq_table(base: pd.DataFrame, alt: pd.DataFrame, cfg: dict,
             quantiles: np.ndarray | None = None) -> pd.DataFrame:
    """E.4 — the resolution sanity check as paired population-weighted
    quantiles of ``t_regime_*`` per regime, uncapped cells only.

    The plan asked for ~200 random cells' friction-vs-network walk times in a
    quantile-quantile plot; the full population-weighted quantile curves are
    the same check without the sampling noise. Fill-capped cells are excluded
    on BOTH engines (via :func:`_capped_mask`) so the curves compare travel
    times, not the finite-fill constant — the §7.1 capped-lattice caveat.
    """
    if quantiles is None:
        quantiles = np.arange(1, 100) / 100.0
    fill = _finite_fill_min(cfg)
    pop = base["population"].to_numpy(float)
    rows = []
    for regime in ("everyday", "emergency"):
        col = f"t_regime_{regime}"
        if col not in base.columns or col not in alt.columns:
            continue
        a = base[col].to_numpy(float)
        b = alt[col].to_numpy(float)
        capped = _capped_mask(base, regime, cfg, fill) | _capped_mask(alt, regime, cfg, fill)
        m = np.isfinite(a) & np.isfinite(b) & np.isfinite(pop) & (pop > 0) & ~capped
        if not m.any():
            continue
        for q in quantiles:
            rows.append({
                "regime": regime, "quantile": float(q),
                "base_min": _weighted_quantile(a[m], pop[m], q),
                "alt_min": _weighted_quantile(b[m], pop[m], q),
            })
    return pd.DataFrame(rows, columns=["regime", "quantile", "base_min", "alt_min"])


def _weighted_quantile(v: np.ndarray, w: np.ndarray, q: float) -> float:
    order = np.argsort(v)
    v, w = v[order], w[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, q * cum[-1])])


def _qq_plot(base_out: Path, alt_out: Path, cfg: dict, city: str,
             alt_engine: str, out_png: Path) -> pd.DataFrame | None:
    """Write the E.4 QQ table + figure (``<city>_engine_qq.csv/.png``)."""
    base = pd.read_parquet(base_out / "surfaces.parquet")
    alt = pd.read_parquet(alt_out / "surfaces.parquet").reindex(base.index)
    table = qq_table(base, alt, cfg)
    if table.empty:
        return None
    table.insert(0, "city", city)
    table.to_csv(out_png.with_suffix(".csv"), index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover - viz extra not installed
        print("  matplotlib not installed; skipping engine QQ figure")
        return table
    from depacc.viz.pipeline import _watermark

    base_engine = cfg["routing"].get("engine", "r5")
    name = cfg["city"].get("name", city)
    regimes = list(table.regime.unique())
    fig, axes = plt.subplots(1, len(regimes), figsize=(5.2 * len(regimes), 5.0),
                             squeeze=False)
    for ax, regime in zip(axes[0], regimes):
        block = table[table.regime == regime]
        hi = float(max(block.base_min.max(), block.alt_min.max())) or 1.0
        ax.plot([0, hi], [0, hi], color="#d1495b", lw=1.2, ls="--", label="1:1")
        ax.plot(block.base_min, block.alt_min, color="#1d3557", lw=1.6,
                marker=".", ms=3, label="pop-weighted quantiles 1–99")
        ax.set_xlabel(f"{base_engine} t_regime quantile (min)")
        ax.set_ylabel(f"{alt_engine} t_regime quantile (min)")
        ax.set_title(f"{regime} (uncapped cells)", fontsize=10)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle(f"{name}: E.4 resolution QQ — {base_engine} vs {alt_engine}",
                 fontsize=12)
    _watermark(fig, cfg)
    fig.tight_layout()
    fig.savefig(out_png, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return table


# --------------------------------------------------------------------------- #
# Driver                                                                       #
# --------------------------------------------------------------------------- #
def run_engine_check(cfg: dict, city: str, root: Path, engine: str = "r5",
                     modes: list[str] | None = None,
                     threshold: float = 0.5,
                     reuse: bool = True,
                     reverse_modes: list[str] | None = None,
                     self_test: bool = False) -> pd.DataFrame:
    """Full E.1 cross-check for one city. Returns the comparison table."""
    base_engine = cfg["routing"].get("engine", "r5")
    if base_engine == engine and not modes and not self_test:
        # REFUSE, do not warn. Comparing an engine against itself returns a
        # table of exact zeros by construction — and it pays for a second full
        # routing of the city to get there. Run 30476375657 dispatched exactly
        # this: Köln's config omitted `routing.engine`, so it inherited r5 from
        # the defaults and the "friction vs r5" cross-check was r5 vs r5, with
        # both sides routed forward. A warning printed at minute zero of a
        # multi-hour job is not a guard; it scrolls past and the run burns
        # anyway. The self-test is still available, explicitly.
        raise ValueError(
            f"engine-check for '{city}' would compare '{engine}' against "
            f"itself: the city's configured routing.engine is already "
            f"'{base_engine}', so every delta is zero by construction and the "
            f"run pays for a second full routing to prove it. Point --engine "
            f"at a DIFFERENT engine (the cross-check exists to bound the "
            f"friction fast path against r5), set routing.engine in "
            f"config/cities/{city}.yaml to the baseline you mean, or pass "
            f"self_test=True if you really want the plumbing self-test.")
    if base_engine == engine:
        print(f"NOTE: engine-check comparing '{engine}' against itself — every "
              f"delta should come out zero; this is the plumbing self-test")
    from depacc.access.matrices import RoutingBudgetExhausted

    # Created BEFORE the multi-hour routing so an interrupted run still has
    # somewhere to leave its progress manifest for the artefact upload.
    val_dir = root / cfg["output"]["root"] / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    alt_cfg, base_out, alt_out = prepare_shadow(cfg, city, root, engine,
                                                modes, reverse_modes)
    ensure_network(alt_cfg, city, root, alt_out)
    if reuse and (alt_out / "surfaces.parquet").exists():
        print(f"engine-check: reusing the cached {engine} surfaces in {alt_out}")
    else:
        try:
            progress = run_alternative(alt_cfg, city, root, engine)
        except RoutingBudgetExhausted as exc:
            write_progress_manifest(val_dir, city, engine, exc)
            raise
        write_asymmetry_report(val_dir, city, engine, progress.asymmetry)

    table = compare_engines(base_out, alt_out, cfg, city, engine, threshold)
    table.to_csv(val_dir / f"{city}_engine_check.csv", index=False)
    _scatter(base_out, alt_out, cfg, city, engine, table,
             val_dir / f"{city}_engine_scatter.png")
    _qq_plot(base_out, alt_out, cfg, city, engine,
             val_dir / f"{city}_engine_qq.png")

    tt = table[table.scope == "travel_time"].dropna(subset=["spearman"])
    if not tt.empty:
        worst = tt.loc[tt["spearman"].idxmin()]
        print(f"  {city}: rank agreement {base_engine} vs {engine} — "
              f"worst {worst['item']} ρ={worst['spearman']:.3f}, "
              f"median ρ={tt['spearman'].median():.3f}")
    flip = table[table.scope == "typology"]
    if not flip.empty:
        print(f"  {city}: {float(flip.iloc[0]['alt']):.1%} of the population "
              f"changes co-location class under {engine}")
    print(f"engine-check outputs -> {val_dir}")
    return table
