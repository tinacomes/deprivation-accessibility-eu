"""Standardisation primitive: percentile properties (the scale-robustness
proof), z-score, and the cross-regime guards (the contract)."""

import numpy as np
import pytest

from depacc.standardize import (
    RegimeSurface,
    require_percentile,
    require_same_standardised,
    require_standardised,
    to_percentile,
    to_zscore,
)


def _surf(values, pop=None, regime="emergency", city="c1", state="raw"):
    values = np.asarray(values, float)
    pop = np.ones_like(values) if pop is None else np.asarray(pop, float)
    return RegimeSurface(values, pop, regime, city, state)


def test_percentile_in_unit_interval_and_monotone():
    s = to_percentile(_surf([5.0, 1.0, 3.0, 2.0, 4.0]))
    assert s.scale_state == "percentile"
    v = s.values
    assert np.all((v >= 0) & (v <= 1))
    # Monotone: order of percentiles matches order of raw values.
    raw = np.array([5.0, 1.0, 3.0, 2.0, 4.0])
    assert np.array_equal(np.argsort(raw), np.argsort(v))


def test_percentile_invariant_to_increasing_rescale():
    """THE scale-robustness proof: multiplying the emergency surface by 1000
    (or any strictly increasing map) yields identical percentiles."""
    base = _surf([0.0, 10.0, 41.0, 546.0, 908.0], pop=[3, 1, 4, 1, 5])
    p1 = to_percentile(base).values
    p2 = to_percentile(_surf(base.values * 1000.0, pop=base.population)).values
    p3 = to_percentile(_surf(np.exp(base.values / 200.0), pop=base.population)).values
    assert np.allclose(p1, p2)
    assert np.allclose(p1, p3)


def test_percentile_population_weighted_and_ties():
    # Cell with huge population dominates the weighted CDF; ties share a value
    # and sit at the MIDPOINT of their block, not its top.
    s = to_percentile(_surf([1.0, 1.0, 2.0], pop=[1.0, 1.0, 8.0]))
    assert s.values[0] == pytest.approx(s.values[1])   # tie
    assert s.values[0] == pytest.approx(0.1)            # block [0, 2]/10 -> 0.1
    assert s.values[2] == pytest.approx(0.6)            # block [2, 10]/10 -> 0.6


def test_large_bottom_tie_block_reads_low_not_high():
    """The tie rule that broke the Layer-3 sweep. 90 % of the population share
    the MINIMUM value; under the old inclusive rank P(X <= x) they all got 0.90
    and were classified "high" at both the p50 and p75 cuts — the least-deprived
    population labelled most-deprived. Mid-rank puts them at 0.45, i.e. low."""
    values = [0.0] * 9 + [1.0]
    s = to_percentile(_surf(values, pop=[1.0] * 10))
    assert s.values[0] == pytest.approx(0.45)
    assert np.all(s.values[:9] < 0.5)      # the block reads LOW
    assert s.values[9] == pytest.approx(0.95)


def test_percentile_cut_leaves_the_right_mass_above_it():
    """The typology's accounting identity (docs §1.1) assumes cutting at q
    leaves (1 - q) of the population above the cut. Mid-rank delivers that for a
    tie-free surface; the inclusive rank shifted every cell up by its own weight."""
    v = np.arange(1.0, 101.0)
    pct = to_percentile(_surf(v, pop=np.ones_like(v))).values
    for q in (0.5, 0.75):
        assert (pct >= q).mean() == pytest.approx(1.0 - q, abs=0.01)


def test_nan_cells_excluded():
    s = to_percentile(_surf([1.0, np.nan, 2.0], pop=[1.0, 5.0, 1.0]))
    assert np.isnan(s.values[1])
    assert np.isfinite(s.values[0]) and np.isfinite(s.values[2])


def test_zscore_weighted():
    s = to_zscore(_surf([1.0, 3.0], pop=[1.0, 1.0]))
    assert s.scale_state == "zscore"
    assert s.values[0] == pytest.approx(-1.0)
    assert s.values[1] == pytest.approx(1.0)


def test_guards_reject_raw():
    raw = _surf([1.0, 2.0])
    with pytest.raises(ValueError, match="standardise first"):
        require_standardised(raw)
    pct = to_percentile(raw)
    require_standardised(pct)  # ok


def test_same_standardised_requires_matching_state_and_city():
    a = to_percentile(_surf([1.0, 2.0], regime="everyday", city="c1"))
    b = to_percentile(_surf([1.0, 2.0], regime="emergency", city="c1"))
    require_same_standardised(a, b)  # ok
    with pytest.raises(ValueError, match="scale_state mismatch"):
        require_same_standardised(a, to_zscore(_surf([1.0, 2.0], city="c1")))
    with pytest.raises(ValueError, match="city_id mismatch"):
        require_same_standardised(a, to_percentile(_surf([1.0, 2.0], city="OTHER")))


def test_typology_requires_percentile_not_zscore():
    z = to_zscore(_surf([1.0, 2.0]))
    with pytest.raises(ValueError, match="requires percentile"):
        require_percentile(z)
    require_percentile(to_percentile(_surf([1.0, 2.0])))  # ok
