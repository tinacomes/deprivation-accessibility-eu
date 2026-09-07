#!/usr/bin/env python3
"""Fig.: the 67 cities in the inequality plane, fill = coverage grade,
marker = macro-region, whiskers = min-max envelope of each Gini over the
deprivation-curvature grid (deprivation_sensitivity_summary.csv).

Output: figures/main/cityplane.png
"""
import pandas as pd

from _figstyle import (PACK, C_GRADE, M_REGION, GRADE_ORDER, REGION_ORDER,
                       cities, style, save, grade_legend, region_legend)
import matplotlib.pyplot as plt  # noqa: E402

LABEL = {"bucuresti": "București", "vilnius": "Vilnius", "tallinn": "Tallinn",
         "riga": "Rīga", "ljubljana": "Ljubljana", "paris": "Paris",
         "madrid": "Madrid", "oslo": "Oslo", "stockholm": "Stockholm",
         "warszawa": "Warszawa", "sofia": "Sofia", "porto": "Porto",
         "caserta": "Caserta", "luxembourg": "Luxembourg"}


def main() -> None:
    style()
    d = cities().set_index("city")
    env = pd.read_csv(PACK / "deprivation_sensitivity_summary.csv")
    env = env[env["axis"] == "curvature"]
    ev = env[env.target == "gini_everyday"].set_index("city")
    em = env[env.target == "gini_emergency"].set_index("city")

    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    for city, r in d.iterrows():
        if city in ev.index and city in em.index:
            ax.plot([ev.loc[city, "min"], ev.loc[city, "max"]],
                    [r.gini_emergency] * 2, color="0.82", lw=0.9, zorder=1)
            ax.plot([r.gini_everyday] * 2,
                    [em.loc[city, "min"], em.loc[city, "max"]],
                    color="0.82", lw=0.9, zorder=1)
    for g in GRADE_ORDER:
        for reg in REGION_ORDER:
            s = d[(d.coverage_grade == g) & (d.region == reg)]
            if s.empty:
                continue
            ax.scatter(s.gini_everyday, s.gini_emergency, marker=M_REGION[reg],
                       s=58 if g != "covered" else 44, color=C_GRADE[g],
                       edgecolor="white", lw=0.6, zorder=3 + GRADE_ORDER.index(g))
    for city, lab in LABEL.items():
        r = d.loc[city]
        ax.annotate(lab, (r.gini_everyday, r.gini_emergency),
                    textcoords="offset points", xytext=(6, 4), fontsize=7.5,
                    color="0.25")
    lim = (0.2, 0.85)
    ax.plot(lim, lim, ls="--", color="0.75", lw=1, zorder=0)
    ax.set_xlim(*lim); ax.set_ylim(*lim)
    ax.set_xlabel("Gini of everyday deprivation level (within city)")
    ax.set_ylabel("Gini of emergency deprivation cost (within city)")
    ax.grid(True, lw=0.4, alpha=0.35); ax.set_axisbelow(True)
    l1 = grade_legend(ax, loc="lower right", title="coverage grade")
    ax.add_artist(l1)
    region_legend(ax, loc="upper left", title="macro-region")
    save(fig, "main/cityplane.png")


if __name__ == "__main__":
    main()
