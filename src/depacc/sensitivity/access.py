"""Layer-3 accessibility sensitivity — the CHEAP variants (from cached inputs).

Layers 1/2 (:mod:`depacc.sensitivity.harness`) sweep the deprivation FUNCTION
on the saved deprivation-free travel times ``t_regime_*`` and — because the
typology is rank-based and every g(t) is monotone — cannot move the class
shares by construction. Layer 3 sweeps the ACCESSIBILITY knobs that build
those travel times in the first place, so it CAN move the ranks (and thus the
HH share, the coupling ρ and the flip-cells).

The whole point is that these variants are cheap: they re-run the DEPRIVATION
stage only, reading the SAVED OD parquets (``od_<service>_<mode>.parquet``) and
facility tables — no re-routing. Each variant changes exactly one knob from the
config baseline and recomputes the everyday effective-time surface:

    softmin.kappa        {0.1, 0.25, 0.5, 1, 2}     soft-min smoothing
    catchment.gamma      {0, 0.25, 0.5, 1}          2SFCA congestion exponent
    catchment.bandwidth  {10, 15, 20} (walk, min)   catchment kernel bandwidth
    routing.k_nearest    {10, 30}                   subset the saved k = 30 OD
    nearest_only                                    hard-min (κ → ∞), no bonus
    unreachable          cap value / exclude        unreachable-cell treatment
    everyday mode set    walk vs walk+car           min travel time across modes

The emergency regime is nearest-facility of a fixed mode and is untouched by
the everyday accessibility axis, so ``t_regime_emergency`` is read once from the
saved ``surfaces.parquet`` and reused for every variant.

Expensive variants (per-variant RE-ROUTING) — friction vs r5 engine, transit
inclusion for Tier-2 — are intentionally NOT here; they are deferred until the
pilot sample exists (Workstream E does the friction-vs-r5 run for Hamburg).

Outputs (under ``<derived>/sensitivity/``):
    <city>_access_sensitivity.csv     per-variant HH share, ρ, Ginis, flips
    <city>_access_flip_cells.png      map of cells that flip class under ANY variant
    <city>_access_acceptance.csv      (Hamburg) which knobs beat the threshold axis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from depacc.access.matrices import keep_k_nearest
from depacc.config import deprivation_spec, load_config
from depacc.deprivation.functions import DeprivationFunction
from depacc.deprivation.surfaces import emergency_surface, everyday_surface
from depacc.divergence.colocation import weighted_spearman
from depacc.divergence.typology import class_shares, classify
from depacc.equity.indices import weighted_gini
from depacc.ingest.pipeline import derived_dir
from depacc.sensitivity.harness import flip_cells
from depacc.standardize import RegimeSurface, to_percentile

# κ → ∞ sentinel for the nearest-only variant: at this smoothing the soft-min
# is the hard minimum to well under a micro-minute for any realistic spread of
# reachable times, so no separate code path is needed.
_NEAREST_ONLY_KAPPA = 1.0e6

# Task defaults for the sweep grid, used when config/sensitivity.yaml does not
# pin a given axis. These mirror the *_sensitivity lists in config/defaults.yaml.
_DEFAULT_GRID = {
    "kappa": [0.1, 0.25, 0.5, 1.0, 2.0],
    "gamma": [0.0, 0.25, 0.5, 1.0],
    "bandwidth_min": [10, 15, 20],
    "k_nearest": [10, 30],
    "nearest_only": True,
    "unreachable": ["cap_at_max_time", "exclude"],
    "everyday_modes": [["walk"], ["walk", "car"]],
}

_THRESHOLDS = (0.4, 0.5, 0.6, 0.75)


@dataclass(frozen=True)
class AccessVariant:
    """One Layer-3 accessibility variant: a one-knob override of the baseline
    everyday-access parameters. ``knob`` names the axis (also the acceptance
    grouping key); ``params`` is the full resolved parameter set."""

    name: str
    knob: str
    params: dict = field(hash=False)


# --------------------------------------------------------------------------- #
# Baseline parameters + variant expansion                                     #
# --------------------------------------------------------------------------- #
def baseline_params(cfg: dict) -> dict:
    """The everyday-access parameters as configured (the sweep's fixed point)."""
    ev_modes = list(cfg["regimes"]["everyday"]["modes"])
    bw_by_mode = cfg["catchment"]["kernel"]["bandwidth_min"]
    return {
        "kappa": float(cfg["softmin"]["kappa"]),
        "gamma": float(cfg["catchment"]["gamma"]),
        "bandwidth": float(bw_by_mode[ev_modes[0]]),
        "kernel_type": cfg["catchment"]["kernel"].get("type", "gaussian"),
        "reference": cfg["catchment"].get("reference", "weighted_median"),
        "factor_clip": tuple(cfg["catchment"].get("factor_clip", (0.5, 4.0))),
        "k": int(cfg["routing"].get("k_nearest", 30)),
        "policy": cfg["unreachable"]["policy"],
        "cap_min": float(cfg["routing"]["max_time_min"]),
        "modes": ev_modes,
        "nearest_only": False,
    }


def expand_access_variants(cfg: dict, grid: dict | None,
                           available_modes: set[str] | None = None
                           ) -> list[AccessVariant]:
    """Baseline + one-knob-at-a-time Layer-3 variants.

    ``grid`` is the ``sensitivity.accessibility`` block; missing axes fall back
    to :data:`_DEFAULT_GRID`. Variants whose mode set is not fully present in
    ``available_modes`` (the modes actually routed and saved) are dropped, so a
    walk-only run silently skips the walk+car variant instead of crashing.
    """
    grid = dict(grid or {})
    base = baseline_params(cfg)
    variants = [AccessVariant("baseline", "baseline", base)]

    def _get(key):
        return grid.get(key, _DEFAULT_GRID[key])

    for kap in _get("kappa"):
        if float(kap) == base["kappa"]:
            continue
        variants.append(AccessVariant(
            f"kappa_{kap}", "kappa", {**base, "kappa": float(kap)}))

    for gam in _get("gamma"):
        if float(gam) == base["gamma"]:
            continue
        variants.append(AccessVariant(
            f"gamma_{gam}", "gamma", {**base, "gamma": float(gam)}))

    for bw in _get("bandwidth_min"):
        if float(bw) == base["bandwidth"]:
            continue
        variants.append(AccessVariant(
            f"bandwidth_{bw}", "bandwidth", {**base, "bandwidth": float(bw)}))

    for kk in _get("k_nearest"):
        if int(kk) == base["k"]:
            continue
        variants.append(AccessVariant(
            f"k_nearest_{kk}", "k_nearest", {**base, "k": int(kk)}))

    if _get("nearest_only"):
        variants.append(AccessVariant(
            "nearest_only", "nearest_only", {**base, "nearest_only": True}))

    for pol in _get("unreachable"):
        # A plain policy name, or a numeric alternative cap value (minutes).
        if isinstance(pol, (int, float)) and not isinstance(pol, bool):
            if float(pol) == base["cap_min"]:
                continue
            variants.append(AccessVariant(
                f"unreachable_cap_{pol}", "unreachable",
                {**base, "policy": "cap_at_max_time", "cap_min": float(pol)}))
        else:
            if str(pol) == base["policy"]:
                continue
            variants.append(AccessVariant(
                f"unreachable_{pol}", "unreachable", {**base, "policy": str(pol)}))

    for modes in _get("everyday_modes"):
        modes = list(modes)
        if modes == base["modes"]:
            continue
        variants.append(AccessVariant(
            f"everyday_modes_{'+'.join(modes)}", "everyday_mode",
            {**base, "modes": modes}))

    if available_modes is not None:
        kept = []
        for v in variants:
            need = set(v.params["modes"])
            if need <= available_modes:
                kept.append(v)
            else:
                missing = sorted(need - available_modes)
                print(f"  skip variant '{v.name}': modes {missing} not routed/saved")
        variants = kept
    return variants


# --------------------------------------------------------------------------- #
# From-cache surface recomputation                                            #
# --------------------------------------------------------------------------- #
def _combined_od_subset(out: Path, service: str, modes: list[str],
                        k: int) -> pd.DataFrame | None:
    """Elementwise-min travel time across ``modes`` from the SAVED OD parquets,
    then trimmed to the k nearest destinations per origin (subsetting the saved
    k = 30 matrix; a no-op when k >= the saved k)."""
    frames = []
    for mode in modes:
        p = out / f"od_{service}_{mode}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return None
    od = pd.concat(frames, ignore_index=True)
    od = od.groupby(["origin", "dest"], as_index=False)["time"].min()
    if k and k > 0:
        od = keep_k_nearest(od, k)
    return od


def available_od_modes(out: Path, services: list[str]) -> set[str]:
    """Modes for which at least one saved OD parquet exists across ``services``."""
    modes: set[str] = set()
    for p in out.glob("od_*.parquet"):
        stem = p.stem  # od_<service>_<mode>
        for s in services:
            prefix = f"od_{s}_"
            if stem.startswith(prefix):
                modes.add(stem[len(prefix):])
    return modes


def routable_mask(out: Path, cells: pd.DataFrame) -> pd.Series:
    """Shared, service- and mode-independent routability probe (methods.md §2),
    reproduced from the SAVED OD: a cell has a network path iff it reaches at
    least one facility of ANY service in ANY mode. This is what the deprivation
    stage uses to split genuinely-unroutable (masked) cells from reachable-but-
    service-deprived ones, so the sweep must use the SAME mask to stay
    consistent with the baseline surfaces."""
    routable_ids: set = set()
    for p in out.glob("od_*.parquet"):
        routable_ids.update(
            pd.read_parquet(p, columns=["origin"])["origin"].unique().tolist())
    return pd.Series(cells.index.isin(routable_ids), index=cells.index)


def everyday_t_regime(cfg: dict, out: Path, cells: pd.DataFrame, params: dict,
                      *, routable: pd.Series | None = None,
                      finite_fill: float | None = None) -> np.ndarray | None:
    """Recompute the composite everyday regime travel time ``t_regime_everyday``
    from cached inputs under one variant's access parameters. Reproduces the
    deprivation stage's reachability semantics: reachable-but-service-deprived
    cells get ``finite_fill`` (stay on the map), genuinely unroutable cells are
    NaN-masked with the shared no-path mask. Returns an array aligned to
    ``cells.index``, or None if no everyday service has an OD for the modes."""
    # The deprivation FUNCTION is irrelevant to t_regime (= t_eff, a travel
    # time); pass the baseline everyday g only because everyday_surface computes
    # a deprivation column internally. We discard it.
    g_ev = DeprivationFunction.from_spec(
        deprivation_spec(cfg, "everyday"), context="everyday deprivation")
    kappa = _NEAREST_ONLY_KAPPA if params["nearest_only"] else params["kappa"]
    kernel = {"type": params["kernel_type"], "bandwidth": params["bandwidth"]}
    weights = cfg["regimes"]["everyday"].get("composite_weights") or {}
    if routable is None:
        routable = routable_mask(out, cells)
    if finite_fill is None:
        finite_fill = float(cfg["unreachable"].get("finite_fill_min")
                            or cfg["routing"]["max_time_min"])

    per_service, used = [], []
    for service in cfg.get("everyday_services", {}):
        od = _combined_od_subset(out, service, params["modes"], params["k"])
        fac_path = out / f"facilities_{service}.parquet"
        if od is None or od.empty or not fac_path.exists():
            continue
        supply = pd.read_parquet(fac_path).set_index("dest_id")["capacity"]
        surf = everyday_surface(
            od, cells, supply, g_ev,
            kappa=kappa, kernel=kernel, gamma=params["gamma"],
            reference=params["reference"], factor_clip=params["factor_clip"],
            policy=params["policy"], max_time_min=params["cap_min"],
            routable=routable, finite_fill_min=finite_fill,
        )
        per_service.append(surf["t_eff"].to_numpy(float))
        used.append(service)
    if not per_service:
        return None
    w = np.array([float(weights.get(s, 1.0)) for s in used])
    vals = np.column_stack(per_service)
    t = _weighted_row_mean(vals, w)
    # Mask the genuinely-unroutable (no-path) cells, exactly as the deprivation
    # stage masks t_regime_everyday — one shared mask for both regimes.
    no_path = ~routable.reindex(cells.index).fillna(False).to_numpy(bool)
    return np.where(no_path, np.nan, t)


def _weighted_row_mean(vals: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Row mean over non-NaN services, weights renormalised per row (matches
    depacc.deprivation.pipeline._weighted_row_mean)."""
    mask = ~np.isnan(vals)
    wm = np.where(mask, w[None, :], 0.0)
    denom = wm.sum(axis=1)
    with np.errstate(invalid="ignore"):
        out = np.nansum(vals * wm, axis=1) / denom
    return np.where(denom > 0, out, np.nan)


# --------------------------------------------------------------------------- #
# Targets                                                                      #
# --------------------------------------------------------------------------- #
def access_variant_targets(t_everyday: np.ndarray, t_emergency: np.ndarray,
                           population: np.ndarray, everyday_spec: dict,
                           emergency_spec: dict, city_id: str,
                           threshold: float) -> dict:
    """Standardised / rank targets for one Layer-3 variant. Everything returned
    is scale-free or population-weighted; raw magnitudes never leave here.
    Adds the coupling ρ (weighted Spearman of the two percentile surfaces) to
    the harness's stable-target set, and returns the per-cell labels for flips.
    """
    g_ev = DeprivationFunction.from_spec(everyday_spec, context="everyday")
    g_em = DeprivationFunction.from_spec(emergency_spec, context="emergency")
    ev = RegimeSurface(g_ev(t_everyday), population, "everyday", city_id, "raw")
    em = RegimeSurface(g_em(t_emergency), population, "emergency", city_id, "raw")
    gini_ev = weighted_gini(ev.values, population)
    gini_em = weighted_gini(em.values, population)
    ev_p = to_percentile(ev)
    em_p = to_percentile(em)
    labels = classify(ev_p.values, em_p.values, threshold)
    shares = class_shares(labels, population)["population_share"].to_dict()
    return {
        "gini_everyday": gini_ev,
        "gini_emergency": gini_em,
        "divergence_gap": gini_em - gini_ev,
        "spearman_rho": weighted_spearman(ev_p, em_p),
        **{f"share_{c}": shares.get(c, np.nan) for c in ("LL", "LH", "HL", "HH")},
        "labels": labels,
    }


# --------------------------------------------------------------------------- #
# Per-city driver                                                             #
# --------------------------------------------------------------------------- #
def city_access_sensitivity(cfg: dict, city: str, root: Path, grid: dict,
                            threshold: float = 0.5) -> pd.DataFrame | None:
    """Run every Layer-3 variant for one city from its cached OD + surfaces.
    Writes the per-variant CSV and the flip-cell map; returns the table (or
    None when the city's cache is incomplete)."""
    out = derived_dir(cfg, city, root)
    cells_path = out / "cells.parquet"
    surf_path = out / "surfaces.parquet"
    if not cells_path.exists() or not surf_path.exists():
        print(f"  {city}: no cached cells/surfaces — run the pipeline first; skipped")
        return None
    cells = pd.read_parquet(cells_path).set_index("cell_id")
    surfaces = pd.read_parquet(surf_path)
    if "t_regime_emergency" not in surfaces:
        print(f"  {city}: surfaces.parquet lacks t_regime_emergency; skipped")
        return None
    pop = cells["population"].to_numpy(float)
    t_em = surfaces["t_regime_emergency"].to_numpy(float)  # invariant across variants
    ev_spec = deprivation_spec(cfg, "everyday")
    em_spec = deprivation_spec(cfg, "emergency")

    # Shared no-path mask + finite-fill, computed once and reused by every
    # variant so the recomputed everyday surface matches the deprivation stage.
    routable = routable_mask(out, cells)
    finite_fill = float(cfg["unreachable"].get("finite_fill_min")
                        or cfg["routing"]["max_time_min"])

    services = list(cfg.get("everyday_services", {}))
    avail = available_od_modes(out, services)
    variants = expand_access_variants(cfg, grid, available_modes=avail)

    rows, base_labels, var_label_sets = [], None, []
    for v in variants:
        t_ev = everyday_t_regime(cfg, out, cells, v.params,
                                 routable=routable, finite_fill=finite_fill)
        if t_ev is None:
            print(f"  {city}: variant '{v.name}' has no everyday OD; skipped")
            continue
        tgt = access_variant_targets(t_ev, t_em, pop, ev_spec, em_spec, city,
                                     threshold)
        labels = tgt.pop("labels")
        if v.name == "baseline":
            base_labels = labels
        else:
            var_label_sets.append(labels)
        p = v.params
        rows.append({
            "city": city, "axis": v.knob, "variant": v.name,
            "kappa": (np.inf if p["nearest_only"] else p["kappa"]),
            "gamma": p["gamma"], "bandwidth": p["bandwidth"], "k_nearest": p["k"],
            "policy": p["policy"], "cap_min": p["cap_min"],
            "modes": "+".join(p["modes"]), "threshold": threshold,
            **{k: tgt[k] for k in ("gini_everyday", "gini_emergency",
                                   "divergence_gap", "spearman_rho",
                                   "share_LL", "share_LH", "share_HL", "share_HH")},
        })

    if base_labels is None:
        print(f"  {city}: baseline variant unavailable; skipped")
        return None

    # Per-variant flip share vs baseline (pop share of cells changing class).
    for row in rows:
        if row["variant"] == "baseline":
            row["flip_pop_share"] = 0.0
            continue
    for row, labels in zip([r for r in rows if r["variant"] != "baseline"],
                           var_label_sets):
        fc = flip_cells(base_labels, [labels], pop)
        row["flip_pop_share"] = fc["sensitive_pop_share"]

    # Threshold-axis block on the BASELINE surfaces (the comparison axis): how
    # far the "how high is high" choice alone moves the HH share. ρ is coupling
    # and threshold-independent, so its threshold-axis range is 0 by definition.
    t_ev_base = everyday_t_regime(cfg, out, cells, baseline_params(cfg),
                                  routable=routable, finite_fill=finite_fill)
    g_ev = DeprivationFunction.from_spec(ev_spec, context="everyday")
    g_em = DeprivationFunction.from_spec(em_spec, context="emergency")
    ev_p = to_percentile(RegimeSurface(g_ev(t_ev_base), pop, "everyday", city, "raw"))
    em_p = to_percentile(RegimeSurface(g_em(t_em), pop, "emergency", city, "raw"))
    rho_base = weighted_spearman(ev_p, em_p)
    for thr in _THRESHOLDS:
        labels = classify(ev_p.values, em_p.values, thr)
        shares = class_shares(labels, pop)["population_share"].to_dict()
        rows.append({
            "city": city, "axis": "threshold", "variant": f"threshold_{thr}",
            "kappa": np.nan, "gamma": np.nan, "bandwidth": np.nan,
            "k_nearest": np.nan, "policy": "", "cap_min": np.nan, "modes": "",
            "threshold": thr, "gini_everyday": np.nan, "gini_emergency": np.nan,
            "divergence_gap": np.nan, "spearman_rho": rho_base,
            **{f"share_{c}": shares.get(c, np.nan) for c in ("LL", "LH", "HL", "HH")},
            "flip_pop_share": np.nan,
        })

    table = pd.DataFrame(rows)
    sens_dir = root / cfg["output"]["root"] / "sensitivity"
    sens_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(sens_dir / f"{city}_access_sensitivity.csv", index=False)

    # Union flip-cell map: cells that flip class under ANY variant vs baseline.
    if var_label_sets:
        fc = flip_cells(base_labels, var_label_sets, pop)
        _flip_cell_map(surfaces, fc["flip_mask"], cfg, city,
                       sens_dir / f"{city}_access_flip_cells.png",
                       sensitive_share=fc["sensitive_pop_share"])
    return table


# --------------------------------------------------------------------------- #
# Acceptance table                                                            #
# --------------------------------------------------------------------------- #
def acceptance_table(table: pd.DataFrame) -> pd.DataFrame:
    """Which Layer-3 knobs move the HH share / ρ by MORE than the threshold
    axis does. Each knob's range spans its variants together with the baseline
    (so the range is measured from the fixed point); the threshold axis's HH
    range is its own; its ρ range is 0 by construction."""
    thr = table[table.axis == "threshold"]
    hh_thr = _range(thr["share_HH"])
    rho_thr = 0.0  # ρ is threshold-independent

    baseline = table[table.variant == "baseline"]
    knob_rows = []
    for knob in ("kappa", "gamma", "bandwidth", "k_nearest", "nearest_only",
                 "unreachable", "everyday_mode"):
        block = pd.concat([table[table.axis == knob], baseline])
        if block[block.axis == knob].empty:
            continue
        hh_rng = _range(block["share_HH"])
        rho_rng = _range(block["spearman_rho"])
        knob_rows.append({
            "knob": knob,
            "hh_share_range": hh_rng,
            "rho_range": rho_rng,
            "hh_exceeds_threshold": bool(hh_rng > hh_thr),
            "rho_exceeds_threshold": bool(rho_rng > rho_thr),
        })
    knob_rows.append({
        "knob": "threshold_axis", "hh_share_range": hh_thr, "rho_range": rho_thr,
        "hh_exceeds_threshold": False, "rho_exceeds_threshold": False,
    })
    acc = pd.DataFrame(knob_rows)
    return acc.sort_values("hh_share_range", ascending=False).reset_index(drop=True)


def _range(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.max() - s.min()) if len(s) else 0.0


# --------------------------------------------------------------------------- #
# Figure                                                                       #
# --------------------------------------------------------------------------- #
def _flip_cell_map(surfaces: pd.DataFrame, flip_mask: np.ndarray, cfg: dict,
                   city: str, out_png: Path, sensitive_share: float) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover - viz extra not installed
        print("  matplotlib not installed; skipping flip-cell map")
        return
    from depacc.viz.pipeline import _grid_scatter, _watermark

    flip = np.asarray(flip_mask, bool)
    STABLE, FLIP = "#e8e8e8", "#d1495b"
    colors = np.where(flip, FLIP, STABLE)
    name = cfg["city"].get("name", city)

    fig, ax = plt.subplots(figsize=(7.2, 6.5))
    _grid_scatter(fig, ax, surfaces.x.to_numpy(), surfaces.y.to_numpy(),
                  color=colors)
    import matplotlib.patches as mpatches
    handles = [
        mpatches.Patch(color=STABLE, label="stable class across all variants"),
        mpatches.Patch(color=FLIP,
                       label=f"flips class under ≥1 Layer-3 variant "
                             f"({sensitive_share:.0%} pop)"),
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1),
              frameon=False, fontsize=8, title="Layer-3 accessibility sensitivity",
              title_fontsize=8)
    ax.set_title(f"{name}: cells whose co-location class flips under the\n"
                 f"Layer-3 accessibility sweep (κ/γ/bandwidth/k/mode/unreachable)",
                 fontsize=11)
    _watermark(fig, cfg)
    fig.tight_layout()
    fig.savefig(out_png, dpi=180, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Top-level entry point                                                       #
# --------------------------------------------------------------------------- #
def run_access_sensitivity(cfg: dict, grid: dict, root: Path,
                           city: str | None = None) -> None:
    """Run the Layer-3 accessibility sweep from cached inputs.

    ``cfg`` is only used for its output paths and non-city defaults; the
    per-city merged config (routing engine, services, baselines) is loaded per
    city so overrides are honoured. Sweeps every non-synthetic city in
    cityplane.csv, or just ``city`` when given.
    """
    derived = root / cfg["output"]["root"]
    access_grid = ((grid or {}).get("accessibility")) or {}
    threshold = float((grid or {}).get("threshold", 0.5))

    if city is not None:
        cities = [city]
    else:
        plane_path = derived / "cityplane.csv"
        if not plane_path.exists():
            print("access-sensitivity: no cityplane.csv — run the pipeline for "
                  ">=1 city first, or pass --city")
            return
        plane = pd.read_csv(plane_path)
        if "synthetic" in plane:
            plane = plane[~plane["synthetic"].astype(bool)]
        cities = [str(c) for c in plane.city]
        if not cities:
            print("access-sensitivity: no non-synthetic cities to sweep")
            return

    print(f"access-sensitivity (Layer 3, from cached OD): {len(cities)} city/ies")
    for c in cities:
        city_cfg = load_config(c)
        print(f"[{c}] Layer-3 accessibility variants:")
        table = city_access_sensitivity(city_cfg, c, root, grid, threshold)
        if table is None:
            continue
        var = table[~table.axis.isin(["threshold"])]
        hh_rng = _range(var["share_HH"])
        rho_rng = _range(var["spearman_rho"])
        print(f"  {c}: across Layer-3 variants — HH-share range {hh_rng:.4f}, "
              f"ρ range {rho_rng:.4f} "
              f"(vs threshold-axis HH range {_range(table[table.axis=='threshold']['share_HH']):.4f})")
        # Acceptance table (written for every city; the Hamburg one is the
        # acceptance artefact called for in the task).
        acc = acceptance_table(table)
        acc.insert(0, "city", c)
        acc_path = derived / "sensitivity" / f"{c}_access_acceptance.csv"
        acc.to_csv(acc_path, index=False)
        top = acc[acc.knob != "threshold_axis"].iloc[0] if len(acc) else None
        if top is not None:
            print(f"  {c}: knob moving HH share most = '{top.knob}' "
                  f"(range {top.hh_share_range:.4f}); acceptance -> {acc_path.name}")
    print(f"access-sensitivity outputs -> {derived / 'sensitivity'}")
