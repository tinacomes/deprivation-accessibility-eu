"""DLF/DCF mapping: shape properties, config round-trip, null-parameter guard.

Tests use SYNTHETIC parameters passed explicitly; they never rely on (or leak
into) the literature-transferred values, which remain null placeholders in
config/deprivation.yaml until filled from the cited papers.
"""

import numpy as np
import pytest

from depacc.config import ConfigError, MissingParameterError, load_config, deprivation_spec
from depacc.deprivation.functions import DeprivationFunction

EXP = dict(form="exponential", params={"beta": 0.05, "scale": 1.0})
BC = dict(form="box_cox", params={"lam": 1.5, "scale": 2.0, "shift": 1.0})
LOG = dict(form="logistic", params={"Lmax": 1.0, "t0": 15.0, "k": 0.2})


@pytest.mark.parametrize("spec", [EXP, BC])
def test_zero_time_zero_deprivation(spec):
    g = DeprivationFunction(**spec)
    assert g(0.0) == pytest.approx(0.0)


@pytest.mark.parametrize("spec", [EXP, BC])
def test_increasing_and_convex(spec):
    g = DeprivationFunction(**spec)
    t = np.linspace(0, 120, 481)
    y = g(t)
    dy = np.diff(y)
    assert np.all(dy > 0), "deprivation must strictly increase in travel time"
    d2y = np.diff(dy)
    assert np.all(d2y >= -1e-9), "deprivation must be convex in travel time"


def test_nan_propagates():
    g = DeprivationFunction(**EXP)
    out = g(np.array([10.0, np.nan]))
    assert np.isnan(out[1]) and not np.isnan(out[0])


def test_negative_time_rejected():
    g = DeprivationFunction(**EXP)
    with pytest.raises(ValueError):
        g(-1.0)


def test_logistic_zero_anchored_by_default():
    """Everyday logistic (zero-anchored): increasing, g(0)=0, saturates at Lmax."""
    g = DeprivationFunction(**LOG)
    t = np.linspace(0, 120, 481)
    y = g(t)
    assert np.all(np.diff(y) > 0), "logistic must strictly increase"
    assert np.all(y < LOG["params"]["Lmax"] + 1e-9)     # bounded above
    assert float(g(0.0)) == pytest.approx(0.0, abs=1e-12)  # zero-anchored
    assert y[-1] == pytest.approx(1.0, abs=1e-3)           # saturates near Lmax


def test_logistic_raw_variant_has_baseline_and_half_at_t0():
    """Without zero-anchoring: raw logistic, g(15)=0.5, small g(0) baseline."""
    g = DeprivationFunction(form="logistic", params=LOG["params"], zero_anchor=False)
    assert float(g(15.0)) == pytest.approx(0.5, abs=1e-6)  # inflection at t0
    assert 0 < float(g(0.0)) < 0.1                          # baseline artifact


@pytest.mark.parametrize(
    "form,params",
    [
        ("exponential", {"beta": -0.1, "scale": 1.0}),  # decreasing
        ("box_cox", {"lam": 0.0, "scale": 1.0, "shift": 1.0}),  # lam <= 0
        ("box_cox", {"lam": 2.0, "scale": -1.0, "shift": 1.0}),  # negative scale
        ("logistic", {"Lmax": 1.0, "t0": 15.0, "k": -0.2}),  # decreasing
        ("logistic", {"Lmax": -1.0, "t0": 15.0, "k": 0.2}),  # negative ceiling
        ("logistic", {"Lmax": 1.0, "k": 0.2}),  # missing t0
        ("nope", {"beta": 0.1, "scale": 1.0}),  # unknown form
    ],
)
def test_invalid_specs_rejected(form, params):
    with pytest.raises(ConfigError):
        DeprivationFunction(form=form, params=params)


def test_box_cox_convexity_is_kind_aware():
    """A saturating DLF may use the concave Box-Cox branch (lam<1); an
    escalating DCF must stay convex (lam>1)."""
    g = DeprivationFunction(form="box_cox", kind="DLF",
                            params={"lam": 0.546, "scale": 0.077, "shift": 1.0})
    y = g(np.array([0.0, 15.0, 45.0]))
    assert y[0] == pytest.approx(0.0) and np.all(np.diff(y) > 0)  # increasing, g(0)=0
    assert y[1] == pytest.approx(0.5 * y[2], rel=2e-3)            # 15/45 anchor
    # concave second difference (saturating), the opposite of the convex DCF.
    assert float(np.diff(np.diff(g(np.linspace(0, 60, 61))))[10]) < 0
    with pytest.raises(ConfigError):
        DeprivationFunction(form="box_cox", kind="DCF",
                            params={"lam": 0.9, "scale": 1.0, "shift": 1.0})


def test_shipped_alternatives_are_anchor_calibrated():
    """The shipped Layer-2 alternatives build, are cited (no TODO), and hit the
    SAME domain anchors as the baselines they swap in for."""
    cfg = load_config()
    bc = DeprivationFunction.from_spec(
        deprivation_spec(cfg, "everyday", alternative="everyday_box_cox"))
    assert bc.form == "box_cox" and bc.kind == "DLF"
    assert float(bc(15.0)) == pytest.approx(0.5 * float(bc(45.0)), rel=2e-3)
    assert float(bc(45.0)) == pytest.approx(1.0, rel=2e-3)  # logistic ceiling
    ex = DeprivationFunction.from_spec(
        deprivation_spec(cfg, "emergency", alternative="emergency_exponential"))
    base = DeprivationFunction.from_spec(deprivation_spec(cfg, "emergency"))
    assert ex.form == "exponential" and ex.kind == "DCF"
    # EMS-benchmark anchors (8/15 min): the forms share the escalation ratio
    # across the benchmark window and coincide at both anchor points.
    assert float(ex(15.0)) / float(ex(8.0)) == pytest.approx(
        float(base(15.0)) / float(base(8.0)), rel=2e-3)
    for g in (bc, ex):
        assert g.source and "TODO(cite)" not in g.source


def test_survival_alternative_is_bounded_and_anchor_calibrated():
    """The bounded survival-based DCF swap: 1 = full deprivation, the SAME
    4/8/15-min benchmark ratio anchors as the baseline Box-Cox, and
    saturation (~full deprivation by 30-45 min) emerging from those anchors."""
    cfg = load_config()
    sv = DeprivationFunction.from_spec(
        deprivation_spec(cfg, "emergency", alternative="emergency_survival"))
    base = DeprivationFunction.from_spec(deprivation_spec(cfg, "emergency"))
    assert sv.form == "logistic" and sv.kind == "DCF"
    assert sv.source and "TODO(cite)" not in sv.source
    # Benchmark-window ratio anchors match the baseline exactly.
    for t in (4.0, 8.0):
        assert float(sv(t)) / float(sv(15.0)) == pytest.approx(
            float(base(t)) / float(base(15.0)), rel=2e-3)
    # Bounded: 1 = full deprivation, approached but never exceeded.
    assert float(sv(30.0)) == pytest.approx(0.982, abs=2e-3)
    assert float(sv(45.0)) > 0.999
    assert float(sv(240.0)) <= 1.0
    # The three escalation hypotheses diverge only beyond the 15-min cut-off:
    # saturating < polynomial (Box-Cox ~11x) at 60 min.
    assert float(sv(60.0)) / float(sv(15.0)) < 2.0
    assert float(base(60.0)) / float(base(15.0)) > 10.0


def test_from_spec_round_trip():
    spec = {"kind": "DCF", "form": "box_cox",
            "params": {"lam": 1.2, "scale": 3.0, "shift": 1.0},
            "source": "synthetic test values"}
    g = DeprivationFunction.from_spec(spec)
    assert g.kind == "DCF"
    assert g(30.0) > g(10.0) > 0


def test_shipped_config_builds_and_is_cited():
    """The shipped config now carries literature-transferred values: it must
    build both regimes and each must carry a non-empty source citation."""
    cfg = load_config()
    everyday = DeprivationFunction.from_spec(deprivation_spec(cfg, "everyday"))
    emergency = DeprivationFunction.from_spec(deprivation_spec(cfg, "emergency"))
    assert everyday.form == "logistic" and everyday.kind == "DLF"
    assert emergency.form == "box_cox" and emergency.kind == "DCF"
    for g in (everyday, emergency):
        assert g.source and "TODO(cite)" not in g.source
    # Everyday saturates (bounded); emergency escalates (far larger at 60 min).
    assert float(everyday(60.0)) <= 1.0
    assert float(emergency(60.0)) > float(everyday(60.0))


def test_null_params_still_guarded():
    """A spec that still has a null placeholder must raise, citing its source."""
    spec = {"form": "logistic", "params": {"Lmax": 1.0, "t0": None, "k": 0.2},
            "source": "TODO(cite): some paper"}
    with pytest.raises(MissingParameterError) as err:
        DeprivationFunction.from_spec(spec)
    assert "TODO(cite)" in str(err.value)


# ---------------------------------------------------------------------------
# Reporting anchor (reference_time_min): the fix for the off-scale emergency
# level. Dividing the unbounded DCF by g(t_ref) makes the reported mean
# interpretable while leaving every rank- and ratio-based output untouched.
# ---------------------------------------------------------------------------

ANCHORED = dict(kind="DCF", form="box_cox",
                params={"lam": 1.8, "scale": 1.0, "shift": 1.0},
                reference_time_min=45.0)


def test_reference_time_normalises_to_one_at_the_anchor():
    g = DeprivationFunction(**ANCHORED)
    assert float(g(45.0)) == pytest.approx(1.0)
    # It does NOT bound the function: escalation past the anchor reads > 1.
    assert float(g(60.0)) > 1.0
    assert float(g(0.0)) == pytest.approx(0.0)


def test_reference_time_is_a_constant_rescaling_of_the_raw_function():
    raw = DeprivationFunction(**{k: v for k, v in ANCHORED.items()
                                 if k != "reference_time_min"})
    g = DeprivationFunction(**ANCHORED)
    t = np.array([0.0, 3.9, 14.4, 45.0, 60.0, 120.0])
    ratio = np.asarray(g(t))[1:] / np.asarray(raw(t))[1:]
    assert np.allclose(ratio, ratio[0])                 # one constant factor
    assert ratio[0] == pytest.approx(1.0 / float(raw(45.0)))


def test_anchor_leaves_every_rank_and_inequality_output_unchanged():
    """The anchor may change reported LEVELS only. Gini, the concentration
    index, the p90/p50 ratio and the population-weighted percentiles must be
    identical, because they are invariant to a positive constant factor."""
    from depacc.divergence.cityplane import _p90_p50
    from depacc.equity.indices import concentration_index, weighted_gini
    from depacc.standardize import RegimeSurface, to_percentile

    rng = np.random.default_rng(7)
    t = rng.uniform(1.0, 40.0, 500)
    pop = rng.uniform(1.0, 200.0, 500)
    ses = rng.uniform(0.3, 0.8, 500)
    raw = DeprivationFunction(**{k: v for k, v in ANCHORED.items()
                                 if k != "reference_time_min"})
    g = DeprivationFunction(**ANCHORED)
    d_raw, d_anch = np.asarray(raw(t)), np.asarray(g(t))

    assert weighted_gini(d_anch, pop) == pytest.approx(weighted_gini(d_raw, pop))
    assert concentration_index(d_anch, ses, pop) == pytest.approx(
        concentration_index(d_raw, ses, pop))
    assert _p90_p50(d_anch, pop) == pytest.approx(_p90_p50(d_raw, pop))
    pct = [to_percentile(RegimeSurface(d, pop, "emergency", "c")).values
           for d in (d_raw, d_anch)]
    assert np.allclose(*pct)
    # ... while the reported LEVEL becomes readable (multiples of g(t_ref)).
    assert np.average(d_raw, weights=pop) > 10.0
    assert np.average(d_anch, weights=pop) < 1.0


def test_shipped_emergency_config_is_anchored_and_readable():
    cfg = load_config()
    em = DeprivationFunction.from_spec(deprivation_spec(cfg, "emergency"))
    assert em.reference_time_min == 15.0
    assert float(em(15.0)) == pytest.approx(1.0)
    # Hamburg's observed median (3.9 min) and p90 (14.4 min) car times to an
    # ED read directly against the EMS benchmark scale: ~11% of the 15-min
    # target cost at the median, just under it at the p90.
    assert 0.0 < float(em(3.9)) < 0.15
    assert 0.5 < float(em(14.4)) < 1.0
    assert "multiples of g(15 min)" in em.units
    # The Layer-2 form swap shares the anchor, so both forms read 1.0 there and
    # the alternative's free `scale` cancels entirely.
    alt = DeprivationFunction.from_spec(
        deprivation_spec(cfg, "emergency", alternative="emergency_exponential"))
    assert float(alt(15.0)) == pytest.approx(1.0)
    # The everyday DLF needs no anchor: it is bounded by its own ceiling.
    everyday = DeprivationFunction.from_spec(deprivation_spec(cfg, "everyday"))
    assert everyday.reference_time_min is None
    assert "saturation ceiling" in everyday.units


@pytest.mark.parametrize("bad", [0.0, -5.0])
def test_non_positive_reference_time_rejected(bad):
    with pytest.raises(ConfigError, match="reference_time_min"):
        DeprivationFunction(**{**ANCHORED, "reference_time_min": bad})
