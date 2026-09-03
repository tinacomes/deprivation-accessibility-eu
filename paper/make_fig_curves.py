#!/usr/bin/env python3
"""Fig. 1: the two deprivation functions and the linear loss an access
average implies. Drawn from config/ (the functions actually swept by the
harness, via depacc.sensitivity.harness.expand_variants), with no in-image
title or footer: the caption lives in main.tex.

Output: figures/main/deprivation_curves.png
"""
import sys

import numpy as np
import yaml

from _figstyle import ROOT, C_EV, C_EM, style, save

sys.path.insert(0, str(ROOT / "src"))
from depacc.config import load_config  # noqa: E402
from depacc.sensitivity.harness import expand_variants  # noqa: E402
from depacc.viz.deprivation_curves import _curve, CUTOFF_MIN  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

MAX_MIN = 60.0
SWEEP = {"color": "0.72", "lw": 0.9, "zorder": 2}
BASE_EV = {"color": C_EV, "lw": 2.6, "zorder": 5}
BASE_EM = {"color": C_EM, "lw": 2.6, "zorder": 5}
ACCESS = {"color": "0.25", "lw": 1.6, "ls": ":", "zorder": 4}
SWAP = {"exponential": {"color": "#4a3aa7", "lw": 1.6, "ls": "--", "zorder": 4},
        "survival": {"color": "#1c8a4c", "lw": 1.6, "ls": "-.", "zorder": 4},
        "box_cox": {"color": "#4a3aa7", "lw": 1.6, "ls": "--", "zorder": 4}}


def main() -> None:
    style()
    cfg = load_config(config_dir=ROOT / "config")
    grid = (yaml.safe_load(open(ROOT / "config/sensitivity.yaml")) or {}
            ).get("sensitivity", {})
    variants = expand_variants(cfg, grid)
    base = next(v for v in variants if v.layer == "baseline")

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6),
                             gridspec_kw={"wspace": 0.32})

    # A. everyday level -----------------------------------------------------
    ax = axes[0]
    t = np.linspace(0, MAX_MIN, 601)
    for v in variants:
        if v.everyday == base.everyday or v.layer == "baseline":
            continue
        if v.layer == "curvature":
            ax.plot(t, _curve(v.everyday, t, None), **SWEEP)
        else:
            ax.plot(t, _curve(v.everyday, t, None), **SWAP["box_cox"],
                    label="form swap (concave)")
    ax.plot(t, _curve(base.everyday, t, None), **BASE_EV,
            label="everyday deprivation level")
    ax.plot(t, (t / 45.0) * float(_curve(base.everyday, np.asarray(45.0), None)),
            **ACCESS, label="linear loss (access average)")
    ax.plot([], [], **SWEEP, label="curvature sweep")
    y15 = float(_curve(base.everyday, np.asarray(15.0), None))
    ax.plot([15], [y15], "o", color="black", ms=4.5, zorder=6)
    ax.annotate("15-minute city", (15, y15), textcoords="offset points",
                xytext=(7, -12), fontsize=7.5, color="0.3")
    ax.set_title("A   Everyday services: a bounded level", loc="left")
    ax.set_xlabel("walking time to services (minutes)")
    ax.set_ylabel("deprivation level (0–1)")
    ax.set_xlim(0, MAX_MIN); ax.set_ylim(0, 1.35)
    ax.legend(loc="upper left", fontsize=7.5)

    # B. emergency cost within the benchmark window --------------------------
    em_swaps = [v for v in variants
                if v.layer == "form_swap" and v.emergency != base.emergency]
    em_curv = [v for v in variants
               if v.layer == "curvature" and v.emergency != base.emergency]
    ax = axes[1]
    tw = np.linspace(0, CUTOFF_MIN, 301)
    for v in em_curv:
        ax.plot(tw, _curve(v.emergency, tw, CUTOFF_MIN), **SWEEP)
    for v in em_swaps:
        key = "exponential" if "exponential" in v.name else "survival"
        ax.plot(tw, _curve(v.emergency, tw, CUTOFF_MIN), **SWAP[key],
                label=f"form swap ({key})")
    ax.plot(tw, _curve(base.emergency, tw, CUTOFF_MIN), **BASE_EM,
            label="emergency deprivation cost")
    ax.plot(tw, tw / CUTOFF_MIN, **ACCESS, label="linear loss (access average)")
    for at, lab, off in ((4, "4 min", (5, -9)), (8, "8 min", (5, -9)),
                         (15, "15 min", (-34, 4))):
        y = float(_curve(base.emergency, np.asarray(float(at)), CUTOFF_MIN))
        ax.plot([at], [y], "o", color="black", ms=4.5, zorder=6)
        ax.annotate(lab, (at, y), textcoords="offset points", xytext=off,
                    fontsize=7.5, color="0.3")
    ax.set_title("B   Emergency care: an escalating cost", loc="left")
    ax.set_xlabel("driving time to emergency care (minutes)")
    ax.set_ylabel("deprivation cost (× cost at 15 min)")
    ax.set_xlim(0, CUTOFF_MIN); ax.set_ylim(0, 1.05)
    ax.legend(loc="upper left", fontsize=7.5)

    # C. beyond the benchmark ----------------------------------------------
    ax = axes[2]
    tb = np.linspace(CUTOFF_MIN, MAX_MIN, 301)
    for v in em_curv:
        ax.plot(tb, _curve(v.emergency, tb, CUTOFF_MIN), **SWEEP)
    for v in em_swaps:
        key = "exponential" if "exponential" in v.name else "survival"
        c = _curve(v.emergency, tb, CUTOFF_MIN)
        ax.plot(tb, c, **SWAP[key])
        ax.annotate(f"{c[-1]:.3g}×", (tb[-1], c[-1]), textcoords="offset points",
                    xytext=(3, 0), fontsize=7.5, color=SWAP[key]["color"],
                    va="center")
    cb = _curve(base.emergency, tb, CUTOFF_MIN)
    ax.plot(tb, cb, **BASE_EM)
    ax.annotate(f"{cb[-1]:.3g}×", (tb[-1], cb[-1]), textcoords="offset points",
                xytext=(3, 0), fontsize=7.5, color=C_EM, va="center")
    ax.axhline(1.0, color="0.6", lw=0.8)
    ax.set_yscale("log")
    ax.set_title("C   Beyond the benchmark: three hypotheses", loc="left")
    ax.set_xlabel("driving time to emergency care (minutes)")
    ax.set_ylabel("deprivation cost (× cost at 15 min, log)")
    ax.set_xlim(CUTOFF_MIN, MAX_MIN + 6)

    for ax in axes:
        ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    save(fig, "main/deprivation_curves.png")


if __name__ == "__main__":
    main()
