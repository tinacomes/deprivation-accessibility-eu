"""Sensitivity computations: variant expansion, per-city stable targets from
saved travel times, cross-variant rank agreement, and flip-cells."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from depacc.divergence.typology import class_shares, classify
from depacc.equity.indices import weighted_gini
from depacc.standardize import RegimeSurface, to_percentile


@dataclass(frozen=True)
class Variant:
    name: str
    layer: str                # "baseline" | "curvature" | "form_swap"
    everyday: dict            # deprivation spec (form + params)
    emergency: dict


def _baseline_specs(cfg: dict) -> tuple[dict, dict]:
    dep = cfg["deprivation"]
    return dict(dep["everyday"]), dict(dep["emergency"])


def expand_variants(cfg: dict, grid: dict) -> list[Variant]:
    """Baseline + Layer-1 curvature variants (+ Layer-2 form-swaps if concrete
    alternate specs are supplied). Each varies one regime, the other baseline."""
    ev0, em0 = _baseline_specs(cfg)
    variants = [Variant("baseline", "baseline", ev0, em0)]

    ev_grid = grid.get("everyday", {}) or {}
    ev_keys = [k for k in ("k", "t0", "Lmax", "beta", "scale", "lam", "shift")
               if k in ev_grid]
    for combo in itertools.product(*[ev_grid[k] for k in ev_keys]) if ev_keys else []:
        params = dict(ev0["params"])
        params.update({k: v for k, v in zip(ev_keys, combo)})
        if params == ev0["params"]:
            continue
        name = "everyday_" + "_".join(f"{k}{v}" for k, v in zip(ev_keys, combo))
        variants.append(Variant(name, "curvature", {**ev0, "params": params}, em0))

    em_grid = grid.get("emergency", {}) or {}
    em_keys = [k for k in ("lam", "shift", "scale", "beta") if k in em_grid]
    for combo in itertools.product(*[em_grid[k] for k in em_keys]) if em_keys else []:
        params = dict(em0["params"])
        params.update({k: v for k, v in zip(em_keys, combo)})
        if params == em0["params"]:
            continue
        name = "emergency_" + "_".join(f"{k}{v}" for k, v in zip(em_keys, combo))
        variants.append(Variant(name, "curvature", ev0, {**em0, "params": params}))

    fs = grid.get("form_swap", {}) or {}
    for entry in fs.get("everyday", []) or []:
        spec, form = _resolve_form_swap(cfg, ev0, entry)
        variants.append(Variant(f"formswap_everyday_{form}", "form_swap", spec, em0))
    for entry in fs.get("emergency", []) or []:
        spec, form = _resolve_form_swap(cfg, em0, entry)
        variants.append(Variant(f"formswap_emergency_{form}", "form_swap", ev0, spec))
    return variants


def _resolve_form_swap(cfg: dict, base_spec: dict, entry: dict) -> tuple[dict, str]:
    """Resolve a Layer-2 form_swap entry to a concrete deprivation spec.

    An entry is either ``{alternative: <name>}`` — resolved from
    ``deprivation.alternatives`` in the merged config (the single source of
    truth for the anchor-calibrated params) — or an inline ``{form, params,
    ...}`` override merged over the regime baseline. Returns (spec, form_label).
    """
    if "alternative" in entry:
        alts = (cfg.get("deprivation", {}) or {}).get("alternatives", {}) or {}
        name = entry["alternative"]
        if name not in alts:
            raise KeyError(
                f"form_swap references unknown alternative '{name}'; "
                f"available: {sorted(alts)}")
        spec = dict(alts[name])
    else:
        spec = {**base_spec, **entry}
    return spec, str(spec.get("form"))


def city_stable_targets(t_everyday: np.ndarray, t_emergency: np.ndarray,
                        population: np.ndarray, everyday_spec: dict,
                        emergency_spec: dict, city_id: str = "c",
                        threshold: float = 0.5) -> dict:
    """Standardised / rank targets for one city under one variant, evaluated on
    the (fixed) travel times. Returns Ginis, divergence_gap, typology shares,
    and the per-cell typology labels. No raw magnitudes leave this function."""
    from depacc.deprivation.functions import DeprivationFunction

    g_ev = DeprivationFunction.from_spec(everyday_spec, context="everyday")
    g_em = DeprivationFunction.from_spec(emergency_spec, context="emergency")
    ev = RegimeSurface(g_ev(t_everyday), population, "everyday", city_id, "raw")
    em = RegimeSurface(g_em(t_emergency), population, "emergency", city_id, "raw")
    gini_ev = weighted_gini(ev.values, population)
    gini_em = weighted_gini(em.values, population)
    labels = classify(to_percentile(ev).values, to_percentile(em).values, threshold)
    shares = class_shares(labels, population)["population_share"].to_dict()
    return {
        "gini_everyday": gini_ev,
        "gini_emergency": gini_em,
        "divergence_gap": gini_em - gini_ev,
        **{f"share_{c}": shares.get(c, np.nan) for c in ("LL", "LH", "HL", "HH")},
        "labels": labels,
    }


def city_variant_table(t_everyday: np.ndarray, t_emergency: np.ndarray,
                       population: np.ndarray, variants: list["Variant"],
                       city_id: str, thresholds=(0.4, 0.5, 0.6, 0.75)) -> pd.DataFrame:
    """Per-city, per-variant robustness table — informative for a SINGLE city.

    Two axes are reported side by side:

      * DEPRIVATION-FUNCTION curvature (each ``variant``): within-regime Ginis
        move, but the co-location typology does NOT — it is computed on
        population-weighted ranks, and every g(t) here is strictly increasing,
        so ranks (and therefore the LL/HL/LH/HH classes) are invariant by
        construction. The table makes that explicit: the Gini columns spread
        while the class-share columns stay put across curvature variants.
      * THRESHOLD (the split choice): the compounding (HH) share is swept over
        several percentile cut-offs, since "how high is high" is an assumption.

    The ``axis`` column separates the deprivation-function *curvature* variants
    (baseline + Layer-1) from the Layer-2 *form_swap* variants, so a consumer
    (e.g. the plane's curvature error bars) can take the curvature envelope
    without the form-swap Ginis leaking into it.
    """
    rows = []
    for v in variants:
        tgt = city_stable_targets(t_everyday, t_emergency, population,
                                  v.everyday, v.emergency, city_id, threshold=0.5)
        axis = "form_swap" if v.layer == "form_swap" else "curvature"
        rows.append({
            "city": city_id, "axis": axis, "variant": v.name,
            "layer": v.layer, "threshold": 0.5,
            "gini_everyday": tgt["gini_everyday"],
            "gini_emergency": tgt["gini_emergency"],
            "divergence_gap": tgt["divergence_gap"],
            **{f"share_{c}": tgt[f"share_{c}"] for c in ("LL", "LH", "HL", "HH")},
        })
    # Threshold sweep on the BASELINE specs.
    base = variants[0]
    g_ev = _dep_fn(base.everyday, "everyday")
    g_em = _dep_fn(base.emergency, "emergency")
    ev_p = to_percentile(RegimeSurface(g_ev(t_everyday), population, "everyday", city_id, "raw")).values
    em_p = to_percentile(RegimeSurface(g_em(t_emergency), population, "emergency", city_id, "raw")).values
    for thr in thresholds:
        labels = classify(ev_p, em_p, thr)
        shares = class_shares(labels, population)["population_share"].to_dict()
        rows.append({
            "city": city_id, "axis": "threshold", "variant": f"threshold_{thr}",
            "layer": "threshold", "threshold": thr,
            "gini_everyday": np.nan, "gini_emergency": np.nan, "divergence_gap": np.nan,
            **{f"share_{c}": shares.get(c, np.nan) for c in ("LL", "LH", "HL", "HH")},
        })
    return pd.DataFrame(rows)


def _dep_fn(spec: dict, context: str):
    from depacc.deprivation.functions import DeprivationFunction

    return DeprivationFunction.from_spec(spec, context=context)


def city_calibration_targets(surfaces: pd.DataFrame, cfg: dict,
                             threshold_mode: str, *, threshold: float = 0.5,
                             city_id: str = "c") -> dict:
    """Stable targets for one city's everyday regime under a `t0` calibration
    (`uniform` vs `per_service`), re-compositing the PER-SERVICE effective
    times saved by the deprivation stage (``t_eff_<service>``). Emergency is
    held at its baseline spec on the saved ``t_regime_emergency`` — no
    re-routing. Only standardised / rank targets leave here; raw magnitudes
    never do.

    Unlike the curvature layers (which act on the composite ``t_regime_*``),
    the calibration variant must be applied per service and then composited,
    because a per-service ``t0`` cannot be recovered from the composite time.
    """
    import copy

    from depacc.config import deprivation_spec, everyday_service_spec
    from depacc.deprivation.functions import DeprivationFunction

    cfg_mode = copy.deepcopy(cfg)
    cfg_mode.setdefault("deprivation", {}).setdefault("everyday", {})[
        "threshold_mode"] = threshold_mode

    pop = surfaces["population"].to_numpy(float)
    services = [s for s in (cfg.get("everyday_services") or {})
                if f"t_eff_{s}" in surfaces.columns]
    if not services:
        raise ValueError("no per-service effective-time columns (t_eff_*) in "
                         "surfaces — re-run the deprivation stage")
    weights = (cfg.get("regimes", {}).get("everyday", {})
               .get("composite_weights") or {})
    w = np.array([float(weights.get(s, 1.0)) for s in services])
    cols = []
    for s in services:
        g = DeprivationFunction.from_spec(
            everyday_service_spec(cfg_mode, s), context=f"everyday [{s}]")
        cols.append(g(surfaces[f"t_eff_{s}"].to_numpy(float)))
    vals = np.column_stack(cols)
    mask = ~np.isnan(vals)
    wm = np.where(mask, w[None, :], 0.0)
    denom = wm.sum(axis=1)
    with np.errstate(invalid="ignore"):
        dep_ev = np.where(denom > 0, np.nansum(vals * wm, axis=1) / denom, np.nan)
    # Shared no-path mask (Phase 1): genuinely unroutable cells stay masked.
    if "unreachable_everyday" in surfaces.columns:
        dep_ev = np.where(surfaces["unreachable_everyday"].to_numpy(bool),
                          np.nan, dep_ev)

    g_em = DeprivationFunction.from_spec(
        deprivation_spec(cfg, "emergency"), context="emergency")
    dep_em = g_em(surfaces["t_regime_emergency"].to_numpy(float))

    ev = RegimeSurface(dep_ev, pop, "everyday", city_id, "raw")
    em = RegimeSurface(dep_em, pop, "emergency", city_id, "raw")
    gini_ev = weighted_gini(ev.values, pop)
    gini_em = weighted_gini(em.values, pop)
    labels = classify(to_percentile(ev).values, to_percentile(em).values, threshold)
    shares = class_shares(labels, pop)["population_share"].to_dict()
    return {
        "gini_everyday": gini_ev,
        "gini_emergency": gini_em,
        "divergence_gap": gini_em - gini_ev,
        **{f"share_{c}": shares.get(c, np.nan) for c in ("LL", "LH", "HL", "HH")},
        "labels": labels,
    }


def adjusted_rand(a: np.ndarray, b: np.ndarray) -> float:
    """Adjusted Rand Index between two label arrays (``None``/NaN pairs are
    dropped). Self-contained (no sklearn) so the harness core stays light;
    used for the per-city typology cluster-membership agreement across a
    calibration variant."""
    a = np.asarray(a, dtype=object)
    b = np.asarray(b, dtype=object)
    keep = np.array([x is not None and y is not None
                     for x, y in zip(a, b)])
    a, b = a[keep], b[keep]
    n = len(a)
    if n < 2:
        return float("nan")
    ua = {lab: i for i, lab in enumerate(sorted(set(a)))}
    ub = {lab: i for i, lab in enumerate(sorted(set(b)))}
    cont = np.zeros((len(ua), len(ub)), dtype=float)
    for x, y in zip(a, b):
        cont[ua[x], ub[y]] += 1
    from math import comb

    def _c2(x):
        return comb(int(x), 2) if x >= 2 else 0.0

    sum_ij = float(np.sum([_c2(v) for v in cont.ravel()]))
    sum_a = float(np.sum([_c2(v) for v in cont.sum(axis=1)]))
    sum_b = float(np.sum([_c2(v) for v in cont.sum(axis=0)]))
    total = _c2(n)
    expected = sum_a * sum_b / total if total else 0.0
    maxi = 0.5 * (sum_a + sum_b)
    denom = maxi - expected
    if denom == 0:
        return 1.0
    return float((sum_ij - expected) / denom)


def flip_cells(baseline_labels: np.ndarray, variant_label_sets: list[np.ndarray],
               population: np.ndarray) -> dict:
    """Cells whose typology class changes under ANY variant vs baseline.
    Returns pop-shares (stable/sensitive) and a per-cell boolean flip mask."""
    pop = np.asarray(population, float)
    flip = np.zeros(len(baseline_labels), dtype=bool)
    for labs in variant_label_sets:
        flip |= (labs != baseline_labels) & (baseline_labels != None) & (labs != None)  # noqa: E711
    total = float(pop[pop > 0].sum())
    sens = float(pop[flip & (pop > 0)].sum())
    return {
        "flip_mask": flip,
        "sensitive_pop_share": sens / total if total > 0 else np.nan,
        "stable_pop_share": 1 - sens / total if total > 0 else np.nan,
    }


def _rank_agreement(baseline: pd.Series, variant: pd.Series) -> tuple[float, float]:
    from scipy.stats import kendalltau, spearmanr

    df = pd.concat([baseline, variant], axis=1).dropna()
    if len(df) < 3:
        return float("nan"), float("nan")
    rho = spearmanr(df.iloc[:, 0], df.iloc[:, 1]).correlation
    tau = kendalltau(df.iloc[:, 0], df.iloc[:, 1]).correlation
    return float(rho), float(tau)


def run_sensitivity(cfg: dict, grid: dict, root: Path) -> None:
    """Run Layers 1/2 across all cities in cityplane and write the rank-agreement
    table, typology-share drift, and flip-cell shares."""
    derived = root / cfg["output"]["root"]
    plane_path = derived / "cityplane.csv"
    if not plane_path.exists():
        print("sensitivity: no cityplane.csv — run the pipeline for >=1 city first")
        return
    cities = pd.read_csv(plane_path)
    cities = cities[~cities.get("synthetic", False).astype(bool)] \
        if "synthetic" in cities else cities
    if cities.empty:
        print("sensitivity: no non-synthetic cities to sweep")
        return

    variants = expand_variants(cfg, grid)
    threshold = float(grid.get("threshold", 0.5))
    print(f"sensitivity: {len(variants)} variants x {len(cities)} cities "
          f"(layers: {sorted(set(v.layer for v in variants))})")

    # target[variant_name] = DataFrame indexed by city with stable scalars
    per_variant: dict[str, pd.DataFrame] = {}
    # flip-cell tracking per city
    flip_records = []
    for city in cities.city.astype(str):
        surf_path = derived / city / "surfaces.parquet"
        if not surf_path.exists():
            continue
        s = pd.read_parquet(surf_path)
        if "t_regime_everyday" not in s or "t_regime_emergency" not in s:
            continue
        t_ev = s["t_regime_everyday"].to_numpy(float)
        t_em = s["t_regime_emergency"].to_numpy(float)
        pop = s["population"].to_numpy(float)
        base_labels = None
        var_label_sets = []
        for v in variants:
            tgt = city_stable_targets(t_ev, t_em, pop, v.everyday, v.emergency,
                                      city, threshold)
            labels = tgt.pop("labels")
            if v.name == "baseline":
                base_labels = labels
            else:
                var_label_sets.append(labels)
            per_variant.setdefault(v.name, {})[city] = tgt
        if base_labels is not None and var_label_sets:
            fc = flip_cells(base_labels, var_label_sets, pop)
            flip_records.append({"city": city,
                                 "sensitive_pop_share": fc["sensitive_pop_share"],
                                 "stable_pop_share": fc["stable_pop_share"]})
        # Per-city table (curvature Gini movement + threshold sweep) — the
        # single-city-meaningful view of deprivation-assumption sensitivity.
        out_city = derived / "sensitivity"
        out_city.mkdir(parents=True, exist_ok=True)
        cvt = city_variant_table(t_ev, t_em, pop, variants, city)
        cvt.to_csv(out_city / f"{city}_deprivation_sensitivity.csv", index=False)
        cur = cvt[cvt.axis == "curvature"]
        g_ev_rng = cur.gini_everyday.max() - cur.gini_everyday.min()
        g_em_rng = cur.gini_emergency.max() - cur.gini_emergency.min()
        hh_rng = cur.share_HH.max() - cur.share_HH.min()
        print(f"  {city}: across curvature variants — gini_everyday range "
              f"{g_ev_rng:.3f}, gini_emergency range {g_em_rng:.3f}; "
              f"HH-share range {hh_rng:.4f} (typology is rank-based → ~0)")

    frames = {name: pd.DataFrame(d).T for name, d in per_variant.items()}
    if "baseline" not in frames:
        print("sensitivity: baseline targets unavailable")
        return

    # Rank-agreement of city ordering vs baseline, per stable target.
    out = derived / "sensitivity"
    out.mkdir(parents=True, exist_ok=True)
    base = frames["baseline"]
    rows = []
    for name, f in frames.items():
        if name == "baseline":
            continue
        for target in ("divergence_gap", "gini_emergency", "gini_everyday"):
            rho, tau = _rank_agreement(base[target], f[target])
            rows.append({"variant": name, "target": target,
                         "spearman_rho": rho, "kendall_tau": tau})
    rank_table = pd.DataFrame(rows)
    rank_table.to_csv(out / "rank_agreement.csv", index=False)
    if not rank_table.empty:
        print("rank agreement vs baseline (min across variants):")
        for target, g in rank_table.groupby("target"):
            print(f"  {target}: min rho={g.spearman_rho.min():.3f} "
                  f"min tau={g.kendall_tau.min():.3f}")

    if flip_records:
        flip_df = pd.DataFrame(flip_records)
        flip_df.to_csv(out / "flip_cells.csv", index=False)
        print(f"flip-cells: mean sensitive pop share "
              f"{flip_df.sensitive_pop_share.mean():.1%} across {len(flip_df)} cities")

    # Typology-share envelope per city (min/max across variants).
    share_rows = []
    for city in base.index:
        for cls in ("LL", "LH", "HL", "HH"):
            vals = [frames[n].loc[city, f"share_{cls}"] for n in frames
                    if city in frames[n].index]
            share_rows.append({"city": city, "class": cls,
                               "baseline": base.loc[city, f"share_{cls}"],
                               "min": np.nanmin(vals), "max": np.nanmax(vals)})
    pd.DataFrame(share_rows).to_csv(out / "typology_share_envelope.csv", index=False)

    # Layer 3-adjacent: the DEPRIVATION-CALIBRATION variant — uniform t0=15 vs
    # per-service t0 — reported as a robustness result against the Layer-3
    # accessibility axis (§7.3): outputs should move MORE with supply/mode than
    # with this calibration choice.
    if grid.get("calibration"):
        _run_calibration(cfg, grid, cities, derived, out, threshold)

    print(f"sensitivity outputs -> {out}")


def _run_calibration(cfg: dict, grid: dict, cities: pd.DataFrame,
                     derived: Path, out: Path, threshold: float) -> None:
    """Uniform-t0 vs per-service-t0 contrast, tracking stable targets only
    (Spearman/Kendall on city rankings, typology-class ARI, typology shares,
    Ginis, divergence_gap). Never tracks raw magnitudes."""
    modes = list(grid["calibration"].get("everyday_t0")
                 or ["uniform", "per_service"])
    if len(modes) < 2:
        print("calibration: need >=2 modes (uniform, per_service); skipped")
        return
    rows: dict[str, dict] = {m: {} for m in modes}
    ari_rows = []
    for city in cities.city.astype(str):
        sp = derived / city / "surfaces.parquet"
        if not sp.exists():
            continue
        s = pd.read_parquet(sp)
        if not any(c.startswith("t_eff_") for c in s.columns):
            continue
        labels_by_mode = {}
        for m in modes:
            tgt = city_calibration_targets(s, cfg, m, threshold=threshold,
                                           city_id=city)
            labels_by_mode[m] = tgt.pop("labels")
            rows[m][city] = tgt
        ref = modes[0]
        for m in modes[1:]:
            ari_rows.append({"city": city, "mode": m,
                             "typology_ari_vs_" + ref:
                                 adjusted_rand(labels_by_mode[ref],
                                               labels_by_mode[m])})
    frames = {m: pd.DataFrame(d).T for m, d in rows.items() if d}
    if len(frames) < 2:
        print("calibration: <2 cities/modes with surfaces; skipped")
        return
    ref = modes[0]
    agree_rows = []
    for m in modes[1:]:
        if m not in frames:
            continue
        for target in ("divergence_gap", "gini_emergency", "gini_everyday"):
            rho, tau = _rank_agreement(frames[ref][target], frames[m][target])
            agree_rows.append({"variant": f"{m}_vs_{ref}", "target": target,
                               "spearman_rho": rho, "kendall_tau": tau})
    pd.DataFrame(agree_rows).to_csv(out / "calibration_rank_agreement.csv", index=False)
    if ari_rows:
        pd.DataFrame(ari_rows).to_csv(out / "calibration_typology_ari.csv", index=False)

    # Per-city typology-share drift + level deltas (uniform vs per_service).
    drift_rows = []
    for city in frames[ref].index:
        for m in modes[1:]:
            if m not in frames or city not in frames[m].index:
                continue
            for col in ("gini_everyday", "gini_emergency", "divergence_gap",
                        "share_LL", "share_LH", "share_HL", "share_HH"):
                drift_rows.append({
                    "city": city, "mode": m, "target": col,
                    ref: frames[ref].loc[city, col],
                    m: frames[m].loc[city, col],
                    "delta": frames[m].loc[city, col] - frames[ref].loc[city, col],
                })
    pd.DataFrame(drift_rows).to_csv(out / "calibration_target_drift.csv", index=False)
    if agree_rows:
        rt = pd.DataFrame(agree_rows)
        print("calibration (uniform vs per-service) rank agreement:")
        for target, g in rt.groupby("target"):
            print(f"  {target}: rho={g.spearman_rho.min():.3f} "
                  f"tau={g.kendall_tau.min():.3f}")
    if ari_rows:
        adf = pd.DataFrame(ari_rows)
        acol = [c for c in adf.columns if c.startswith("typology_ari")][0]
        print(f"calibration typology ARI (uniform vs per-service): "
              f"mean {adf[acol].mean():.3f} across {len(adf)} cities")
