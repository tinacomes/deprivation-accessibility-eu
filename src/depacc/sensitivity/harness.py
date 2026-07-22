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
    for alt in fs.get("everyday", []) or []:
        variants.append(Variant(f"formswap_everyday_{alt['form']}", "form_swap",
                                 {**ev0, **alt}, em0))
    for alt in fs.get("emergency", []) or []:
        variants.append(Variant(f"formswap_emergency_{alt['form']}", "form_swap",
                                 ev0, {**em0, **alt}))
    return variants


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
    """
    rows = []
    for v in variants:
        tgt = city_stable_targets(t_everyday, t_emergency, population,
                                  v.everyday, v.emergency, city_id, threshold=0.5)
        rows.append({
            "city": city_id, "axis": "curvature", "variant": v.name,
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
    print(f"sensitivity outputs -> {out}")
