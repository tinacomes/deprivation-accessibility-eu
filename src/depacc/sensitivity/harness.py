"""Sensitivity computations: variant expansion, per-city stable targets from
the saved PER-SERVICE travel times (variant g applied per service, composited
with the pipeline's weighted row mean — never g of the composite time),
cross-variant rank agreement, and flip-cells."""

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


def stable_targets_from_deprivation(dep_everyday: np.ndarray,
                                    dep_emergency: np.ndarray,
                                    population: np.ndarray,
                                    city_id: str = "c",
                                    threshold: float = 0.5) -> dict:
    """Standardised / rank targets for one city from precomputed DEPRIVATION
    surfaces. Returns Ginis, divergence_gap, typology shares, and the per-cell
    typology labels. No raw magnitudes leave this function."""
    ev = RegimeSurface(dep_everyday, population, "everyday", city_id, "raw")
    em = RegimeSurface(dep_emergency, population, "emergency", city_id, "raw")
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


def city_stable_targets(t_everyday: np.ndarray, t_emergency: np.ndarray,
                        population: np.ndarray, everyday_spec: dict,
                        emergency_spec: dict, city_id: str = "c",
                        threshold: float = 0.5) -> dict:
    """Single-surface evaluator: ``g(t)`` per regime on ONE composite time
    array each. Correct only when a regime has (or is modelled as) a single
    service — synthetic fixtures and property tests. The real pipeline
    composites per-service deprivations (``Σ w_s g(t_s)``), and because g is
    nonlinear the two differ by a Jensen gap; multi-service cities must go
    through :func:`variant_regime_deprivations` instead (this function applied
    to Hamburg's composite time gave gini_everyday 0.583 against the
    pipeline's 0.543)."""
    from depacc.deprivation.functions import DeprivationFunction

    g_ev = DeprivationFunction.from_spec(everyday_spec, context="everyday")
    g_em = DeprivationFunction.from_spec(emergency_spec, context="emergency")
    return stable_targets_from_deprivation(g_ev(t_everyday), g_em(t_emergency),
                                           population, city_id, threshold)


def variant_regime_deprivations(surfaces: pd.DataFrame, cfg: dict,
                                everyday_spec: dict, emergency_spec: dict
                                ) -> tuple[np.ndarray, np.ndarray]:
    """Both regimes' composite deprivation under one variant's specs, built
    EXACTLY as ``depacc.deprivation.pipeline`` builds them: the variant's g is
    applied PER SERVICE to the saved per-service times (``t_eff_<s>`` for
    everyday, ``t_nearest_<s>`` for emergency) and composited with the
    regime's weighted row mean; the shared no-path masks
    (``unreachable_<regime>``) are then applied. g is nonlinear, so
    ``g(mean t)`` — the previous implementation — is a different estimator
    whose "baseline" did not reproduce ``cityplane_row.csv`` (the Layer-3
    sweep had the same defect, fixed in plan §5.4; this is the Layer-1/2
    counterpart).

    The everyday variant spec replaces ``deprivation.everyday`` wholesale and
    is resolved through :func:`depacc.config.everyday_service_spec`, so under
    ``threshold_mode: per_service`` the per-service ``t0``/``k`` overrides
    still win — the same precedence the pipeline gives them.
    """
    import copy

    from depacc.config import everyday_service_spec
    from depacc.deprivation.functions import DeprivationFunction

    cfg_v = copy.deepcopy(cfg)
    cfg_v.setdefault("deprivation", {})["everyday"] = everyday_spec

    ev_services = [s for s in (cfg.get("everyday_services") or {})
                   if f"t_eff_{s}" in surfaces.columns]
    em_services = [s for s in (cfg.get("emergency_services") or {})
                   if f"t_nearest_{s}" in surfaces.columns]
    if not ev_services or not em_services:
        raise ValueError(
            "surfaces lack the per-service time columns (t_eff_*/t_nearest_*) "
            "the per-service composite needs — re-run the deprivation stage "
            "for this city")

    def _composite(services: list[str], col_prefix: str, regime: str,
                   fns: dict) -> np.ndarray:
        weights = (cfg.get("regimes", {}).get(regime, {})
                   .get("composite_weights") or {})
        w = np.array([float(weights.get(s, 1.0)) for s in services])
        vals = np.column_stack([
            fns[s](surfaces[f"{col_prefix}{s}"].to_numpy(float))
            for s in services])
        dep = _weighted_row_mean(vals, w)
        mask_col = f"unreachable_{regime}"
        if mask_col in surfaces.columns:
            dep = np.where(surfaces[mask_col].to_numpy(bool), np.nan, dep)
        return dep

    ev_fns = {s: DeprivationFunction.from_spec(
        everyday_service_spec(cfg_v, s), context=f"everyday [{s}]")
        for s in ev_services}
    g_em = DeprivationFunction.from_spec(emergency_spec, context="emergency")
    em_fns = {s: g_em for s in em_services}
    return (_composite(ev_services, "t_eff_", "everyday", ev_fns),
            _composite(em_services, "t_nearest_", "emergency", em_fns))


def _weighted_row_mean(vals: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Row mean over non-NaN services, weights renormalised per row (matches
    depacc.deprivation.pipeline._weighted_row_mean)."""
    mask = ~np.isnan(vals)
    wm = np.where(mask, w[None, :], 0.0)
    denom = wm.sum(axis=1)
    with np.errstate(invalid="ignore"):
        out = np.nansum(vals * wm, axis=1) / denom
    return np.where(denom > 0, out, np.nan)


def city_variant_table(surfaces: pd.DataFrame, cfg: dict,
                       variants: list["Variant"],
                       city_id: str, thresholds=(0.4, 0.5, 0.6, 0.75)) -> pd.DataFrame:
    """Per-city, per-variant robustness table — informative for a SINGLE city.

    Two axes are reported side by side:

      * DEPRIVATION-FUNCTION curvature (each ``variant``): within-regime Ginis
        move, while the co-location typology is NEAR-invariant. Every g(t)
        here is strictly increasing, so PER-SERVICE ranks never move; the
        multi-service composite ``Σ w_s g(t_s)`` can still reorder cells
        because a curvature change reweights how the services mix. (Under the
        old ``g(composite time)`` estimator the invariance was exact — an
        artifact of the estimator mismatch, not a property of the model.) The
        table measures the residual drift instead of asserting zero: the Gini
        columns spread while the class-share columns barely move.
      * THRESHOLD (the split choice): the compounding (HH) share is swept over
        several percentile cut-offs, since "how high is high" is an assumption.

    The ``axis`` column separates the deprivation-function *curvature* variants
    (baseline + Layer-1) from the Layer-2 *form_swap* variants, so a consumer
    (e.g. the plane's curvature error bars) can take the curvature envelope
    without the form-swap Ginis leaking into it.
    """
    population = surfaces["population"].to_numpy(float)
    rows = []
    base_dep = None
    for v in variants:
        dep_ev, dep_em = variant_regime_deprivations(surfaces, cfg,
                                                     v.everyday, v.emergency)
        if v.name == "baseline":
            base_dep = (dep_ev, dep_em)
        tgt = stable_targets_from_deprivation(dep_ev, dep_em, population,
                                              city_id, threshold=0.5)
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
    if base_dep is None:
        base = variants[0]
        base_dep = variant_regime_deprivations(surfaces, cfg,
                                               base.everyday, base.emergency)
    ev_p = to_percentile(RegimeSurface(base_dep[0], population, "everyday", city_id, "raw")).values
    em_p = to_percentile(RegimeSurface(base_dep[1], population, "emergency", city_id, "raw")).values
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


RANK_TARGETS = ("divergence_gap", "gini_emergency", "gini_everyday")


def _merge_persisted(path: Path, fresh: pd.DataFrame,
                     keys: list[str]) -> pd.DataFrame:
    """Union a freshly computed per-city table with the one already on disk,
    the fresh rows winning on the shared keys. Accumulating tables must not
    shrink to whatever subset of cities a single batch happened to stage."""
    if not path.exists():
        return fresh
    try:
        old = pd.read_csv(path)
    except Exception:
        return fresh
    if not set(keys) <= set(old.columns):
        return fresh
    keep = old.merge(fresh[keys].drop_duplicates(), on=keys, how="left",
                     indicator=True)
    keep = keep[keep["_merge"] == "left_only"].drop(columns="_merge")
    return pd.concat([keep, fresh], ignore_index=True) \
             .sort_values(keys).reset_index(drop=True)


def rank_agreement_from_tables(sens_dir: Path) -> pd.DataFrame:
    """Cross-city rank agreement vs baseline from the persisted per-city
    variant tables (``<city>_deprivation_sensitivity.csv``). Reading the
    tables instead of this run's staged surfaces means the statistic covers
    every persisted city, the same source the spec curve reads. Rows carry
    ``n_cities`` — the paired city count each rho/tau is computed on."""
    frames = []
    for p in sorted(sens_dir.glob("*_deprivation_sensitivity.csv")):
        f = pd.read_csv(p)
        frames.append(f[f.axis.isin(["curvature", "form_swap"])]
                      .drop_duplicates(["city", "variant"]))
    if not frames:
        return pd.DataFrame()
    stacked = pd.concat(frames, ignore_index=True)
    base = stacked[stacked.variant == "baseline"].set_index("city")
    if base.empty:
        return pd.DataFrame()
    rows = []
    for name, vf in stacked[stacked.variant != "baseline"].groupby("variant",
                                                                   sort=True):
        vf = vf.set_index("city")
        for target in RANK_TARGETS:
            paired = pd.concat([base[target], vf[target]], axis=1,
                               join="inner").dropna()
            rho, tau = _rank_agreement(paired.iloc[:, 0], paired.iloc[:, 1])
            rows.append({"variant": name, "target": target,
                         "spearman_rho": rho, "kendall_tau": tau,
                         "n_cities": len(paired)})
    return pd.DataFrame(rows)


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
        has_per_service = (any(c.startswith("t_eff_") for c in s.columns)
                           and any(c.startswith("t_nearest_") for c in s.columns))
        if not has_per_service:
            print(f"  NOTE: {city} skipped — surfaces.parquet lacks the "
                  f"per-service time columns (t_eff_*/t_nearest_*) the "
                  f"per-service composite needs; re-run its deprivation stage")
            continue
        pop = s["population"].to_numpy(float)
        base_labels = None
        var_label_sets = []
        for v in variants:
            dep_ev, dep_em = variant_regime_deprivations(s, cfg,
                                                         v.everyday, v.emergency)
            tgt = stable_targets_from_deprivation(dep_ev, dep_em, pop,
                                                  city, threshold)
            labels = tgt.pop("labels")
            if v.name == "baseline":
                base_labels = labels
                # The baseline recompute must be the model: pin it against the
                # deprivation stage's own saved composites (they disagree only
                # if the config's deprivation params changed since the city's
                # surfaces were written — then the surfaces are stale).
                for col, dep in (("deprivation_everyday", dep_ev),
                                 ("deprivation_emergency", dep_em)):
                    if col in s.columns:
                        saved = s[col].to_numpy(float)
                        both = np.isfinite(saved) & np.isfinite(dep)
                        gap = (float(np.max(np.abs(saved[both] - dep[both])))
                               if both.any() else 0.0)
                        if gap > 1e-9 or (np.isfinite(saved) != np.isfinite(dep)).any():
                            print(f"  WARNING: {city} baseline recompute "
                                  f"deviates from saved {col} (max |Δ| "
                                  f"{gap:.3g}) — stale surfaces vs config?")
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
        cvt = city_variant_table(s, cfg, variants, city)
        cvt.to_csv(out_city / f"{city}_deprivation_sensitivity.csv", index=False)
        cur = cvt[cvt.axis == "curvature"]
        g_ev_rng = cur.gini_everyday.max() - cur.gini_everyday.min()
        g_em_rng = cur.gini_emergency.max() - cur.gini_emergency.min()
        hh_rng = cur.share_HH.max() - cur.share_HH.min()
        print(f"  {city}: across curvature variants — gini_everyday range "
              f"{g_ev_rng:.3f}, gini_emergency range {g_em_rng:.3f}; "
              f"HH-share range {hh_rng:.4f} (rank-based typology → near-0; "
              f"exact zero only held under the old composite-time estimator)")

    frames = {name: pd.DataFrame(d).T for name, d in per_variant.items()}
    if "baseline" not in frames:
        print("sensitivity: baseline targets unavailable")
        return

    # Rank-agreement of city ordering vs baseline, per stable target —
    # computed from the persisted per-city variant TABLES (unioned across
    # runs by the persist import), not from the cities staged in this run.
    # The staged-surfaces version needed every batch city's surfaces in one
    # job: any partial round (a paris-only resume) saw <= 2 cities, Spearman
    # needs 3, and depacc-results carried an all-NaN table for 67 cities.
    out = derived / "sensitivity"
    out.mkdir(parents=True, exist_ok=True)
    base = frames["baseline"]
    rank_table = rank_agreement_from_tables(out)
    if rank_table.empty or rank_table.n_cities.max() < 3:
        n = 0 if rank_table.empty else int(rank_table.n_cities.max())
        print(f"rank agreement skipped: only {n} persisted variant table(s) "
              f"(needs >= 3 cities); existing rank_agreement.csv left as-is")
    else:
        rank_table.to_csv(out / "rank_agreement.csv", index=False)
        print(f"rank agreement vs baseline over "
              f"{int(rank_table.n_cities.max())} cities "
              f"(min across variants):")
        for target, g in rank_table.groupby("target"):
            print(f"  {target}: min rho={g.spearman_rho.min():.3f} "
                  f"min tau={g.kendall_tau.min():.3f}")

    # These two tables are built ONLY from the cities whose surfaces were
    # staged in this run (they need the cell-level surfaces, which are not
    # persisted). Writing them straight out would shrink the accumulated
    # table to the current batch — how a 67-city flip-cell table became a
    # one-city table after a paris-only resume round. Merge instead: keep
    # every persisted city, let this run's rows win for the cities it
    # recomputed. Same union guarantee the rank-agreement table gets from
    # reading the persisted per-city variant tables.
    if flip_records:
        flip_df = _merge_persisted(out / "flip_cells.csv",
                                   pd.DataFrame(flip_records), ["city"])
        flip_df.to_csv(out / "flip_cells.csv", index=False)
        print(f"flip-cells: mean sensitive pop share "
              f"{flip_df.sensitive_pop_share.mean():.1%} across "
              f"{len(flip_df)} cities")

    # Typology-share envelope per city (min/max across variants).
    share_rows = []
    for city in base.index:
        for cls in ("LL", "LH", "HL", "HH"):
            vals = [frames[n].loc[city, f"share_{cls}"] for n in frames
                    if city in frames[n].index]
            share_rows.append({"city": city, "class": cls,
                               "baseline": base.loc[city, f"share_{cls}"],
                               "min": np.nanmin(vals), "max": np.nanmax(vals)})
    if share_rows:
        _merge_persisted(out / "typology_share_envelope.csv",
                         pd.DataFrame(share_rows), ["city", "class"]) \
            .to_csv(out / "typology_share_envelope.csv", index=False)

    # Specification curve: the cross-city Gini claims re-estimated under
    # every variant. Reads the per-city variant TABLES (unioned across runs
    # by the persist import), so it covers all persisted cities even when
    # only a few had surfaces staged in this run.
    from depacc.cityvector.clustering import _region_lookup
    from depacc.cityvector.spec_curve import run_spec_curve

    run_spec_curve(derived, _region_lookup(cfg))

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
