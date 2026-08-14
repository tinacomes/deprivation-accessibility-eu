"""Figure 1 (Musso et al. 1C grammar): the 67-city sample on a Europe map,
coloured by the everyday-emergency divergence gap, with a definition inset
(mini city plane), a distribution inset (KDE with median), and a size legend
— all anchored inside the map over ocean, so the layout is stable.

Usage:  python make_map.py <cityplane.csv> <city_coordinates.csv>
                           <clustered.csv> <ne_countries.geojson> <out.png>
"""

from __future__ import annotations

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PolyCollection
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

# Everyday wears blue and emergency wears orange throughout the paper, so
# the gap (gini_em - gini_ev) runs blue (everyday-side) -> neutral grey ->
# orange (emergency-side). Classic CVD-safe diverging pair, grey midpoint.
CMAP = LinearSegmentedColormap.from_list(
    "gap", ["#1d5eb0", "#7aa6dd", "#f2f1ef", "#f09a71", "#c94f16"])
LAND = "#eae8e4"
BORDER = "#ffffff"
SEA = "#f8f7f5"
INK, MUT = "#0b0b0b", "#6b6963"
BOX = dict(boxstyle="round,pad=0.35", fc="white", ec="#d0cec9", lw=0.8)

LON0, LON1, LAT0, LAT1 = -12.5, 34.0, 34.0, 64.5


def load_countries(path: str):
    polys = []
    for feat in json.load(open(path))["features"]:
        geom = feat["geometry"]
        rings = geom["coordinates"] if geom["type"] == "MultiPolygon" \
            else [geom["coordinates"]]
        for poly in rings:
            outer = np.asarray(poly[0], float)
            if outer[:, 0].max() < LON0 - 8 or outer[:, 0].min() > LON1 + 8:
                continue
            if outer[:, 1].max() < LAT0 - 8 or outer[:, 1].min() > LAT1 + 8:
                continue
            polys.append(outer)
    return polys


def _size(pop):
    return 16 + 60 * (np.log10(pop) - 5.0) / (7.2 - 5.0)


def main(plane_path, coords_path, clustered_path, ne_path, out_path):
    plane = pd.read_csv(plane_path)
    coords = pd.read_csv(coords_path)
    v = plane.merge(coords, on="city", how="left")
    missing = v[v.lat.isna()].city.tolist()
    if missing:
        raise SystemExit(f"no coordinates for: {missing}")
    clus = pd.read_csv(clustered_path)[["city", "cluster_kmeans"]]
    v = v.merge(clus, on="city", how="left")
    sizes = v.cluster_kmeans.value_counts()
    desert = (v.cluster_kmeans == sizes.idxmin()) if len(sizes) > 1 \
        else pd.Series(False, index=v.index)

    gap = v.divergence_gap.astype(float)
    lim = float(np.nanmax(np.abs(gap)))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)

    fig, ax = plt.subplots(figsize=(8.6, 8.0))
    fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.05)
    ax.set_facecolor(SEA)
    ax.add_collection(PolyCollection(load_countries(ne_path), facecolors=LAND,
                                     edgecolors=BORDER, linewidths=0.6,
                                     zorder=1))
    s = _size(v.population)
    sc = ax.scatter(v.lon, v.lat, c=gap, cmap=CMAP, norm=norm, s=s,
                    edgecolors="#55534e", linewidths=0.5, zorder=3)
    ax.scatter(v.lon[desert], v.lat[desert], facecolors="none",
               edgecolors=INK, s=s[desert] + 150, linewidths=1.3, zorder=4)
    for r in v[desert].itertuples():
        ax.annotate(r.name, (r.lon, r.lat), textcoords="offset points",
                    xytext=(8, 5), fontsize=8, color=INK, zorder=5)
    for city, dx, dy in (("paris", -6, -13), ("madrid", 6, -12),
                         ("oslo", 7, 2), ("napoli", 6, -11),
                         ("warszawa", 7, 3)):
        r = v[v.city == city].iloc[0]
        ax.annotate(r["name"], (r.lon, r.lat), textcoords="offset points",
                    xytext=(dx, dy), fontsize=7.5, color=MUT, zorder=5)

    ax.set_xlim(LON0, LON1)
    ax.set_ylim(LAT0, LAT1)
    ax.set_aspect(1.0 / np.cos(np.deg2rad(49.0)))
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#d8d6d1")

    # --- Colour bar: inside the map, over the central Mediterranean. ---
    cax = ax.inset_axes([0.33, 0.055, 0.30, 0.022])
    cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
    cb.set_label("divergence gap  (Gini$_{em}$ − Gini$_{ev}$)",
                 fontsize=8.5, color=INK, labelpad=2)
    cb.ax.tick_params(labelsize=7, colors=MUT)
    cb.outline.set_color("#c9c7c2")
    cax.text(-0.02, 1.5, "← everyday-side", fontsize=7, color="#1d5eb0",
             transform=cax.transAxes, ha="left")
    cax.text(1.02, 1.5, "emergency-side →", fontsize=7, color="#c94f16",
             transform=cax.transAxes, ha="right")

    # --- LEFT INSET (Atlantic, top-left): how the gap is defined. ---
    axd = ax.inset_axes([0.025, 0.66, 0.21, 0.24])
    axd.set_facecolor("white")
    axd.plot([0, 1], [0, 1], color="0.75", lw=1, ls="--")
    axd.scatter(v.gini_everyday, v.gini_emergency, s=4, c="#c9c7c2",
                linewidths=0)
    ex = v[v.city == "vilnius"].iloc[0]
    axd.scatter([ex.gini_everyday], [ex.gini_emergency], s=16, c="#c94f16",
                linewidths=0, zorder=3)
    axd.plot([ex.gini_everyday] * 2, [ex.gini_everyday, ex.gini_emergency],
             color=INK, lw=1.2, zorder=2)
    axd.annotate("gap", (ex.gini_everyday,
                         (ex.gini_everyday + ex.gini_emergency) / 2),
                 textcoords="offset points", xytext=(4, -3), fontsize=7.5,
                 color=INK)
    axd.set_xlim(0.2, 0.9)
    axd.set_ylim(0.2, 0.9)
    axd.set_xticks([])
    axd.set_yticks([])
    axd.set_xlabel("Gini everyday", fontsize=6.5, color=MUT, labelpad=1)
    axd.set_ylabel("Gini emergency", fontsize=6.5, color=MUT, labelpad=1)
    for sp in axd.spines.values():
        sp.set_color("#c9c7c2")
    axd.set_title("gap = distance above the\nequality diagonal", fontsize=7,
                  color=INK, pad=3)

    # --- RIGHT INSET (eastern Mediterranean corner): KDE of the gap. ---
    axk = ax.inset_axes([0.76, 0.045, 0.215, 0.15])
    axk.set_facecolor("white")
    from scipy.stats import gaussian_kde

    xs = np.linspace(-lim * 1.1, lim * 1.1, 240)
    kde = gaussian_kde(gap.dropna())(xs)
    axk.fill_between(xs, kde, color="#dedcd7", lw=0)
    axk.plot(xs, kde, color="#8a8880", lw=1)
    axk.axvline(float(gap.median()), color=INK, lw=1, ls=":")
    axk.axvline(0, color="#b9b7b2", lw=0.8)
    axk.set_yticks([])
    axk.set_xticks([-0.2, 0, 0.2])
    axk.tick_params(labelsize=6.5, colors=MUT, pad=1)
    for sp in axk.spines.values():
        sp.set_color("#c9c7c2")
    axk.set_title("density (dotted = median)", fontsize=7, color=INK, pad=3)

    # --- Size legend (Atlantic, mid-left), boxed. ---
    axl = ax.inset_axes([0.025, 0.42, 0.14, 0.20])
    axl.set_facecolor("white")
    axl.set_xticks([])
    axl.set_yticks([])
    for sp in axl.spines.values():
        sp.set_color("#c9c7c2")
    for i, (p, lbl) in enumerate([(2e5, "0.2 M"), (1e6, "1 M"),
                                  (8e6, "8 M")]):
        axl.scatter([0.22], [0.76 - i * 0.27], s=_size(p), c="#d5d3ce",
                    edgecolors="#55534e", linewidths=0.5)
        axl.text(0.45, 0.76 - i * 0.27, lbl, fontsize=7, color=MUT,
                 va="center")
    axl.set_title("population", fontsize=7, color=INK, pad=2)
    axl.set_xlim(0, 1)
    axl.set_ylim(0, 1)

    ax.scatter([], [], facecolors="none", edgecolors=INK, s=110,
               linewidths=1.3, label="emergency-desert group")
    ax.legend(frameon=False, fontsize=8, loc="upper right")

    ax.set_title("The 67-city sample: emergency-side vs everyday-side "
                 "inequality", fontsize=11.5, pad=8)
    ax.text(0.01, -0.025,
            f"{len(v)} FUAs, 24 countries · colour = divergence gap · circle "
            f"area = population · ring = emergency-desert group · r5/OSM · "
            f"cross-sectional space-for-time",
            transform=ax.transAxes, fontsize=6.5, color=MUT)
    fig.savefig(out_path, dpi=220, facecolor="white")
    print("written", out_path)


if __name__ == "__main__":
    main(*sys.argv[1:6])
