#!/usr/bin/env python3
"""Fig. 3: what city size does to mean deprivation (A) and to within-city
inequality (B), per regime. Points from cities_descriptives.csv; slopes and
p-values annotated from inference_scaling_clustered.csv and
inference_regime_paired.csv (the fitted lines are the same OLS the pack
reports; only the annotated inference is country-clustered).

Output: figures/main/scaling_elasticity.png
"""
import numpy as np
import pandas as pd

from _figstyle import PACK, C_EV, C_EM, cities, style, save
import matplotlib.pyplot as plt  # noqa: E402


def fit_line(ax, x, y, color, log_y=True):
    lx = np.log(x)
    ly = np.log(y) if log_y else y
    b, a = np.polyfit(lx, ly, 1)
    xs = np.linspace(lx.min(), lx.max(), 50)
    ys = a + b * xs
    ax.plot(np.exp(xs), np.exp(ys) if log_y else ys, color=color, lw=2.2,
            zorder=4)
    return b


def main() -> None:
    style()
    d = cities()
    inf = pd.read_csv(PACK / "inference_scaling_clustered.csv").set_index("outcome")
    paired = pd.read_csv(PACK / "inference_regime_paired.csv").set_index("measure")

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11.2, 4.3))

    # A. means (log-log) ---------------------------------------------------
    for col, c, m, lab in (("mean_everyday", C_EV, "o", "everyday deprivation level"),
                           ("mean_emergency", C_EM, "s", "emergency deprivation cost")):
        ax.scatter(d["population"], d[col], color=c, marker=m, s=34,
                   alpha=0.85, zorder=3, label=lab, edgecolor="white", lw=0.5)
        fit_line(ax, d["population"], d[col], c)
    ax.set_xscale("log"); ax.set_yscale("log")
    e_ev, p_ev = inf.loc["mean_everyday", ["elasticity", "p_wild_cluster_bootstrap"]]
    e_em, p_em = inf.loc["mean_emergency", ["elasticity", "p_wild_cluster_bootstrap"]]
    ax.text(0.02, 0.05,
            f"everyday: elasticity {e_ev:+.2f}, p = {p_ev:.4f}\n"
            f"emergency: elasticity {e_em:+.2f}, p = {p_em:.2f}\n"
            f"difference {paired.loc['mean', 'gradient_difference_emergency']:+.2f}, "
            f"p = {paired.loc['mean', 'p_wild_cluster_bootstrap']:.3f}",
            transform=ax.transAxes, fontsize=8, va="bottom",
            bbox=dict(fc="white", ec="none", alpha=0.85))
    ax.set_xlabel("population of the functional urban area")
    ax.set_ylabel("mean deprivation\n(everyday: level 0–1; emergency: × cost at 15 min)")
    ax.set_title("A   Mean deprivation falls with size in the everyday regime only",
                 loc="left", fontsize=10)
    ax.legend(loc="upper right")

    # B. within-city inequality --------------------------------------------
    for col, c, m, lab in (("gini_everyday", C_EV, "o", "everyday"),
                           ("gini_emergency", C_EM, "s", "emergency")):
        bx.scatter(d["population"], d[col], color=c, marker=m, s=34,
                   alpha=0.85, zorder=3, label=lab, edgecolor="white", lw=0.5)
        fit_line(bx, d["population"], d[col], c, log_y=True)
    bx.set_xscale("log"); bx.set_yscale("log")
    g_ev, pg_ev = inf.loc["gini_everyday", ["elasticity", "p_wild_cluster_bootstrap"]]
    g_em, pg_em = inf.loc["gini_emergency", ["elasticity", "p_wild_cluster_bootstrap"]]
    bx.text(0.02, 0.05,
            f"everyday: elasticity {g_ev:+.3f}, p = {pg_ev:.4f}\n"
            f"emergency: elasticity {g_em:+.3f}, p = {pg_em:.2f}\n"
            f"difference {paired.loc['gini', 'gradient_difference_emergency']:+.3f}, "
            f"p = {paired.loc['gini', 'p_wild_cluster_bootstrap']:.3f}",
            transform=bx.transAxes, fontsize=8, va="bottom",
            bbox=dict(fc="white", ec="none", alpha=0.85))
    bx.set_xlabel("population of the functional urban area")
    bx.set_ylabel("within-city Gini of deprivation (log scale)")
    bx.set_ylim(0.2, 0.9)
    bx.set_yticks([0.2, 0.3, 0.4, 0.5, 0.6, 0.8])
    bx.set_yticklabels(["0.2", "0.3", "0.4", "0.5", "0.6", "0.8"])
    bx.minorticks_off()
    bx.set_title("B   Inequality rises with size in the everyday regime only",
                 loc="left", fontsize=10)
    bx.legend(loc="upper right")

    for a in (ax, bx):
        a.grid(True, lw=0.4, alpha=0.35); a.set_axisbelow(True)
    fig.tight_layout()
    save(fig, "main/scaling_elasticity.png")


if __name__ == "__main__":
    main()
