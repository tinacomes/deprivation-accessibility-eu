#!/usr/bin/env python3
"""Fig.: regional structure of four indicators, each city drawn as its
country code so that the country clustering inside a region is visible;
bar = regional median, band = interquartile range. Test results in the
caption come from inference_regional.csv and regional_dispersion.csv.

Output: figures/main/region_strips.png
"""
import numpy as np
import pandas as pd

from _figstyle import PACK, C_REGION, REGION_ORDER, cities, style, save
import matplotlib.pyplot as plt  # noqa: E402

PANELS = [("spearman_rho", "coupling ρ of the two surfaces"),
          ("gini_everyday", "Gini of everyday deprivation level"),
          ("gini_emergency", "Gini of emergency deprivation cost"),
          ("divergence_gap", "divergence gap (emergency − everyday Gini)")]


def main() -> None:
    style()
    d = cities()
    inf = pd.read_csv(PACK / "inference_regional.csv").set_index("outcome")
    disp = pd.read_csv(PACK / "regional_dispersion.csv").set_index("indicator")
    fig, axes = plt.subplots(1, 4, figsize=(12.4, 4.0))
    for ax, (col, title) in zip(axes, PANELS):
        for i, reg in enumerate(REGION_ORDER):
            s = d[d.region == reg].copy()
            # countries spread left-to-right by their median, cities stacked
            order = s.groupby("country")[col].median().sort_values().index
            xpos = {c: i + (k - (len(order) - 1) / 2) * (0.7 / max(len(order) - 1, 1))
                    for k, c in enumerate(order)}
            for _, r in s.iterrows():
                ax.text(xpos[r.country], r[col], r.country, ha="center",
                        va="center", fontsize=6.5, color=C_REGION[reg],
                        fontweight="bold", zorder=3)
            q1, med, q3 = np.percentile(s[col], [25, 50, 75])
            ax.add_patch(plt.Rectangle((i - 0.42, q1), 0.84, q3 - q1,
                                       color=C_REGION[reg], alpha=0.10, lw=0,
                                       zorder=1))
            ax.plot([i - 0.42, i + 0.42], [med, med], color="black", lw=1.6,
                    zorder=2)
        pm = inf.loc[col, "p_permutation_countries"]
        pd_ = disp.loc[col, "p_permutation_countries"]
        ax.set_title(f"{title}\nmedian p = {pm:.3f}; dispersion p = {pd_:.3f}",
                     fontsize=9)
        ax.set_xticks(range(4)); ax.set_xticklabels(REGION_ORDER)
        ax.set_xlim(-0.6, 3.6)
        lo, hi = d[col].min(), d[col].max()
        ax.set_ylim(lo - 0.06 * (hi - lo), hi + 0.06 * (hi - lo))
        if col == "divergence_gap":
            ax.axhline(0, color="0.6", lw=0.8, ls="--")
        ax.grid(True, axis="y", lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, "main/region_strips.png")


if __name__ == "__main__":
    main()
