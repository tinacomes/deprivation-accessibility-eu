"""Deprivation functions g(t): increasing functions of travel time.

The deprivation function is the impedance function of a gravity model run in
the opposite direction: instead of a decreasing impedance f(t) discounting
opportunities, an increasing g(t) prices the burden of the (effective) travel
time itself. g is evaluated at an effective time (soft-min of congestion-
inflated times for the everyday regime; nearest-facility time for the
emergency regime), never bolted onto a decreasing-impedance gravity score.

The two regimes use deliberately different shapes:

  * EVERYDAY deprivation SATURATES — everyday services are substitutable and
    non-critical, so beyond some threshold the (relative) deprivation tops out
    at a ceiling. Modelled with a bounded logistic S-curve.
  * EMERGENCY deprivation ESCALATES without bound — it is time-critical, so
    the cost rises ever more steeply. Modelled with a convex form (Box-Cox or
    exponential).

Forms (t in minutes; parameters from config/deprivation.yaml — nulls are
rejected by depacc.config.require_params):

    logistic    : g(t) = Lmax / (1 + exp(-k * (t - t0)))         k > 0
                  monotone increasing, saturating at Lmax; inflection at t0.
                  (Not globally convex — convex below t0, concave above.)
    exponential : g(t) = scale * (exp(beta * t) - 1)             beta > 0
    box_cox     : g(t) = scale * ((t + shift)**lam - shift**lam)/lam,  lam > 0

box_cox is convex for lam > 1 and concave for lam < 1; its curvature is
therefore kind-specific. An escalating DCF (emergency) must be convex, so
lam > 1 is enforced for kind="DCF". A saturating DLF (everyday) uses the
concave branch (lam < 1) — the diminishing-returns, form-swapped counterpart
of the logistic — so kind="DLF" allows any lam > 0. exponential is always
convex (beta > 0). exponential and convex box_cox satisfy g(0)=0, g'>0,
g''>=0; the concave box_cox is increasing with g(0)=0 but g''<0. The raw
logistic has a small positive baseline g(0)=Lmax/(1+exp(k*t0)); with
``zero_anchor`` (default True) it is rescaled to
g(t) = Lmax*(L(t)-L(0))/(Lmax-L(0)) so g(0)=0 and g(inf)=Lmax exactly,
removing that baseline artifact. (It washes out under the standardisation
layer anyway, but the anchored surface is cleaner.)

REPORTING SCALE. The saturating DLF lands in [0, Lmax] by construction, but the
escalating DCF is unbounded and its `scale` is a free relative constant, so with
scale=1 the emergency surface is on an arbitrary scale (Box-Cox lam=1.8,
shift=1 gives g(45) ≈ 545, so a city's mean emergency deprivation reads ~15.8 —
a number with no interpretation, and one that silently invites comparison with
the everyday 0-1 surface). ``reference_time_min`` fixes that by dividing g by
g(t_ref) for a configured domain anchor (the ~45-min clinical time-to-care
threshold for the DCF), so 1.0 means "the deprivation of arriving at the
threshold" and >1 means "worse than it". It is division by a positive constant:
percentiles, the typology, Ginis, the concentration index, ρ and every ranking
are EXACTLY unchanged — only reported levels become interpretable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from depacc.config import ConfigError, require_params

FORMS = ("logistic", "exponential", "box_cox")

# Required parameter names per form.
_REQUIRED = {
    "logistic": ("Lmax", "t0", "k"),
    "exponential": ("beta", "scale"),
    "box_cox": ("lam", "scale", "shift"),
}


def _logistic(t: np.ndarray, Lmax: float, t0: float, k: float,
              zero_anchor: bool = True) -> np.ndarray:
    raw = Lmax / (1.0 + np.exp(-k * (t - t0)))
    if not zero_anchor:
        return raw
    l0 = Lmax / (1.0 + np.exp(k * t0))  # = raw at t=0
    return Lmax * (raw - l0) / (Lmax - l0)


def _exponential(t: np.ndarray, beta: float, scale: float) -> np.ndarray:
    return scale * np.expm1(beta * t)


def _box_cox(t: np.ndarray, lam: float, scale: float, shift: float) -> np.ndarray:
    return scale * ((t + shift) ** lam - shift**lam) / lam


@dataclass(frozen=True)
class DeprivationFunction:
    """A configured deprivation function, callable on scalars or arrays.

    ``kind`` distinguishes the dimensionless Deprivation Level Function
    ("DLF", everyday framing) from the monetary Deprivation Cost Function
    ("DCF", emergency framing); it labels units of the output surface only.

    ``reference_time_min`` divides g by g(t_ref), putting the surface in units
    of "multiples of the deprivation at t_ref minutes". This is the reporting
    anchor for the UNBOUNDED escalating DCF: with scale = 1 the raw Box-Cox
    values run into the hundreds (g(45) ≈ 545), which makes the reported
    absolute levels — the city row's ``mean_emergency`` and the vulnerability
    table's ``mean_dep_emergency`` — unreadable and invites the cross-regime
    magnitude comparison the standardisation layer exists to forbid. Because it
    is division by a positive CONSTANT, every rank- or ratio-based output is
    unchanged exactly: percentiles, the typology, Spearman ρ, Jaccard, the
    Ginis, the concentration index and the p90/p50 ratio are all invariant
    (regression-tested). It changes reported LEVELS only, and it does not bound
    the function: escalation past t_ref shows up as values > 1.
    """

    form: str
    params: Mapping[str, float]
    kind: str = "DLF"
    source: str = ""
    zero_anchor: bool = True  # logistic only: rescale so g(0)=0
    reference_time_min: float | None = None  # report in units of g(t_ref)

    def __post_init__(self) -> None:
        if self.form not in FORMS:
            raise ConfigError(f"Unknown deprivation form '{self.form}'; known: {FORMS}")
        p = self.params
        missing = set(_REQUIRED[self.form]) - set(p)
        if missing:
            raise ConfigError(f"{self.form} form missing params {sorted(missing)}")
        if self.form == "logistic":
            if p["k"] <= 0:
                raise ConfigError("logistic form requires k > 0 (increasing in time)")
            if p["Lmax"] <= 0:
                raise ConfigError("logistic form requires Lmax > 0 (saturation ceiling)")
            if p["t0"] < 0:
                raise ConfigError("logistic form requires t0 >= 0")
        elif self.form == "exponential":
            if p["beta"] <= 0:
                raise ConfigError("exponential form requires beta > 0 (increasing, convex)")
            if p["scale"] <= 0:
                raise ConfigError("deprivation scale must be > 0")
        else:  # box_cox
            if p["lam"] <= 0:
                raise ConfigError("box_cox form requires lam > 0")
            if p["shift"] < 0:
                raise ConfigError("box_cox form requires shift >= 0")
            if p["scale"] <= 0:
                raise ConfigError("deprivation scale must be > 0")
            # Convexity is kind-specific: an escalating DCF (emergency) must be
            # convex (lam > 1); a saturating DLF (everyday) uses the concave
            # branch (lam < 1) — the diminishing-returns counterpart of the
            # logistic, calibrated to the same 15/45-min anchors.
            if self.kind == "DCF" and p["lam"] <= 1:
                raise ConfigError(
                    "box_cox DCF (escalating emergency cost) requires lam > 1 "
                    "for convexity in time")
        if self.reference_time_min is not None:
            t_ref = float(self.reference_time_min)
            if t_ref <= 0:
                raise ConfigError(
                    "reference_time_min must be > 0 (it is the anchor time "
                    "whose deprivation is reported as 1.0)")
            g_ref = float(self._raw(np.asarray(t_ref)))
            if not np.isfinite(g_ref) or g_ref <= 0:
                raise ConfigError(
                    f"reference_time_min={t_ref} gives a non-positive "
                    f"g(t_ref); pick an anchor inside the function's range")

    @classmethod
    def from_spec(cls, spec: Mapping[str, object], context: str = "deprivation function") -> "DeprivationFunction":
        """Build from a config spec ({kind, form, params, source}); rejects
        null-placeholder parameters with the citation in the error message."""
        params = require_params(spec, context=context)
        ref = spec.get("reference_time_min")
        return cls(
            form=str(spec.get("form")),
            params=params,
            kind=str(spec.get("kind", "DLF")),
            source=str(spec.get("source", "")),
            zero_anchor=bool(spec.get("zero_anchor", True)),
            reference_time_min=None if ref is None else float(ref),
        )

    def _raw(self, arr: np.ndarray) -> np.ndarray:
        p = self.params
        if self.form == "logistic":
            return _logistic(arr, p["Lmax"], p["t0"], p["k"], self.zero_anchor)
        if self.form == "exponential":
            return _exponential(arr, p["beta"], p["scale"])
        return _box_cox(arr, p["lam"], p["scale"], p["shift"])

    @property
    def units(self) -> str:
        """Human-readable units of the output surface, carried into the equity
        outputs so a reported level is never unitless-by-accident."""
        if self.reference_time_min is not None:
            return (f"{self.kind}: multiples of g({self.reference_time_min:g} min) "
                    f"[anchored]")
        if self.form == "logistic":
            return f"{self.kind}: fraction of the saturation ceiling Lmax"
        return f"{self.kind}: relative units (unbounded, scale={self.params['scale']:g})"

    def __call__(self, t) -> np.ndarray:
        """Evaluate g(t); NaN in -> NaN out (unreachable propagates until the
        caller applies the configured unreachable policy)."""
        arr = np.asarray(t, dtype=float)
        if np.any((arr < 0) & ~np.isnan(arr)):
            raise ValueError("travel time must be non-negative")
        out = self._raw(arr)
        if self.reference_time_min is None:
            return out
        return out / self._raw(np.asarray(float(self.reference_time_min)))
