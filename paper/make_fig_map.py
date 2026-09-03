#!/usr/bin/env python3
"""Fig.: where the 67 cities are, coloured by emergency-coverage grade,
marker by macro-region, sized by population. Base map: Natural Earth
low-resolution countries bundled with geopandas 0.14; city points from
city_coords.csv (city-centre coordinates).

Output: figures/main/city_map.png
"""
import numpy as np
import geopandas as gpd

from _figstyle import (C_GRADE, M_REGION, GRADE_ORDER, REGION_ORDER,
                       cities, style, save, grade_legend, region_legend)
import matplotlib.pyplot as plt  # noqa: E402

LABEL = {"bucuresti": "București", "vilnius": "Vilnius", "tallinn": "Tallinn",
         "riga": "Rīga", "ljubljana": "Ljubljana"}


def main() -> None:
    style()
    d = cities()
    world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    fig, ax = plt.subplots(figsize=(7.6, 7.2))
    world.plot(ax=ax, color="#f1f1f1", edgecolor="white", lw=0.6)
    size = 18 + 60 * np.log10(d["population"] / 1e5)
    for g in GRADE_ORDER:
        for reg in REGION_ORDER:
            s = d[(d.coverage_grade == g) & (d.region == reg)]
            if s.empty:
                continue
            ax.scatter(s.lon, s.lat, s=size[s.index], marker=M_REGION[reg],
                       color=C_GRADE[g], edgecolor="white", lw=0.6,
                       zorder=3 + GRADE_ORDER.index(g), alpha=0.95)
    for city, lab in LABEL.items():
        r = d.set_index("city").loc[city]
        ax.annotate(lab, (r.lon, r.lat), textcoords="offset points",
                    xytext=(7, 3), fontsize=8, color="0.2")
    ax.set_xlim(-11, 31); ax.set_ylim(35, 66)
    ax.set_aspect(1 / np.cos(np.radians(52)))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    l1 = grade_legend(ax, loc="upper left", title="emergency-coverage grade")
    ax.add_artist(l1)
    region_legend(ax, loc="lower right", title="macro-region (marker)")
    save(fig, "main/city_map.png")


if __name__ == "__main__":
    main()
