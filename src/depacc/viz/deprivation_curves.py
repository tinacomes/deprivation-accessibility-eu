"""The deprivation curves themselves — baseline, sweep, and pure access.

Everything else in `sensitivity/` reports the *consequences* of varying the
deprivation functions (Ginis move, ranks do not, the specification curve).
This module draws the functions being varied, which is what a reader needs
to judge whether the envelope is defensible. Three panels:

* **everyday DLF** (saturating logistic): a deprivation *level* on [0, 1] —
  1 IS full deprivation — with its Layer-1 curvature grid and Layer-2
  concave Box-Cox swap;
* **emergency DCF, benchmark window (0-15 min, linear)**: every curve
  normalised to its own value at the 15-min upper target, so the EMS
  anchors (negligible at the 3-4 min ideal, ~1/3 of threshold cost at the
  contested 8-min urban standard, 1.0 at the 15-min cut-off) are visible
  and the anchor discipline is visible too — all Layer-2 forms coincide
  through the window BY CONSTRUCTION;
* **emergency DCF, beyond the cut-off (15-60 min, log scale)**: the region
  no benchmark constrains, where the three escalation hypotheses part
  ways — saturating (survival-based bounded curve, → 1.6× the benchmark
  cost), polynomial (Box-Cox, the baseline, ~11× at 60 min), exponential
  (Holguín-Veras line, ~120×). This divergence is exactly the
  conditionality of the emergency-Gini result (methods §7a).

A **pure-access reference** (deprivation proportional to minutes,
normalised at each panel's anchor) is drawn in the first two panels: it is
the implicit loss function of every "average minutes to the nearest X"
measure, and the gap between it and the calibrated curves is the paper's
methodological claim.

UNITS. The two regimes are different objects and the labels say so: the
everyday surface is a deprivation LEVEL (bounded, 1 = full deprivation);
the emergency surface is a deprivation COST reported in multiples of the
15-min benchmark cost g(15) — unbounded by design, so "3.4" means 3.4×
the cost of arriving at the EMS upper target, not a level on any 0-1
scale. The bounded survival-based swap is the exception that probes this
choice: it saturates at 1 = full deprivation. Panels must not be compared
to each other — that is the cross-regime magnitude comparison the
standardisation layer exists to forbid (methods §3).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MAX_MINUTES = 60.0
CUTOFF_MIN = 15.0
EVERYDAY_ANCHORS = ((15.0, "15-min city\n(inflection / half-max)"),
                    (45.0, "45 min (ceiling)"))
# EMS response benchmarks (Pons et al. 2005; Vo et al. 2020; Khan et al.
# 2026): negligible below the 3-4 min ideal, widely used 8-min urban response
# standard (contested: Pons 2005 vs Blanchard 2012), 10-15 min upper-bound
# target. NOT a half-max structure — see config/deprivation.yaml: convexity
# caps g(8)/g(15) at 0.427, so 8 min is an intermediate mark (~1/3), unlike
# the everyday DLF's 15-min half-max.
EMERGENCY_ANCHORS = ((4.0, "3-4 min\n(negligible)"),
                     (8.0, "8 min\n(response standard,\ncontested)"),
                     (15.0, "15 min\n(upper target)"))
BASELINE_STYLE = {"color": "#1a1a1a", "lw": 2.6, "zorder": 5}
CURVATURE_STYLE = {"color": "#eb6834", "lw": 1.1, "alpha": 0.75, "zorder": 3}
FORMSWAP_STYLE = {"color": "#4a3aa7", "lw": 2.0, "ls": "--", "zorder": 4}
SURVIVAL_STYLE = {"color": "#1c8a4c", "lw": 2.0, "ls": "-.", "zorder": 4}
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


def _emergency_style(variant_name: str) -> tuple[dict, str]:
    """Style + short label for an emergency Layer-2 swap, keyed on the
    variant name so the two escalation hypotheses are distinguishable."""
    if "survival" in variant_name:
        return SURVIVAL_STYLE, "saturating (survival-based, 1 = full)"
    return FORMSWAP_STYLE, "exponential (Holguín-Veras line)"


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

    fig, axes = plt.subplots(1, 3, figsize=(15.6, 4.9))

    # ---- panel 1: everyday DLF (a LEVEL on [0, 1]) -------------------------
    ax = axes[0]
    t = np.linspace(0.0, float(max_minutes), 601)
    seen_curv = seen_swap = False
    for v in variants:
        spec = v.everyday
        if spec == base.everyday and v.layer != "baseline":
            continue                          # this variant moves emergency
        if v.layer == "curvature":
            ax.plot(t, _curve(spec, t, None), **CURVATURE_STYLE,
                    label="Layer 1: curvature sweep" if not seen_curv else None)
            seen_curv = True
        elif v.layer == "form_swap":
            ax.plot(t, _curve(spec, t, None), **FORMSWAP_STYLE,
                    label="Layer 2: form swap (anchors held)"
                    if not seen_swap else None)
            seen_swap = True
    ax.plot(t, _curve(base.everyday, t, None), **BASELINE_STYLE,
            label="baseline (published)")
    ax.plot(t, (t / 45.0) * float(_curve(base.everyday, np.asarray(45.0), None)),
            **ACCESS_STYLE, label="pure access (linear in minutes)")
    for at, label in EVERYDAY_ANCHORS:
        y = float(_curve(base.everyday, np.asarray(at), None))
        ax.plot([at], [y], "o", color="#1a1a1a", ms=5.5, zorder=6)
        ax.annotate(label, (at, y), textcoords="offset points",
                    xytext=(8, -18), fontsize=7, color="0.35")
    ax.set_title("everyday DLF — a LEVEL, saturating\n(1 = full deprivation)",
                 fontsize=10)
    ax.set_ylabel("deprivation level (0–1)")
    ax.set_xlim(0, max_minutes)
    ax.set_ylim(bottom=0)

    # ---- panels 2+3: emergency DCF (a COST, × the 15-min benchmark) -------
    em_swaps = [v for v in variants
                if v.layer == "form_swap" and v.emergency != base.emergency]
    em_curv = [v for v in variants
               if v.layer == "curvature" and v.emergency != base.emergency]

    # panel 2 — the benchmark window: everything the anchors pin down.
    ax = axes[1]
    tw = np.linspace(0.0, CUTOFF_MIN, 301)
    seen_curv = False
    for v in em_curv:
        ax.plot(tw, _curve(v.emergency, tw, CUTOFF_MIN), **CURVATURE_STYLE,
                label="Layer 1: curvature sweep" if not seen_curv else None)
        seen_curv = True
    for v in em_swaps:
        style, label = _emergency_style(v.name)
        ax.plot(tw, _curve(v.emergency, tw, CUTOFF_MIN), **style, label=label)
    ax.plot(tw, _curve(base.emergency, tw, CUTOFF_MIN), **BASELINE_STYLE,
            label="baseline: Box-Cox λ=1.8 (published)")
    ax.plot(tw, tw / CUTOFF_MIN, **ACCESS_STYLE,
            label="pure access (linear in minutes)")
    for at, label in EMERGENCY_ANCHORS:
        y = float(_curve(base.emergency, np.asarray(at), CUTOFF_MIN))
        ax.plot([at], [y], "o", color="#1a1a1a", ms=5.5, zorder=6)
        ax.annotate(label, (at, y), textcoords="offset points",
                    xytext=(6, -4) if at < 12 else (-58, -22), fontsize=7,
                    color="0.35")
    ax.set_title("emergency DCF, benchmark window —\nall forms coincide at "
                 "the anchors (by construction)", fontsize=10)
    ax.set_ylabel("deprivation cost (× 15-min benchmark cost g(15))")
    ax.set_xlim(0, CUTOFF_MIN)
    ax.set_ylim(0, 1.05)

    # panel 3 — beyond the cut-off: no benchmark exists, the escalation
    # hypotheses part ways. Log scale so all three stay readable.
    ax = axes[2]
    tb = np.linspace(CUTOFF_MIN, float(max_minutes), 301)
    for v in em_curv:
        ax.plot(tb, _curve(v.emergency, tb, CUTOFF_MIN), **CURVATURE_STYLE)
    for v in em_swaps:
        style, _ = _emergency_style(v.name)
        curve = _curve(v.emergency, tb, CUTOFF_MIN)
        ax.plot(tb, curve, **style)
        ax.annotate(f"{curve[-1]:.3g}×", (tb[-1], curve[-1]),
                    textcoords="offset points", xytext=(3, 0), fontsize=7.5,
                    color=style["color"], va="center")
    base_b = _curve(base.emergency, tb, CUTOFF_MIN)
    ax.plot(tb, base_b, **BASELINE_STYLE)
    ax.annotate(f"{base_b[-1]:.3g}×", (tb[-1], base_b[-1]),
                textcoords="offset points", xytext=(3, 0), fontsize=7.5,
                color=BASELINE_STYLE["color"], va="center")
    ax.axhline(1.0, color="0.6", lw=0.8, ls="-")
    ax.annotate("cost at the 15-min target", (CUTOFF_MIN + 2, 1.0),
                textcoords="offset points", xytext=(0, 5), fontsize=7,
                color="0.45")
    ax.set_yscale("log")
    ax.set_title("beyond the cut-off — NO benchmark exists;\nthe escalation "
                 "hypotheses diverge (log scale)", fontsize=10)
    ax.set_ylabel("deprivation cost (× g(15), log scale)")
    ax.set_xlim(CUTOFF_MIN, max_minutes)

    for ax in axes:
        ax.set_xlabel("travel time (minutes)")
        if ax is not axes[2]:  # panel 3 curves are labelled directly
            ax.legend(frameon=False, fontsize=7.5, loc="upper left")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, lw=0.4, alpha=0.35)
        ax.set_axisbelow(True)

    fig.suptitle("Deprivation level (everyday) vs deprivation cost "
                 "(emergency): what the robustness layers vary, and what "
                 "pure access assumes instead", fontsize=11)
    fig.text(0.01, -0.02,
             "everyday = bounded LEVEL (1 = full deprivation); emergency = "
             "COST in multiples of the 15-min benchmark cost g(15) — "
             "different objects, do not compare panels (methods §3) · "
             "Layer 1 = curvature grid · Layer 2 = form swap with the EMS "
             "anchors held fixed (saturating survival-based swap bounded at "
             "1 = full deprivation) · the access line is the loss function "
             "a minutes average implies · beyond 15 min no EMS benchmark "
             "exists — the emergency-Gini size result is conditional on the "
             "escalation form (methods §7a)",
             fontsize=6.5, color="0.45", ha="left", va="top")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path
