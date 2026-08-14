"""Methods overview figure: (A) from places to travel times, (B) from
minutes to deprivation — the two anchored functions, (C) from surfaces to
the co-location typology and city indicators.

Usage: python make_methods_fig.py <out.png>
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK, MUT = "#0b0b0b", "#6b6963"
EV, EM = "#2a78d6", "#c94f16"
# Typology class colours (match the published compounding maps).
C_LL, C_HL, C_LH, C_HH = "#e8c46b", "#5bc8c0", "#d95fa4", "#31379c"


def _box(ax, x, y, w, h, text, fc="#f4f3f1", ec="#c9c7c2", fs=8,
         color=INK, lw=0.9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                fc=fc, ec=ec, lw=lw, mutation_scale=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=color, linespacing=1.35)


def _arrow(ax, x0, y0, x1, y1, color="#8a8880"):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                                 mutation_scale=11, lw=1.1, color=color))


def panel_a(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _box(ax, 0.06, 0.80, 0.40, 0.14, "population grid\n100 m (GHS-POP)")
    _box(ax, 0.54, 0.80, 0.40, 0.14, "facilities\n(OSM, benchmarked)")
    _box(ax, 0.22, 0.56, 0.56, 0.13,
         "street routing (r5)\nwalk · everyday    car · emergency", fs=8)
    _arrow(ax, 0.26, 0.80, 0.42, 0.69)
    _arrow(ax, 0.74, 0.80, 0.58, 0.69)
    _box(ax, 0.03, 0.22, 0.45, 0.24,
         "EVERYDAY\nGP · pharmacy · supermarket\nschool · green space\n"
         "substitutable → soft-min over\noptions × 2SFCA congestion",
         fc="#e9f0fa", ec=EV, fs=7.2, color=INK)
    _box(ax, 0.52, 0.22, 0.45, 0.24,
         "EMERGENCY\nED hospital · ambulance\n\nnon-substitutable →\n"
         "nearest facility only",
         fc="#faeee7", ec=EM, fs=7.2, color=INK)
    _arrow(ax, 0.38, 0.56, 0.26, 0.47, color=EV)
    _arrow(ax, 0.62, 0.56, 0.74, 0.47, color=EM)
    ax.text(0.255, 0.13, "effective time  $t_{eff}$ (min)", ha="center",
            fontsize=8, color=EV)
    ax.text(0.745, 0.13, "nearest time  $t$ (min)", ha="center",
            fontsize=8, color=EM)
    _arrow(ax, 0.255, 0.215, 0.255, 0.165, color=EV)
    _arrow(ax, 0.745, 0.215, 0.745, 0.165, color=EM)
    ax.set_title("A   From places to travel times", loc="left", fontsize=10,
                 color=INK)


def panel_b(ax):
    ax.axis("off")
    ax.set_title("B   From minutes to deprivation (anchored functions)",
                 loc="left", fontsize=10, color=INK)
    # Everyday DLF: zero-anchored logistic, t0 = 15, k = 0.2.
    axl = ax.inset_axes([0.06, 0.20, 0.40, 0.60])
    t = np.linspace(0, 45, 200)
    sig = 1 / (1 + np.exp(-0.2 * (t - 15.0)))
    s0 = 1 / (1 + np.exp(-0.2 * (0 - 15.0)))
    g = (sig - s0) / (1 - s0)
    axl.plot(t, g, color=EV, lw=2)
    axl.axvline(15, color="0.8", lw=0.9, ls="--")
    axl.annotate("15-min-city\ninflection", (15, 0.5),
                 textcoords="offset points", xytext=(6, -14), fontsize=6.8,
                 color=MUT)
    axl.set_xlabel("effective time (min)", fontsize=7, color=MUT, labelpad=1)
    axl.set_ylabel("deprivation (0–1)", fontsize=7, color=MUT, labelpad=1)
    axl.set_title("everyday DLF\nbounded, S-shaped", fontsize=7.5, color=EV)
    # Emergency DCF: Box-Cox lambda = 1.8, anchored g(45) = 1.
    axr = ax.inset_axes([0.58, 0.20, 0.40, 0.60])
    t2 = np.linspace(0, 75, 200)
    lam = 1.8
    g2 = ((t2 + 1) ** lam - 1) / lam
    g2 = g2 / (((45 + 1) ** lam - 1) / lam)
    axr.plot(t2, g2, color=EM, lw=2)
    for a in (45, 60):
        axr.axvline(a, color="0.8", lw=0.9, ls="--")
    axr.axhline(1.0, color="0.85", lw=0.8)
    axr.annotate("clinical anchors\n45 / 60 min\ng(60)/g(45) ≈ 1.66",
                 (45, 0.22), textcoords="offset points", xytext=(-64, 0),
                 fontsize=6.8, color=MUT)
    axr.set_xlabel("nearest time (min)", fontsize=7, color=MUT, labelpad=1)
    axr.set_ylabel("deprivation (× g(45))", fontsize=7, color=MUT, labelpad=1)
    axr.set_title("emergency DCF\nconvex, unbounded", fontsize=7.5, color=EM)
    for a in (axl, axr):
        a.tick_params(labelsize=6.5, colors=MUT)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            a.spines[sp].set_color("#c9c7c2")
    ax.text(0.5, -0.005,
            "forms transferred from literature; curvature calibrated to the "
            "anchors;\nper-service deprivations composited by weighted mean",
            ha="center", fontsize=7, color=MUT, transform=ax.transAxes)


def panel_c(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("C   From surfaces to co-location and city indicators",
                 loc="left", fontsize=10, color=INK)
    # Typology quadrant on population-weighted percentiles.
    q = ax.inset_axes([0.04, 0.16, 0.44, 0.62])
    for (x0, y0, c, lbl, tc) in [(0, 0, C_LL, "LL\nlow both", INK),
                                 (0.5, 0, C_HL, "HL\neveryday\nonly", INK),
                                 (0, 0.5, C_LH, "LH\nemergency\nonly", "white"),
                                 (0.5, 0.5, C_HH, "HH\ncompounding", "white")]:
        q.add_patch(plt.Rectangle((x0, y0), 0.5, 0.5, fc=c, ec="white",
                                  lw=2))
        q.text(x0 + 0.25, y0 + 0.25, lbl, ha="center", va="center",
               fontsize=7.2, color=tc, linespacing=1.3)
    q.set_xlim(0, 1)
    q.set_ylim(0, 1)
    q.set_xticks([0.5])
    q.set_xticklabels(["median split"], fontsize=6.5, color=MUT)
    q.set_yticks([0.5])
    q.set_yticklabels(["median\nsplit"], fontsize=6.5, color=MUT)
    q.set_xlabel("everyday percentile (pop-weighted)", fontsize=7,
                 color=MUT, labelpad=2)
    q.set_ylabel("emergency percentile", fontsize=7, color=MUT, labelpad=2)
    for sp in q.spines.values():
        sp.set_color("#c9c7c2")
    # Outputs list.
    _box(ax, 0.54, 0.50, 0.43, 0.28,
         "per city\nGini$_{ev}$, Gini$_{em}$, gap\ncoupling ρ · HH share\n"
         "compounding intensity", fs=7.4)
    _box(ax, 0.54, 0.16, 0.43, 0.26,
         "across 67 cities\nsize scaling (space-for-time)\nregional tests · "
         "clustering\nvulnerability strata", fs=7.4)
    _arrow(ax, 0.50, 0.55, 0.54, 0.60)
    _arrow(ax, 0.755, 0.50, 0.755, 0.44)
    ax.text(0.26, 0.055, "ranks never mix raw magnitudes across regimes",
            ha="center", fontsize=6.8, color=MUT)


def main(out_path):
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.3))
    fig.subplots_adjust(left=0.015, right=0.985, top=0.88, bottom=0.04,
                        wspace=0.10)
    panel_a(axes[0])
    panel_b(axes[1])
    panel_c(axes[2])
    fig.suptitle("Measuring two-regime potential deprivation",
                 fontsize=12, y=0.985)
    fig.savefig(out_path, dpi=220, facecolor="white")
    print("written", out_path)


if __name__ == "__main__":
    main(sys.argv[1])
