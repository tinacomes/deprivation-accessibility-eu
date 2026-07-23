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


def test_city_variant_table_curvature_invariant_typology():
    """The co-location typology is rank-based, so curvature variants leave the
    class shares identical while the within-regime Ginis move; the threshold
    sweep, by contrast, moves the shares."""
    cfg = load_config()
    grid = {"everyday": {"k": [0.1, 0.2, 0.3]}, "emergency": {"lam": [1.4, 1.8, 2.2]}}
    variants = expand_variants(cfg, grid)
    rng = np.random.default_rng(3)
    n = 400
    t_ev = rng.uniform(0, 40, n)
    t_em = rng.uniform(0, 90, n)
    pop = rng.uniform(1, 500, n)
    tbl = city_variant_table(t_ev, t_em, pop, variants, "c")
    cur = tbl[tbl.axis == "curvature"]
    # Class shares invariant across curvature variants (rank-based typology).
    for cls in ("LL", "LH", "HL", "HH"):
        assert cur[f"share_{cls}"].nunique() == 1
    # But the everyday Gini genuinely moves with curvature.
    assert cur["gini_everyday"].max() - cur["gini_everyday"].min() > 1e-3
    # Threshold sweep changes the compounding (HH) share monotonically down.
    thr = tbl[tbl.axis == "threshold"].sort_values("threshold")
    assert thr["share_HH"].is_monotonic_decreasing


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
    n = 300
    t_ev, t_em = rng.uniform(0, 40, n), rng.uniform(0, 90, n)
    pop = rng.uniform(1, 100, n)
    tbl = city_variant_table(t_ev, t_em, pop, variants, "c")
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


def test_flip_cells():
    base = np.array(["LL", "HH", "HL", "LH"], dtype=object)
    v1 = np.array(["LL", "HH", "HH", "LH"], dtype=object)   # cell 2 flips
    v2 = np.array(["LL", "HL", "HL", "LH"], dtype=object)   # cell 1 flips
    pop = np.array([10.0, 10.0, 10.0, 10.0])
    fc = flip_cells(base, [v1, v2], pop)
    assert fc["flip_mask"].tolist() == [False, True, True, False]
    assert fc["sensitive_pop_share"] == pytest.approx(0.5)
    assert fc["stable_pop_share"] == pytest.approx(0.5)
