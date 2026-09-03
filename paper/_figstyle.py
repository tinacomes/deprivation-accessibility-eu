"""Shared style and data helpers for the paper figures (paper/make_fig_*.py).

Every script reads only docs/paper-pack/data/ (plus config/ for the
deprivation functions) and never re-derives a statistic: the pack tables are
the source of every number drawn.
"""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACK = ROOT / "docs/paper-pack/data"
FIG = pathlib.Path(__file__).resolve().parent / "figures"

# regimes
C_EV = "#2a78d6"     # everyday (blue)
C_EM = "#eb6834"     # emergency (orange)
# coverage grades (fill)
C_GRADE = {"covered": "#8c8c8c", "partial desert": "#eb6834",
           "desert": "#4a3aa7"}
GRADE_ORDER = ["covered", "partial desert", "desert"]
# macro-regions (marker shape)
M_REGION = {"North": "o", "West": "s", "South": "^", "CEE": "D"}
REGION_ORDER = ["North", "West", "South", "CEE"]
C_REGION = {"North": "#2a78d6", "West": "#eb6834", "South": "#2bb673",
            "CEE": "#4a3aa7"}

RC = {
    "font.size": 9.5, "axes.titlesize": 10.5, "axes.labelsize": 9.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "legend.frameon": False, "legend.fontsize": 8.5,
}


def style() -> None:
    plt.rcParams.update(RC)


def cities() -> pd.DataFrame:
    """cities_descriptives + coverage grade (from the two clustering passes)
    + coordinates."""
    d = pd.read_csv(PACK / "cities_descriptives.csv")
    main = pd.read_csv(PACK / "cityvector_clustered.csv")
    peeled = pd.read_csv(PACK / "cityvector_clustered_peeled.csv")
    grade = pd.Series("covered", index=d["city"], dtype=object)
    small = peeled["cluster_kmeans"].value_counts().idxmin()
    grade[peeled.loc[peeled["cluster_kmeans"] == small, "city"]] = "partial desert"
    small = main["cluster_kmeans"].value_counts().idxmin()
    grade[main.loc[main["cluster_kmeans"] == small, "city"]] = "desert"
    d["coverage_grade"] = d["city"].map(grade)
    coords = pd.read_csv(pathlib.Path(__file__).resolve().parent
                         / "city_coords.csv")
    return d.merge(coords, on="city", how="left")


def grade_legend(ax, loc="lower right", title=None, **kw):
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker="o", ls="", color=C_GRADE[g], ms=7,
                      label=f"{g} (n={n})")
               for g, n in zip(GRADE_ORDER, (48, 14, 5))]
    return ax.legend(handles=handles, loc=loc, title=title, **kw)


def region_legend(ax, loc="lower right", title=None, **kw):
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker=M_REGION[r], ls="", color="0.35",
                      mfc="white", ms=7, label=r) for r in REGION_ORDER]
    return ax.legend(handles=handles, loc=loc, title=title, **kw)


def save(fig, name: str) -> pathlib.Path:
    out = FIG / name
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)
    return out
