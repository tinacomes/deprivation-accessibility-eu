"""The deprivation cost curves themselves — baseline, sweep, and pure access.

Everything else in `sensitivity/` reports the *consequences* of varying the
deprivation functions (Ginis move, ranks do not, the specification curve).
This module draws the functions being varied, which is what a reader needs
to judge whether the envelope is defensible:

* the everyday **DLF** (saturating logistic) and the emergency **DCF**
  (escalating Box-Cox), each with its Layer-1 curvature grid and its
  Layer-2 anchor-calibrated form swap, all built from the same
  `expand_variants` the harness sweeps — the picture cannot drift from the
  sweep;
* the calibration **anchors** drawn as points, so "form transferred,
  curvature calibrated" is visible rather than asserted (everyday: the
  15-minute-city inflection and the 45-min ceiling; emergency: the EMS
  response benchmarks — negligible below the 3-4 min ideal, the
  WHO-recommended 8 min, the 15-min upper-bound target);
* a **pure-access reference**: deprivation proportional to travel time,
  normalised at the same anchor. This is the implicit loss function of
  every "average minutes to the nearest X" accessibility measure. The gap
  between it and the calibrated curves is the entire methodological claim
  of the paper — near the anchor an extra minute is priced far more
  heavily by the DCF and far less by the saturated DLF than a minutes
  average can express.

Each panel uses the reporting convention of its own surface (§3), not a
common rescaling: the everyday DLF is drawn raw on its dimensionless
0-Lmax scale, the emergency DCF in multiples of g(15 min). The
pure-access line is drawn on whichever of those scales the panel uses, so
"what a minutes average would have said" is directly readable against the
calibrated curve. The two panels must not be compared to each other —
that is exactly the cross-regime magnitude comparison the standardisation
layer exists to forbid.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MAX_MINUTES = 60.0
EVERYDAY_ANCHORS = ((15.0, "15-min city\n(inflection / half-max)"),
                    (45.0, "45 min (ceiling)"))
# EMS response benchmarks (Pons et al. 2005; Vo et al. 2020; Khan et al.
# 2026): negligible below the 3-4 min ideal, WHO-recommended 8 min in dense
# urban cores, 10-15 min upper-bound target. NOT a half-max structure — see
# config/deprivation.yaml: convexity caps g(8)/g(15) at 0.427, so 8 min is
# an intermediate mark (~1/3), unlike the everyday DLF's 15-min half-max.
EMERGENCY_ANCHORS = ((4.0, "3-4 min\n(negligible)"),
                     (8.0, "8 min\n(WHO recommended)"),
                     (15.0, "15 min\n(upper target)"))
BASELINE_STYLE = {"color": "#1a1a1a", "lw": 2.6, "zorder": 5}
CURVATURE_STYLE = {"color": "#eb6834", "lw": 1.1, "alpha": 0.75, "zorder": 3}
FORMSWAP_STYLE = {"color": "#4a3aa7", "lw": 2.0, "ls": "--", "zorder": 4}
ACCESS_STYLE = {"color": "#2a78d6", "lw": 1.8, "ls": ":", "zorder": 4}


def _curve(spec: dict, t: np.ndarray, t_ref: float | None) -> np.ndarray:
    """g(t), divided by g(t_ref) when the regime reports on that anchor."""
    from depacc.deprivation.functions import DeprivationFunction

    fn = DeprivationFunction.from_spec({**spec, "reference_time_min": None})
    g = np.asarray(fn(t), dtype=float)
    if t_ref is None:
        return g
    g_ref = float(np.asarray(fn(np.asarray(float(t_ref))), dtype=float))
    return g / g_ref if g_ref > 0 else g


def plot_deprivation_curves(cfg: dict, grid: dict, out_path: Path,
                            max_minutes: float = MAX_MINUTES) -> Path:
    """Draw both regimes' curve families + the pure-access reference.

    ``grid`` is the sweep grid the harness runs (``config/sensitivity.yaml``
    → ``sensitivity``), passed in rather than read from ``cfg``: the grid is
    a separate file and the whole point of this figure is that it shows the
    variants that were actually swept.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from depacc.sensitivity.harness import expand_variants

    variants = expand_variants(cfg, grid or {})
    base = next(v for v in variants if v.layer == "baseline")
    t = np.linspace(0.0, float(max_minutes), 601)

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.9))
    panels = (
        # (regime, axis, title, anchors, y-label, reporting reference,
        #  access-line match point). The access line is matched at each
        #  panel's own anchor: the everyday DLF's 45-min ceiling, the
        #  emergency DCF's 15-min reporting anchor.
        ("everyday", axes[0], "everyday DLF — saturating (logistic)",
         EVERYDAY_ANCHORS, "deprivation (dimensionless, ceiling Lmax = 1)",
         None, 45.0),
        ("emergency", axes[1], "emergency DCF — escalating (Box-Cox)",
         EMERGENCY_ANCHORS, "deprivation, multiples of g(15 min)", 15.0,
         15.0),
    )
    for regime, ax, title, anchors, ylab, t_ref, anchor in panels:
        seen_curv = seen_swap = False
        for v in variants:
            spec = getattr(v, regime)
            if spec == getattr(base, regime) and v.layer != "baseline":
                continue                      # this variant moves the OTHER regime
            if v.layer == "curvature":
                ax.plot(t, _curve(spec, t, t_ref), **CURVATURE_STYLE,
                        label="Layer 1: curvature sweep" if not seen_curv else None)
                seen_curv = True
            elif v.layer == "form_swap":
                ax.plot(t, _curve(spec, t, t_ref), **FORMSWAP_STYLE,
                        label="Layer 2: form swap (anchors held)"
                        if not seen_swap else None)
                seen_swap = True
        base_curve = _curve(getattr(base, regime), t, t_ref)
        ax.plot(t, base_curve, **BASELINE_STYLE, label="baseline (published)")
        # Pure access: deprivation linear in minutes, matched to this panel's
        # own anchor so the two are readable against each other.
        ax.plot(t, (t / anchor) * float(_curve(getattr(base, regime),
                                               np.asarray(anchor), t_ref)),
                **ACCESS_STYLE, label="pure access (linear in minutes)")
        for at, label in anchors:
            y = float(_curve(getattr(base, regime), np.asarray(at), t_ref))
            ax.plot([at], [y], "o", color="#1a1a1a", ms=5.5, zorder=6)
            ax.annotate(label, (at, y), textcoords="offset points",
                        xytext=(8, -18), fontsize=7, color="0.35")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("travel time (minutes)")
        ax.set_ylabel(ylab)
        ax.set_xlim(0, max_minutes)
        ax.set_ylim(bottom=0)
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, lw=0.4, alpha=0.35)
        ax.set_axisbelow(True)

    fig.suptitle("Deprivation functions: what the robustness layers vary, "
                 "and what pure access assumes instead", fontsize=11)
    fig.text(0.01, -0.02,
             "each panel on its own reporting scale (everyday raw, emergency "
             "in multiples of g(15 min)) — do not compare panels · Layer 1 = "
             "curvature grid (config/sensitivity.yaml) · Layer 2 = form swap "
             "with the domain anchors held fixed (config/deprivation.yaml "
             "alternatives) · the access line is the loss function a minutes "
             "average implies, matched to the baseline at each panel's anchor",
             fontsize=6.5, color="0.45", ha="left", va="top")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path
