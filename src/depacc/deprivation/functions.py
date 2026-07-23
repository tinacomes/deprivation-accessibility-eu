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
    """

    form: str
    params: Mapping[str, float]
    kind: str = "DLF"
    source: str = ""
    zero_anchor: bool = True  # logistic only: rescale so g(0)=0

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

    @classmethod
    def from_spec(cls, spec: Mapping[str, object], context: str = "deprivation function") -> "DeprivationFunction":
        """Build from a config spec ({kind, form, params, source}); rejects
        null-placeholder parameters with the citation in the error message."""
        params = require_params(spec, context=context)
        return cls(
            form=str(spec.get("form")),
            params=params,
            kind=str(spec.get("kind", "DLF")),
            source=str(spec.get("source", "")),
            zero_anchor=bool(spec.get("zero_anchor", True)),
        )

    def __call__(self, t) -> np.ndarray:
        """Evaluate g(t); NaN in -> NaN out (unreachable propagates until the
        caller applies the configured unreachable policy)."""
        arr = np.asarray(t, dtype=float)
        if np.any((arr < 0) & ~np.isnan(arr)):
            raise ValueError("travel time must be non-negative")
        p = self.params
        if self.form == "logistic":
            return _logistic(arr, p["Lmax"], p["t0"], p["k"], self.zero_anchor)
        if self.form == "exponential":
            return _exponential(arr, p["beta"], p["scale"])
        return _box_cox(arr, p["lam"], p["scale"], p["shift"])
