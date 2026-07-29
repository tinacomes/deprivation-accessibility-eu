"""Divergence typology on percentile surfaces + co-location statistics."""

import numpy as np
import pytest

from depacc.divergence.colocation import (
    compounding_intensity,
    compounding_pop_share,
    jaccard_high,
    weighted_spearman,
)
from depacc.divergence.typology import bivariate_typology, classify
from depacc.standardize import RegimeSurface, to_percentile


def _pct(values, pop=None, regime="everyday", city="c1"):
    values = np.asarray(values, float)
    pop = np.ones_like(values) if pop is None else np.asarray(pop, float)
    return to_percentile(RegimeSurface(values, pop, regime, city, "raw"))


def test_classify_four_quadrants():
    # everyday percentile, emergency percentile designed to hit each quadrant.
    ev = np.array([0.1, 0.1, 0.9, 0.9])
    em = np.array([0.1, 0.9, 0.1, 0.9])
    labels = classify(ev, em, threshold=0.5)
    assert list(labels) == ["LL", "LH", "HL", "HH"]


def test_typology_requires_percentile():
    raw_e = RegimeSurface(np.array([1.0, 2.0]), np.ones(2), "everyday", "c1", "raw")
    raw_m = RegimeSurface(np.array([1.0, 2.0]), np.ones(2), "emergency", "c1", "raw")
    with pytest.raises(ValueError, match="requires percentile"):
        bivariate_typology(raw_e, raw_m)


def test_pop_weighted_shares_sum_to_one():
    e = _pct([1, 2, 3, 4, 5, 6, 7, 8], regime="everyday")
    m = _pct([8, 7, 6, 5, 4, 3, 2, 1], regime="emergency")
    _, summary = bivariate_typology(e, m, threshold=0.5)
    assert summary["population_share"].sum() == pytest.approx(1.0)


def test_higher_threshold_shrinks_compounding():
    rng = np.random.default_rng(0)
    ev = rng.uniform(size=200)
    em = 0.7 * ev + 0.3 * rng.uniform(size=200)  # positively coupled
    e = _pct(ev, regime="everyday"); m = _pct(em, regime="emergency")
    hh50 = compounding_pop_share(e, m, 0.5)
    hh75 = compounding_pop_share(e, m, 0.75)
    assert hh75 <= hh50


def test_spearman_scale_invariant():
    ev = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    em = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    e = _pct(ev, regime="everyday")
    m1 = _pct(em, regime="emergency")
    m2 = _pct(em * 1000.0, regime="emergency")   # scaled emergency
    assert weighted_spearman(e, m1) == pytest.approx(weighted_spearman(e, m2))
    assert weighted_spearman(e, m1) == pytest.approx(1.0, abs=1e-9)  # perfect rank match


def test_compounding_intensity_anchors():
    """Pop-weighted mean of min(ev_pct, em_pct): 1/2 comonotone, ~1/4
    countermonotone, ~1/3 independent — the documented anchors."""
    n = 4000
    rng = np.random.default_rng(1)
    base = rng.uniform(size=n)
    e = _pct(base, regime="everyday")
    same = _pct(base * 3.0, regime="emergency")          # comonotone (scaled)
    opposite = _pct(-base, regime="emergency")           # countermonotone
    indep = _pct(rng.uniform(size=n), regime="emergency")
    assert compounding_intensity(e, same) == pytest.approx(0.5, abs=0.01)
    assert compounding_intensity(e, opposite) == pytest.approx(0.25, abs=0.01)
    assert compounding_intensity(e, indep) == pytest.approx(1 / 3, abs=0.02)


def test_compounding_intensity_comonotone_anchor_is_weight_robust():
    """Identical surfaces hit the 0.5 anchor EXACTLY, whatever the weights:
    with mid-rank percentiles the pop-weighted mean percentile is 1/2 by
    construction, so the comonotone anchor cannot drift with the population
    distribution."""
    vals = np.array([1.0, 2.0, 3.0, 4.0])
    for pop in (None, np.array([100.0, 1.0, 1.0, 1.0]),
                np.array([1.0, 1.0, 1.0, 50.0])):
        e = _pct(vals, pop=pop, regime="everyday")
        m = _pct(vals, pop=pop, regime="emergency")
        assert compounding_intensity(e, m) == pytest.approx(0.5, abs=1e-12)


def test_jaccard_high_bounds():
    e = _pct([0.0, 1.0, 2.0, 3.0], regime="everyday")
    m = _pct([0.0, 1.0, 2.0, 3.0], regime="emergency")
    # identical surfaces -> high sets coincide -> Jaccard 1.
    assert jaccard_high(e, m, 0.5) == pytest.approx(1.0)
