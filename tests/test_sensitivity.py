"""Robustness harness core: variant expansion, stable-target scale-invariance,
curvature rank-robustness, flip-cells."""

import numpy as np
import pandas as pd
import pytest

from depacc.config import load_config
from depacc.sensitivity.harness import (
    Variant,
    adjusted_rand,
    city_calibration_targets,
    city_stable_targets,
    city_variant_table,
    expand_variants,
    flip_cells,
)

BASE_EV = {"kind": "DLF", "form": "logistic", "params": {"Lmax": 1.0, "t0": 15.0, "k": 0.2}}
BASE_EM = {"kind": "DCF", "form": "box_cox", "params": {"lam": 1.8, "shift": 1.0, "scale": 1.0}}


def test_expand_variants_includes_baseline_and_curvature():
    cfg = load_config()
    grid = {"everyday": {"k": [0.1, 0.2, 0.3]}, "emergency": {"lam": [1.4, 1.8, 2.2]}}
    variants = expand_variants(cfg, grid)
    assert variants[0].name == "baseline"
    names = [v.name for v in variants]
    # baseline k=0.2 / lam=1.8 are skipped as no-ops; the off-baseline remain.
    assert any("everyday_k0.1" in n for n in names)
    assert any("emergency_lam2.2" in n for n in names)
    assert all(isinstance(v, Variant) for v in variants)


def test_stable_targets_scale_invariant_to_emergency_scale():
    rng = np.random.default_rng(0)
    n = 300
    t_ev = rng.uniform(0, 40, n)
    t_em = rng.uniform(0, 90, n)
    pop = rng.uniform(1, 500, n)
    a = city_stable_targets(t_ev, t_em, pop, BASE_EV, BASE_EM)
    # Scaling the emergency DCF (scale x1000) must not change Ginis/typology.
    em_scaled = {**BASE_EM, "params": {**BASE_EM["params"], "scale": 1000.0}}
    b = city_stable_targets(t_ev, t_em, pop, BASE_EV, em_scaled)
    assert a["gini_emergency"] == pytest.approx(b["gini_emergency"])
    assert a["divergence_gap"] == pytest.approx(b["divergence_gap"])
    for cls in ("LL", "LH", "HL", "HH"):
        assert a[f"share_{cls}"] == pytest.approx(b[f"share_{cls}"])


def test_curvature_preserves_city_rankings():
    """City ordering by divergence_gap is stable across a curvature tweak."""
    rng = np.random.default_rng(1)
    pop = rng.uniform(1, 100, 200)
    gaps_base, gaps_var = [], []
    em_var = {**BASE_EM, "params": {**BASE_EM["params"], "lam": 2.2}}
    for seed in range(8):  # 8 synthetic "cities"
        r = np.random.default_rng(seed)
        t_ev = r.uniform(0, 40, 200)
        t_em = r.uniform(0, 90, 200) + seed * 3  # cities differ systematically
        gaps_base.append(city_stable_targets(t_ev, t_em, pop, BASE_EV, BASE_EM)["divergence_gap"])
        gaps_var.append(city_stable_targets(t_ev, t_em, pop, BASE_EV, em_var)["divergence_gap"])
    from scipy.stats import spearmanr
    rho = spearmanr(gaps_base, gaps_var).correlation
    assert rho > 0.8  # rankings survive the curvature change


def _synthetic_surfaces(cfg, n, rng):
    surf = pd.DataFrame({"population": rng.uniform(1, 500, n)})
    for svc in cfg["everyday_services"]:
        surf[f"t_eff_{svc}"] = rng.uniform(0, 40, n)
    for svc in cfg["emergency_services"]:
        surf[f"t_nearest_{svc}"] = rng.uniform(0, 90, n)
    return surf


def test_city_variant_table_curvature_near_invariant_typology():
    """The co-location typology is rank-based, so curvature variants move the
    class shares only marginally (per-service ranks are invariant; the
    composite can drift slightly as curvature reweights the service mix)
    while the within-regime Ginis move materially; the threshold sweep, by
    contrast, moves the shares by design."""
    cfg = load_config()
    grid = {"everyday": {"k": [0.1, 0.2, 0.3]}, "emergency": {"lam": [1.4, 1.8, 2.2]}}
    variants = expand_variants(cfg, grid)
    rng = np.random.default_rng(3)
    surf = _synthetic_surfaces(cfg, 400, rng)
    tbl = city_variant_table(surf, cfg, variants, "c")
    cur = tbl[tbl.axis == "curvature"]
    # Class shares near-invariant across curvature variants (rank-based
    # typology; small composite-mix drift only).
    for cls in ("LL", "LH", "HL", "HH"):
        assert cur[f"share_{cls}"].max() - cur[f"share_{cls}"].min() < 0.02
    # But the Ginis genuinely move with curvature — an order of magnitude more
    # than the shares.
    assert cur["gini_emergency"].max() - cur["gini_emergency"].min() > 0.05
    assert cur["gini_everyday"].max() - cur["gini_everyday"].min() > 1e-2
    # Threshold sweep changes the compounding (HH) share monotonically down.
    thr = tbl[tbl.axis == "threshold"].sort_values("threshold")
    assert thr["share_HH"].is_monotonic_decreasing


def test_variant_composite_is_per_service_not_g_of_mean():
    """The variant recompute must equal the pipeline's estimator (weighted row
    mean of per-service g(t)) exactly, and must NOT equal g applied to the
    composite time — the Jensen gap that made the old sensitivity baseline
    (and the spec curve's ringed point) miss cityplane_row.csv."""
    from depacc.config import everyday_service_spec
    from depacc.deprivation.functions import DeprivationFunction
    from depacc.sensitivity.harness import variant_regime_deprivations

    cfg = load_config()
    rng = np.random.default_rng(7)
    surf = _synthetic_surfaces(cfg, 300, rng)
    ev_spec = cfg["deprivation"]["everyday"]
    em_spec = cfg["deprivation"]["emergency"]
    dep_ev, dep_em = variant_regime_deprivations(surf, cfg, ev_spec, em_spec)

    # Hand-built pipeline composite, with the config's composite weights.
    ev_services = list(cfg["everyday_services"])
    ev_weights = cfg["regimes"]["everyday"].get("composite_weights") or {}
    w = np.array([float(ev_weights.get(s, 1.0)) for s in ev_services])
    cols = []
    for s in ev_services:
        g = DeprivationFunction.from_spec(everyday_service_spec(cfg, s),
                                          context=f"t [{s}]")
        cols.append(g(surf[f"t_eff_{s}"].to_numpy(float)))
    vals = np.column_stack(cols)
    expected = (vals * w[None, :]).sum(axis=1) / w.sum()
    np.testing.assert_allclose(dep_ev, expected, rtol=0, atol=1e-12)

    # ...and the Jensen gap: g(mean t) is a different surface.
    g_ev = DeprivationFunction.from_spec(ev_spec, context="ev")
    t_mean = (np.column_stack(
        [surf[f"t_eff_{s}"].to_numpy(float) for s in ev_services])
        * w[None, :]).sum(axis=1) / w.sum()
    assert np.max(np.abs(g_ev(t_mean) - dep_ev)) > 1e-3

    # Emergency: same per-service estimator with the (two) emergency services.
    em_services = list(cfg["emergency_services"])
    em_weights = cfg["regimes"]["emergency"].get("composite_weights") or {}
    ew = np.array([float(em_weights.get(s, 1.0)) for s in em_services])
    g_em = DeprivationFunction.from_spec(em_spec, context="em")
    em_vals = np.column_stack(
        [g_em(surf[f"t_nearest_{s}"].to_numpy(float)) for s in em_services])
    em_expected = (em_vals * ew[None, :]).sum(axis=1) / ew.sum()
    np.testing.assert_allclose(dep_em, em_expected, rtol=0, atol=1e-12)


def test_variant_composite_masks_no_path_cells():
    cfg = load_config()
    rng = np.random.default_rng(11)
    surf = _synthetic_surfaces(cfg, 60, rng)
    surf["unreachable_everyday"] = np.array([True] * 4 + [False] * 56)
    surf["unreachable_emergency"] = np.array([True] * 4 + [False] * 56)
    from depacc.sensitivity.harness import variant_regime_deprivations

    dep_ev, dep_em = variant_regime_deprivations(
        surf, cfg, cfg["deprivation"]["everyday"], cfg["deprivation"]["emergency"])
    assert np.isnan(dep_ev[:4]).all() and np.isnan(dep_em[:4]).all()
    assert np.isfinite(dep_ev[4:]).all() and np.isfinite(dep_em[4:]).all()


def test_form_swap_resolves_named_alternatives():
    """Layer 2: a form_swap entry referencing a named alternative resolves to
    that alternative's anchor-calibrated spec, on the separate form_swap axis."""
    cfg = load_config()
    grid = {"form_swap": {"everyday": [{"alternative": "everyday_box_cox"}],
                          "emergency": [{"alternative": "emergency_exponential"}]}}
    variants = expand_variants(cfg, grid)
    by_name = {v.name: v for v in variants}
    assert by_name["formswap_everyday_box_cox"].layer == "form_swap"
    assert by_name["formswap_emergency_exponential"].layer == "form_swap"
    ev = by_name["formswap_everyday_box_cox"]
    # everyday regime swapped to the concave Box-Cox DLF; emergency baseline kept.
    assert ev.everyday["form"] == "box_cox" and ev.everyday["params"]["lam"] < 1
    assert ev.emergency == cfg["deprivation"]["emergency"]
    em = by_name["formswap_emergency_exponential"]
    assert em.emergency["form"] == "exponential"
    assert em.everyday == cfg["deprivation"]["everyday"]


def test_form_swap_unknown_alternative_raises():
    cfg = load_config()
    with pytest.raises(KeyError, match="unknown alternative"):
        expand_variants(cfg, {"form_swap": {"everyday": [{"alternative": "nope"}]}})


def test_city_table_separates_form_swap_from_curvature():
    """The curvature envelope (axis='curvature') must not absorb the Layer-2
    form-swap Ginis (axis='form_swap')."""
    cfg = load_config()
    grid = {"emergency": {"lam": [1.4, 1.8, 2.2]},
            "form_swap": {"emergency": [{"alternative": "emergency_exponential"}]}}
    variants = expand_variants(cfg, grid)
    rng = np.random.default_rng(5)
    surf = _synthetic_surfaces(cfg, 300, rng)
    tbl = city_variant_table(surf, cfg, variants, "c")
    assert (tbl.axis == "form_swap").any()
    cur = tbl[tbl.axis == "curvature"]
    assert not cur.variant.str.contains("formswap").any()


def test_adjusted_rand_identity_and_none_dropped():
    a = np.array(["LL", "HH", "HL", "LH", "HH"], dtype=object)
    assert adjusted_rand(a, a) == pytest.approx(1.0)
    b = np.array(["HH", "LL", "LH", "HL", "LL"], dtype=object)
    assert -0.6 <= adjusted_rand(a, b) <= 1.0
    # None pairs are dropped, not counted as a class.
    c = np.array(["LL", "HH", None, "LH", "HH"], dtype=object)
    assert adjusted_rand(a, c) == pytest.approx(1.0)


def test_calibration_targets_uniform_vs_per_service():
    cfg = load_config()  # everyday is logistic, per_service seeds present
    rng = np.random.default_rng(3)
    n = 400
    surf = pd.DataFrame({
        "population": rng.uniform(1, 500, n),
        "t_regime_emergency": rng.uniform(0, 90, n),
        "unreachable_everyday": np.zeros(n, dtype=bool),
    })
    for svc in cfg["everyday_services"]:
        surf[f"t_eff_{svc}"] = rng.uniform(0, 40, n)
    uni = city_calibration_targets(surf, cfg, "uniform")
    per = city_calibration_targets(surf, cfg, "per_service")
    for tgt in (uni, per):
        assert 0 <= tgt["gini_everyday"] <= 1
        assert {f"share_{c}" for c in ("LL", "LH", "HL", "HH")} <= set(tgt)
    # Per-service thresholds change the everyday surface, so at least one stable
    # target must differ (they are not identical by construction).
    assert (uni["gini_everyday"] != pytest.approx(per["gini_everyday"])
            or uni["share_HH"] != pytest.approx(per["share_HH"]))
    # Emergency is held fixed across the calibration variant.
    assert uni["gini_emergency"] == pytest.approx(per["gini_emergency"])


def test_calibration_masks_no_path_cells():
    cfg = load_config()
    rng = np.random.default_rng(5)
    n = 50
    surf = pd.DataFrame({
        "population": rng.uniform(1, 100, n),
        "t_regime_emergency": rng.uniform(0, 90, n),
        "unreachable_everyday": np.array([True] * 5 + [False] * (n - 5)),
    })
    for svc in cfg["everyday_services"]:
        surf[f"t_eff_{svc}"] = rng.uniform(0, 40, n)
    tgt = city_calibration_targets(surf, cfg, "per_service")
    # Masked cells are unclassified (they carry NaN everyday deprivation), so
    # the classified shares still sum to ~1 over the reachable cells.
    assert sum(tgt[f"share_{c}"] for c in ("LL", "LH", "HL", "HH")) == pytest.approx(1.0)


def test_rank_agreement_from_tables(tmp_path):
    """Cross-city rank agreement reads the persisted per-city variant tables,
    so it covers every persisted city — not just the cities whose surfaces
    were staged in the current run (the all-NaN-table failure mode)."""
    from depacc.sensitivity.harness import rank_agreement_from_tables

    ginis = {"a": 0.30, "b": 0.45, "c": 0.60, "d": 0.75}
    for city, g in ginis.items():
        rows = [
            # baseline
            dict(city=city, axis="curvature", variant="baseline",
                 layer="baseline", threshold=0.5, gini_everyday=g,
                 gini_emergency=g / 2, divergence_gap=-g / 2,
                 share_LL=0.3, share_LH=0.2, share_HL=0.2, share_HH=0.3),
            # order-preserving variant -> rho 1
            dict(city=city, axis="curvature", variant="mono",
                 layer="curvature", threshold=0.5, gini_everyday=g + 0.05,
                 gini_emergency=g / 2 + 0.01, divergence_gap=-g / 2,
                 share_LL=0.3, share_LH=0.2, share_HL=0.2, share_HH=0.3),
            # order-reversing variant -> rho -1
            dict(city=city, axis="curvature", variant="rev",
                 layer="curvature", threshold=0.5, gini_everyday=1.0 - g,
                 gini_emergency=g / 2, divergence_gap=-g / 2,
                 share_LL=0.3, share_LH=0.2, share_HL=0.2, share_HH=0.3),
            # threshold rows must be ignored
            dict(city=city, axis="threshold", variant="threshold_0.75",
                 layer="threshold", threshold=0.75, gini_everyday=np.nan,
                 gini_emergency=np.nan, divergence_gap=np.nan,
                 share_LL=0.6, share_LH=0.1, share_HL=0.1, share_HH=0.2),
        ]
        pd.DataFrame(rows).to_csv(
            tmp_path / f"{city}_deprivation_sensitivity.csv", index=False)

    table = rank_agreement_from_tables(tmp_path)
    assert set(table.variant) == {"mono", "rev"}
    assert (table.n_cities == 4).all()
    mono = table[(table.variant == "mono") & (table.target == "gini_everyday")]
    rev = table[(table.variant == "rev") & (table.target == "gini_everyday")]
    assert mono.spearman_rho.iloc[0] == pytest.approx(1.0)
    assert rev.spearman_rho.iloc[0] == pytest.approx(-1.0)


def test_rank_agreement_from_tables_empty_dir(tmp_path):
    from depacc.sensitivity.harness import rank_agreement_from_tables

    assert rank_agreement_from_tables(tmp_path).empty


def test_merge_persisted_keeps_cities_this_run_did_not_recompute(tmp_path):
    """A one-city resume round must not shrink an accumulated table."""
    from depacc.sensitivity.harness import _merge_persisted

    path = tmp_path / "flip_cells.csv"
    pd.DataFrame({"city": ["berlin", "madrid", "paris"],
                  "sensitive_pop_share": [0.09, 0.16, 0.50]}).to_csv(
        path, index=False)
    fresh = pd.DataFrame({"city": ["paris"], "sensitive_pop_share": [0.12]})
    out = _merge_persisted(path, fresh, ["city"])
    assert sorted(out.city) == ["berlin", "madrid", "paris"]
    # The rerun city takes this run's value, the others keep theirs.
    assert out.set_index("city").sensitive_pop_share["paris"] == 0.12
    assert out.set_index("city").sensitive_pop_share["berlin"] == 0.09
    # Nothing on disk yet, or an unusable file: the fresh table stands alone.
    assert _merge_persisted(tmp_path / "absent.csv", fresh,
                            ["city"]).equals(fresh)


def test_merge_persisted_uses_every_key_column(tmp_path):
    from depacc.sensitivity.harness import _merge_persisted

    path = tmp_path / "envelope.csv"
    pd.DataFrame({"city": ["berlin", "berlin", "paris"],
                  "class": ["HH", "LL", "HH"],
                  "baseline": [0.3, 0.2, 0.33]}).to_csv(path, index=False)
    fresh = pd.DataFrame({"city": ["paris"], "class": ["HH"],
                          "baseline": [0.34]})
    out = _merge_persisted(path, fresh, ["city", "class"])
    assert len(out) == 3
    assert out[(out.city == "paris") & (out["class"] == "HH")] \
        .baseline.iloc[0] == 0.34
    assert set(out[out.city == "berlin"]["class"]) == {"HH", "LL"}


def test_deprivation_sensitivity_summary_keeps_axes_apart(tmp_path):
    from depacc.sensitivity.harness import deprivation_sensitivity_summary

    rows = []
    for city, g in (("a", 0.50), ("b", 0.60)):
        rows += [
            {"city": city, "axis": "curvature", "variant": "baseline",
             "gini_everyday": g, "share_HH": 0.32},
            {"city": city, "axis": "curvature", "variant": "k0.3",
             "gini_everyday": g + 0.20, "share_HH": 0.33},
            {"city": city, "axis": "threshold", "variant": "threshold_0.75",
             "gini_everyday": np.nan, "share_HH": 0.14},
        ]
    pd.DataFrame(rows).to_csv(
        tmp_path / "a_deprivation_sensitivity.csv", index=False)
    out = deprivation_sensitivity_summary(tmp_path)

    curv = out[(out.city == "a") & (out.axis == "curvature")
               & (out.target == "gini_everyday")].iloc[0]
    assert curv.baseline == pytest.approx(0.50)
    assert curv.width == pytest.approx(0.20)
    assert curv.n_variants == 2
    # The threshold axis is its own envelope, never pooled with curvature.
    thr = out[(out.city == "a") & (out.axis == "threshold")
              & (out.target == "share_HH")].iloc[0]
    assert thr.width == pytest.approx(0.0)
    assert set(out.axis) == {"curvature", "threshold"}
    # An all-NaN target on an axis produces no row rather than a NaN row.
    assert out[(out.axis == "threshold")
               & (out.target == "gini_everyday")].empty


def test_deprivation_curves_figure_covers_both_layers(tmp_path):
    pytest.importorskip("matplotlib")
    from depacc.viz.deprivation_curves import plot_deprivation_curves

    cfg = load_config()
    grid = {"everyday": {"k": [0.1, 0.2, 0.3]},
            "emergency": {"lam": [1.4, 1.8, 2.2]},
            "form_swap": {"everyday": [{"alternative": "everyday_box_cox"}],
                          "emergency": [{"alternative":
                                         "emergency_exponential"}]}}
    out = plot_deprivation_curves(cfg, grid, tmp_path / "curves.png")
    assert out.exists() and out.stat().st_size > 0


def test_deprivation_curve_helper_uses_the_reporting_anchor():
    from depacc.viz.deprivation_curves import _curve

    cfg = load_config()
    spec = cfg["deprivation"]["emergency"]
    t = np.array([15.0, 30.0])
    anchored = _curve(spec, t, 15.0)
    raw = _curve(spec, t, None)
    assert anchored[0] == pytest.approx(1.0)          # g(15) = 1 by anchor
    assert anchored[1] == pytest.approx(raw[1] / raw[0])
    assert anchored[1] > 1.0                          # escalating past 15 min


def test_emergency_anchor_encodes_the_ems_benchmark_windows():
    """The re-anchored DCF must read as the three-window benchmark
    structure (Pons 2005; Vo 2020; Khan 2026): negligible below the 3-4 min
    ideal, well under half at the WHO-recommended 8 (convexity caps
    g(8)/g(15) at 0.427 given g(4)/g(15)=0.1), 1.0 at the 15-min target."""
    from depacc.viz.deprivation_curves import _curve

    cfg = load_config()
    spec = cfg["deprivation"]["emergency"]
    assert float(spec["reference_time_min"]) == 15.0
    r = _curve(spec, np.array([3.0, 4.0, 8.0, 15.0]), 15.0)
    assert r[0] < 0.10 and r[1] < 0.15                # negligible <= 3-4 min
    assert 0.25 < r[2] < 0.427                        # intermediate, convex-feasible
    assert r[3] == pytest.approx(1.0)


def test_flip_cells():
    base = np.array(["LL", "HH", "HL", "LH"], dtype=object)
    v1 = np.array(["LL", "HH", "HH", "LH"], dtype=object)   # cell 2 flips
    v2 = np.array(["LL", "HL", "HL", "LH"], dtype=object)   # cell 1 flips
    pop = np.array([10.0, 10.0, 10.0, 10.0])
    fc = flip_cells(base, [v1, v2], pop)
    assert fc["flip_mask"].tolist() == [False, True, True, False]
    assert fc["sensitive_pop_share"] == pytest.approx(0.5)
    assert fc["stable_pop_share"] == pytest.approx(0.5)
