"""RegimeSurface and the standardisation transforms + guards.

All aggregation is POPULATION-WEIGHTED (deprivation is about people). Empty /
NaN cells are excluded from the weighting throughout (their standardised
value is NaN and never contributes to weighted counts, means or SDs).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

SCALE_STATES = ("raw", "percentile", "zscore")


@dataclass(frozen=True)
class RegimeSurface:
    """A per-cell deprivation surface for one regime of one city, tagged with
    its current scale state so cross-regime consumers can enforce that raw
    magnitudes are never combined.

    ``values`` and ``population`` are 1-D arrays aligned per populated cell.
    """

    values: np.ndarray
    population: np.ndarray
    regime: str            # "everyday" | "emergency"
    city_id: str
    scale_state: str = "raw"

    def __post_init__(self) -> None:
        v = np.asarray(self.values, dtype=float)
        p = np.asarray(self.population, dtype=float)
        if v.shape != p.shape or v.ndim != 1:
            raise ValueError("values and population must be 1-D arrays of equal length")
        if self.regime not in ("everyday", "emergency"):
            raise ValueError(f"unknown regime {self.regime!r}")
        if self.scale_state not in SCALE_STATES:
            raise ValueError(f"unknown scale_state {self.scale_state!r}")
        object.__setattr__(self, "values", v)
        object.__setattr__(self, "population", p)

    # -- validity mask (finite value AND positive weight) -------------------
    @property
    def valid(self) -> np.ndarray:
        return np.isfinite(self.values) & np.isfinite(self.population) & (self.population > 0)


def _weighted_mean_sd(v: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    mu = np.average(v, weights=w)
    var = np.average((v - mu) ** 2, weights=w)
    return float(mu), float(np.sqrt(var))


def to_percentile(surface: RegimeSurface) -> RegimeSurface:
    """Population-weighted MID-RANK empirical CDF: each cell -> the weighted
    population strictly below its value plus HALF the weight of its own tie
    group, over total valid pop. Result in [0, 1], monotone in the input and
    invariant to any strictly increasing rescaling — this is what tames the
    unbounded emergency tail. NaN cells stay NaN.

    Mid-rank, not the inclusive rank P(X <= x), because a tie group is a set of
    cells that the surface cannot tell apart and the percentile must place them
    where they collectively sit, not at the top of their own block. The
    difference is invisible until a tie group is large, and then it inverts the
    meaning of the cut: a degenerate everyday surface whose least-deprived 90 %
    share one floored value gets percentile 0.90 under the inclusive rank and is
    classified "high" at BOTH the p50 and p75 thresholds — the least-deprived
    population labelled most-deprived. That is what the κ = 0.1 and walk+car
    Layer-3 variants produced (100 % of Hamburg everyday-high, LL = LH = 0). Under
    mid-rank the same block lands at 0.45 and reads "low", which is the honest
    answer for a surface that has stopped discriminating; the degeneracy is then
    detected and reported on its own terms (see depacc.sensitivity.access).

    Mid-rank is also what the typology's accounting identity assumes: cutting at
    q leaves (1 - q) of the population above the cut, exactly, up to ties.
    """
    v, w = surface.values, surface.population
    mask = surface.valid
    out = np.full(v.shape, np.nan)
    if not mask.any():
        return replace(surface, values=out, scale_state="percentile")
    vv, ww = v[mask], w[mask]
    order = np.argsort(vv, kind="mergesort")
    vs, wsorted = vv[order], ww[order]
    cum = np.cumsum(wsorted)
    total = cum[-1]
    # Map each sorted position to the MIDPOINT of its tie group's weight span,
    # so equal values receive an equal percentile centred on the block.
    pct_sorted = np.empty_like(vs)
    i = 0
    n = len(vs)
    while i < n:
        j = i
        while j + 1 < n and vs[j + 1] == vs[i]:
            j += 1
        below = cum[i - 1] if i > 0 else 0.0
        pct_sorted[i:j + 1] = 0.5 * (below + cum[j]) / total
        i = j + 1
    pct = np.empty_like(vv)
    pct[order] = pct_sorted
    out[mask] = pct
    return replace(surface, values=out, scale_state="percentile")


def max_tie_pop_share(values, population) -> float:
    """Population share of the largest exact-tie group among valid cells.

    A surface whose largest tie block exceeds 0.5 cannot support a median split:
    the percentile surface is constant over more than half the population, so the
    typology cut falls inside one indistinguishable block and the resulting class
    shares say nothing about that population. Used to flag degenerate variants
    rather than letting them set a sensitivity headline.
    """
    v = np.asarray(values, dtype=float)
    w = np.asarray(population, dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        return float("nan")
    vv, ww = v[mask], w[mask]
    total = ww.sum()
    if total <= 0:
        return float("nan")
    order = np.argsort(vv, kind="mergesort")
    vs, ws = vv[order], ww[order]
    best, i, n = 0.0, 0, len(vs)
    while i < n:
        j = i
        while j + 1 < n and vs[j + 1] == vs[i]:
            j += 1
        best = max(best, float(ws[i:j + 1].sum()))
        i = j + 1
    return best / float(total)


def to_zscore(surface: RegimeSurface) -> RegimeSurface:
    """Population-weighted z-score (v - weighted_mean) / weighted_sd. Used for
    feature vectors, NOT the typology. NaN cells stay NaN."""
    v, w = surface.values, surface.population
    mask = surface.valid
    out = np.full(v.shape, np.nan)
    if mask.sum() >= 2:
        mu, sd = _weighted_mean_sd(v[mask], w[mask])
        out[mask] = (v[mask] - mu) / sd if sd > 0 else 0.0
    return replace(surface, values=out, scale_state="zscore")


# -- guards: the contract -----------------------------------------------------

def require_standardised(*surfaces: RegimeSurface) -> None:
    """Reject any raw surface entering a cross-regime operation."""
    for s in surfaces:
        if s.scale_state == "raw":
            raise ValueError(
                "cross-regime op on raw surfaces — standardise first "
                "(to_percentile / to_zscore)"
            )


def require_same_standardised(a: RegimeSurface, b: RegimeSurface) -> None:
    """Two surfaces combined together must be standardised, in the SAME scale
    state, and from the SAME city."""
    require_standardised(a, b)
    if a.scale_state != b.scale_state:
        raise ValueError(
            f"scale_state mismatch: {a.scale_state!r} vs {b.scale_state!r}")
    if a.city_id != b.city_id:
        raise ValueError(f"city_id mismatch: {a.city_id!r} vs {b.city_id!r}")


def require_percentile(*surfaces: RegimeSurface) -> None:
    """The typology is defined on percentiles specifically — raw AND zscore
    are both rejected here."""
    for s in surfaces:
        if s.scale_state != "percentile":
            raise ValueError(
                f"typology requires percentile surfaces, got {s.scale_state!r}"
            )
