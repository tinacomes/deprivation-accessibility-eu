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
    assert float(ex(60.0)) / float(ex(45.0)) == pytest.approx(
        float(base(60.0)) / float(base(45.0)), rel=2e-3)  # clinical-threshold ratio
    for g in (bc, ex):
        assert g.source and "TODO(cite)" not in g.source


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
