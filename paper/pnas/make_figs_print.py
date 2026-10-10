#!/usr/bin/env python3
"""Print-size figures for the PNAS-format version (paper/pnas/figures/).

Same data and the same scripts' logic as paper/make_fig_*.py, re-rendered at
PNAS column widths (8.7 cm single, 17.8 cm double) with 7-pt type, so that
nothing is scaled down after the fact. Reads only docs/paper-pack/data/,
config/ and paper/city_coords.csv. Also writes contact_sheet.png with the
five figures at true print size on one A4 page.

    cd paper/pnas && python3 make_figs_print.py
"""
import csv
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
PAPER = HERE.parent
ROOT = PAPER.parent
sys.path.insert(0, str(PAPER))
sys.path.insert(0, str(ROOT / "src"))
from _figstyle import (PACK, C_EV, C_EM, C_GRADE, M_REGION, GRADE_ORDER,  # noqa: E402
                       REGION_ORDER, C_REGION, cities)
from depacc.config import load_config  # noqa: E402
from depacc.sensitivity.harness import expand_variants  # noqa: E402
from depacc.viz.deprivation_curves import _curve, CUTOFF_MIN  # noqa: E402

CM = 1 / 2.54
COL, PAGE = 8.7 * CM, 17.8 * CM
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
C_DEP, C_ACC = "#1f4e8c", "#8a8a8a"

plt.rcParams.update({
    "font.size": 7, "axes.titlesize": 7.5, "axes.labelsize": 7,
    "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "legend.fontsize": 6,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "axes.linewidth": 0.6, "xtick.major.width": 0.5,
    "ytick.major.width": 0.5, "lines.linewidth": 1.2, "figure.dpi": 300,
    "savefig.dpi": 600, "font.family": "sans-serif",
})


def save(fig, name):
    out = FIG / name
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", out)


def grid(ax):
    ax.grid(True, lw=0.3, alpha=0.35)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- Fig 1
def fig_curves():
    cfg = load_config(config_dir=ROOT / "config")
    gridcfg = (yaml.safe_load(open(ROOT / "config/sensitivity.yaml")) or {}).get("sensitivity", {})
    variants = expand_variants(cfg, gridcfg)
    base = next(v for v in variants if v.layer == "baseline")
    SW = dict(color="0.75", lw=0.6, zorder=2)
    ACC = dict(color="0.25", lw=0.9, ls=":", zorder=4)
    fig, axes = plt.subplots(1, 3, figsize=(PAGE, 5.2 * CM), gridspec_kw={"wspace": 0.42})
    ax = axes[0]
    t = np.linspace(0, 60, 601)
    for v in variants:
        if v.everyday == base.everyday or v.layer == "baseline":
            continue
        if v.layer == "curvature":
            ax.plot(t, _curve(v.everyday, t, None), **SW)
        else:
            ax.plot(t, _curve(v.everyday, t, None), color="#4a3aa7", lw=0.9, ls="--", zorder=4)
    ax.plot(t, _curve(base.everyday, t, None), color=C_EV, lw=1.8, zorder=5)
    ax.plot(t, (t / 45) * float(_curve(base.everyday, np.asarray(45.0), None)), **ACC)
    y15 = float(_curve(base.everyday, np.asarray(15.0), None))
    ax.plot([15], [y15], "o", color="black", ms=2.8, zorder=6)
    ax.annotate("15-min city", (15, y15), textcoords="offset points", xytext=(4, -9), fontsize=6, color="0.3")
    ax.set_title("A  Everyday: a bounded level", loc="left")
    ax.set_xlabel("walking time (min)"); ax.set_ylabel("deprivation level (0–1)")
    ax.set_xlim(0, 60); ax.set_ylim(0, 1.3)
    em_sw = [v for v in variants if v.layer == "form_swap" and v.emergency != base.emergency]
    em_cv = [v for v in variants if v.layer == "curvature" and v.emergency != base.emergency]
    STY = {"exponential": dict(color="#4a3aa7", lw=0.9, ls="--", zorder=4),
           "survival": dict(color="#1c8a4c", lw=0.9, ls="-.", zorder=4)}
    ax = axes[1]
    tw = np.linspace(0, CUTOFF_MIN, 301)
    for v in em_cv:
        ax.plot(tw, _curve(v.emergency, tw, CUTOFF_MIN), **SW)
    for v in em_sw:
        k = "exponential" if "exponential" in v.name else "survival"
        ax.plot(tw, _curve(v.emergency, tw, CUTOFF_MIN), **STY[k])
    ax.plot(tw, _curve(base.emergency, tw, CUTOFF_MIN), color=C_EM, lw=1.8, zorder=5)
    ax.plot(tw, tw / CUTOFF_MIN, **ACC)
    for at, lab, off in ((4, "4 min", (3, -8)), (8, "8 min", (3, -8)), (15, "15 min", (-24, 3))):
        y = float(_curve(base.emergency, np.asarray(float(at)), CUTOFF_MIN))
        ax.plot([at], [y], "o", color="black", ms=2.8, zorder=6)
        ax.annotate(lab, (at, y), textcoords="offset points", xytext=off, fontsize=6, color="0.3")
    ax.set_title("B  Emergency: an escalating cost", loc="left")
    ax.set_xlabel("driving time (min)"); ax.set_ylabel("cost (× cost at 15 min)")
    ax.set_xlim(0, 15); ax.set_ylim(0, 1.05)
    ax = axes[2]
    tb = np.linspace(CUTOFF_MIN, 60, 301)
    for v in em_cv:
        ax.plot(tb, _curve(v.emergency, tb, CUTOFF_MIN), **SW)
    for v in em_sw:
        k = "exponential" if "exponential" in v.name else "survival"
        c = _curve(v.emergency, tb, CUTOFF_MIN)
        ax.plot(tb, c, **STY[k])
        ax.annotate(f"{c[-1]:.3g}×", (tb[-1], c[-1]), textcoords="offset points", xytext=(2, 0),
                    fontsize=6, color=STY[k]["color"], va="center")
    cb = _curve(base.emergency, tb, CUTOFF_MIN)
    ax.plot(tb, cb, color=C_EM, lw=1.8, zorder=5)
    ax.annotate(f"{cb[-1]:.3g}×", (tb[-1], cb[-1]), textcoords="offset points", xytext=(2, 0),
                fontsize=6, color=C_EM, va="center")
    ax.axhline(1, color="0.6", lw=0.5); ax.set_yscale("log")
    ax.set_title("C  Beyond the benchmark", loc="left")
    ax.set_xlabel("driving time (min)"); ax.set_ylabel("cost (log)")
    ax.set_xlim(15, 68)
    h = [Line2D([], [], color=C_EV, lw=1.8, label="everyday level"),
         Line2D([], [], color=C_EM, lw=1.8, label="emergency cost"),
         Line2D([], [], color="0.75", lw=0.6, label="curvature sweep"),
         Line2D([], [], color="#4a3aa7", lw=0.9, ls="--", label="form swap"),
         Line2D([], [], color="#1c8a4c", lw=0.9, ls="-.", label="survival swap"),
         Line2D([], [], color="0.25", lw=0.9, ls=":", label="linear loss (access)")]
    fig.legend(handles=h, loc="lower center", ncol=6, bbox_to_anchor=(0.5, -0.2), handlelength=1.8, columnspacing=1.2)
    for a in axes:
        grid(a)
    save(fig, "fig1_curves.png")


# ---------------------------------------------------------------- Fig 2
def fig_dep_vs_access():
    rows = [r for r in csv.DictReader(open(PACK / "deprivation_vs_access.csv")) if r["block"] == "size_elasticity"]
    LAB = {("everyday", "mean_everyday"): "deprivation level",
           ("everyday", "everyday_median_time"): "median walk min",
           ("everyday", "everyday_mean_time"): "mean walk min",
           ("emergency", "mean_emergency"): "deprivation cost",
           ("emergency", "emergency_median_time"): "median drive min",
           ("emergency", "emergency_mean_time"): "mean drive min",
           ("emergency", "emergency_p90_time"): "p90 drive min"}
    data = {(r["regime"], r["outcome"]): r for r in rows}
    deserts = list(csv.DictReader(open(PACK / "desert_access_contrast.csv")))
    NAME = {"vilnius": "Vilnius", "ljubljana": "Ljubljana", "riga": "Rīga", "bucuresti": "București", "tallinn": "Tallinn"}
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(PAGE, 5.4 * CM), gridspec_kw={"width_ratios": [1.2, 1], "wspace": 0.55})
    ys = list(range(len(LAB) - 1, -1, -1))
    for y, key in zip(ys, LAB):
        r = data[key]; est, se, r2 = float(r["elasticity"]), float(r["se"]), float(r["r2"])
        dep = r["kind"] == "deprivation"; c = C_DEP if dep else C_ACC
        ax.plot([est - 1.96 * se, est + 1.96 * se], [y, y], color=c, lw=1.4, solid_capstyle="round")
        ax.plot(est, y, "o", color=c, ms=4 if dep else 3)
        ax.text(0.13, y, f"$R^2$={r2:.2f}", va="center", fontsize=6, color="0.3")
    ax.axvline(0, color="0.75", lw=0.6)
    ax.set_yticks(ys); ax.set_yticklabels(list(LAB.values()))
    for tl, key in zip(ax.get_yticklabels(), LAB):
        if data[key]["kind"] == "deprivation":
            tl.set_fontweight("bold"); tl.set_color(C_DEP)
    ax.text(-0.33, 6.6, "everyday (walk)", fontsize=6, style="italic", color="0.3")
    ax.text(-0.33, 3.6, "emergency (car)", fontsize=6, style="italic", color="0.3")
    ax.set_xlim(-0.36, 0.26); ax.set_ylim(-0.6, 7.1)
    ax.set_xlabel("size elasticity (95% CI)")
    ax.set_title("A  Deprivation vs minutes: size elasticities", loc="left")
    yb = list(range(len(deserts) - 1, -1, -1))
    for y, r in zip(yb, deserts):
        t = float(r["median_time_ratio_vs_sample"]); d = float(r["deprivation_ratio_vs_sample"])
        bx.plot([t, d], [y, y], color="0.8", lw=1); bx.plot(t, y, "o", color=C_ACC, ms=3.5)
        bx.plot(d, y, "o", color=C_DEP, ms=4); bx.text(d + 0.12, y, f"{d:.1f}×", va="center", fontsize=6, color=C_DEP)
    bx.axvline(1, color="0.75", lw=0.6, ls="--")
    bx.set_yticks(yb); bx.set_yticklabels([NAME[r["city"]] for r in deserts])
    bx.set_xlim(0, 5.6); bx.set_ylim(-1.5, len(deserts) - 0.4)
    bx.set_xlabel("ratio to 67-city sample")
    bx.set_title("B  Five emergency deserts", loc="left")
    bx.plot([], [], "o", color=C_ACC, ms=3.5, label="median drive minutes")
    bx.plot([], [], "o", color=C_DEP, ms=4, label="mean deprivation cost")
    bx.legend(loc="lower right")
    grid(ax); grid(bx)
    save(fig, "fig2_dep_vs_access.png")


# ---------------------------------------------------------------- Fig 3
def fig_scaling():
    d = cities()
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(PAGE, 5.6 * CM), gridspec_kw={"wspace": 0.3})

    def fit(a, x, y, c):
        lx, ly = np.log(x), np.log(y); b, a0 = np.polyfit(lx, ly, 1)
        xs = np.linspace(lx.min(), lx.max(), 50); a.plot(np.exp(xs), np.exp(a0 + b * xs), color=c, lw=1.4, zorder=4)
    for col, c, m in (("mean_everyday", C_EV, "o"), ("mean_emergency", C_EM, "s")):
        ax.scatter(d.population, d[col], color=c, marker=m, s=9, alpha=0.85, zorder=3, lw=0)
        fit(ax, d.population, d[col], c)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("FUA population"); ax.set_ylabel("mean deprivation\n(level 0–1; cost × g(15))")
    ax.set_title("A  Mean deprivation vs size", loc="left")
    for col, c, m, lab in (("gini_everyday", C_EV, "o", "everyday"), ("gini_emergency", C_EM, "s", "emergency")):
        bx.scatter(d.population, d[col], color=c, marker=m, s=9, alpha=0.85, zorder=3, lw=0, label=lab)
        fit(bx, d.population, d[col], c)
    bx.set_xscale("log"); bx.set_yscale("log")
    bx.set_ylim(0.2, 0.9); bx.set_yticks([0.2, 0.3, 0.4, 0.6, 0.8]); bx.set_yticklabels(["0.2", "0.3", "0.4", "0.6", "0.8"]); bx.minorticks_off()
    bx.set_xlabel("FUA population"); bx.set_ylabel("within-city Gini")
    bx.set_title("B  Inequality vs size", loc="left")
    bx.legend(loc="lower right", handletextpad=0.3)
    grid(ax); grid(bx)
    save(fig, "fig3_scaling.png")


# ---------------------------------------------------------------- Fig 4
def fig_geography():
    import geopandas as gpd
    d = cities()
    env = pd.read_csv(PACK / "deprivation_sensitivity_summary.csv")
    env = env[env.axis == "curvature"]
    ev = env[env.target == "gini_everyday"].set_index("city"); em = env[env.target == "gini_emergency"].set_index("city")
    world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(PAGE, 7.6 * CM), gridspec_kw={"width_ratios": [1, 1.05], "wspace": 0.25})
    world.plot(ax=ax, color="#f0f0f0", edgecolor="white", lw=0.4)
    size = 5 + 14 * np.log10(d.population / 1e5)
    for g in GRADE_ORDER:
        for reg in REGION_ORDER:
            s = d[(d.coverage_grade == g) & (d.region == reg)]
            if s.empty:
                continue
            ax.scatter(s.lon, s.lat, s=size[s.index], marker=M_REGION[reg], color=C_GRADE[g],
                       edgecolor="white", lw=0.3, zorder=3 + GRADE_ORDER.index(g))
    for city, lab, off in (("bucuresti", "București", (4, -6)), ("vilnius", "Vilnius", (4, 1)),
                           ("tallinn", "Tallinn", (4, 1)), ("riga", "Rīga", (4, 0)), ("ljubljana", "Ljubljana", (-30, -8))):
        r = d.set_index("city").loc[city]
        ax.annotate(lab, (r.lon, r.lat), textcoords="offset points", xytext=off, fontsize=5.5, color="0.2")
    ax.set_xlim(-11, 31); ax.set_ylim(35, 66); ax.set_aspect(1 / np.cos(np.radians(52)))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    hg = [Line2D([], [], marker="o", ls="", color=C_GRADE[g], ms=4, label=f"{g} ({n})") for g, n in zip(GRADE_ORDER, (48, 14, 5))]
    hr = [Line2D([], [], marker=M_REGION[r], ls="", color="0.35", mfc="white", ms=4, label=r) for r in REGION_ORDER]
    ax.legend(handles=hg, loc="upper left", title="coverage grade (fill)", title_fontsize=6, handletextpad=0.2, borderpad=0.3)
    fig.legend(handles=hr, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.06), title="macro-region (marker)", title_fontsize=6, handletextpad=0.2, columnspacing=1.5)
    ax.set_title("A  Coverage grade by city", loc="left")
    dd = d.set_index("city")
    for city, r in dd.iterrows():
        if city in ev.index and city in em.index:
            bx.plot([ev.loc[city, "min"], ev.loc[city, "max"]], [r.gini_emergency] * 2, color="0.85", lw=0.5, zorder=1)
            bx.plot([r.gini_everyday] * 2, [em.loc[city, "min"], em.loc[city, "max"]], color="0.85", lw=0.5, zorder=1)
    for g in GRADE_ORDER:
        for reg in REGION_ORDER:
            s = dd[(dd.coverage_grade == g) & (dd.region == reg)]
            if s.empty:
                continue
            bx.scatter(s.gini_everyday, s.gini_emergency, marker=M_REGION[reg], s=16 if g != "covered" else 11,
                       color=C_GRADE[g], edgecolor="white", lw=0.3, zorder=3 + GRADE_ORDER.index(g))
    for city, lab in (("bucuresti", "București"), ("vilnius", "Vilnius"), ("tallinn", "Tallinn"), ("riga", "Rīga"), ("ljubljana", "Ljubljana")):
        r = dd.loc[city]; bx.annotate(lab, (r.gini_everyday, r.gini_emergency), textcoords="offset points", xytext=(3, 2), fontsize=5.5, color="0.25")
    bx.plot([0.2, 0.85], [0.2, 0.85], ls="--", color="0.75", lw=0.6, zorder=0)
    bx.set_xlim(0.2, 0.85); bx.set_ylim(0.2, 0.85)
    bx.set_xlabel("Gini of everyday deprivation level"); bx.set_ylabel("Gini of emergency deprivation cost")
    bx.set_title("B  Within-city inequality by grade", loc="left")
    grid(bx)
    save(fig, "fig4_geography.png")


# ---------------------------------------------------------------- Fig 5
def fig_vulnerability():
    v = pd.read_csv(PACK / "vulnerability.csv")
    v = v[v.level == "age_census"]
    reg = cities().set_index("city")["region"]
    v["region"] = v.city.map(reg)
    fig, axes = plt.subplots(2, 2, figsize=(COL, 8 * CM), sharex=True, gridspec_kw={"hspace": 0.35, "wspace": 0.45})
    panels = [("mean_dep_everyday_ratio_covered", "everyday deprivation ratio", 1.0),
              ("hh_share_gap_covered", "compounding (HH) share gap", 0.0)]
    for j, stratum in enumerate(("elderly_census", "children_census")):
        for i, (col, lab, ref) in enumerate(panels):
            ax = axes[i, j]
            s = v[v.stratum == stratum]
            for k, r in enumerate(REGION_ORDER):
                vals = s[s.region == r][col].dropna().values
                rng = np.random.default_rng(k)
                ax.scatter(k + rng.uniform(-0.22, 0.22, len(vals)), vals, s=6, color=C_REGION[r], alpha=0.8, lw=0, zorder=3)
                ax.plot([k - 0.35, k + 0.35], [np.median(vals)] * 2, color="black", lw=1.2, zorder=4)
            ax.axhline(ref, color="0.6", lw=0.5, ls="--")
            ax.set_xticks(range(4)); ax.set_xticklabels(REGION_ORDER, fontsize=6)
            if j == 0:
                ax.set_ylabel(lab, fontsize=6.5)
            if i == 0:
                ax.set_title({"elderly_census": "Elderly (65+)", "children_census": "Children (<15)"}[stratum], loc="left")
            grid(ax)
    save(fig, "fig5_vulnerability.png")


# ------------------------------------------------------------- contact sheet
def contact_sheet():
    from matplotlib.image import imread
    fig = plt.figure(figsize=(21.0 * CM, 29.7 * CM))
    items = [("fig1_curves.png", PAGE), ("fig2_dep_vs_access.png", PAGE), ("fig3_scaling.png", PAGE),
             ("fig4_geography.png", PAGE), ("fig5_vulnerability.png", COL)]
    y = 0.975; SC = 0.88
    for name, width in items:
        img = imread(FIG / name); h, w = img.shape[:2]
        wf = SC * width / (21.0 * CM); hf = wf * (h / w) * (21.0 / 29.7)
        ax = fig.add_axes([0.07, y - hf, wf, hf]); ax.imshow(img); ax.axis("off")
        fig.text(0.07, y + 0.004, name, fontsize=7, color="0.4")
        y -= hf + 0.018
    fig.text(0.07, 0.015, "Contact sheet at 88 % of print size on A4 (PNAS column 8.7 cm, page 17.8 cm).", fontsize=7, color="0.4")
    fig.savefig(FIG / "contact_sheet.png", dpi=150)
    fig.savefig(FIG / "contact_sheet.pdf")
    plt.close(fig); print("wrote contact sheet")


if __name__ == "__main__":
    fig_curves(); fig_dep_vs_access(); fig_scaling(); fig_geography(); fig_vulnerability(); contact_sheet()
