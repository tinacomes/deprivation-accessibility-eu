"""Figure for Results 2.5 (deprivation vs access), drawn ONLY from the
paper-pack tables (no new statistics):

  panel A -- size elasticities of deprivation-based vs minutes-based
             outcomes with 95% CIs and R^2, from deprivation_vs_access.csv
  panel B -- the five emergency-desert capitals' ratio to the 67-city
             sample under an access average (median drive minutes) and
             under deprivation cost, from desert_access_contrast.csv

Output: figures/main/dep_vs_access.png. Rerun after any pack refresh.
"""
import csv
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PACK = pathlib.Path("../docs/paper-pack/data")
OUT = pathlib.Path("figures/main/dep_vs_access.png")

C_DEP = "#1f4e8c"   # deprivation outcomes (one saturated hue, fixed)
C_ACC = "#8a8a8a"   # minutes-based access outcomes (neutral)
C_REF = "#bbbbbb"   # reference lines
Z = 1.96            # 95% CI on the reported country-clustered SEs

# ---------------------------------------------------------------- panel A data
rows = [r for r in csv.DictReader(open(PACK / "deprivation_vs_access.csv"))
        if r["block"] == "size_elasticity"]
LABELS = {
    ("everyday", "mean_everyday"): "deprivation level (mean)",
    ("everyday", "everyday_median_time"): "median walk minutes",
    ("everyday", "everyday_mean_time"): "mean walk minutes",
    ("emergency", "mean_emergency"): "deprivation cost (mean)",
    ("emergency", "emergency_median_time"): "median drive minutes",
    ("emergency", "emergency_mean_time"): "mean drive minutes",
    ("emergency", "emergency_p90_time"): "p90 drive minutes",
}
ORDER = list(LABELS)
data = {(r["regime"], r["outcome"]): r for r in rows}

# ---------------------------------------------------------------- panel B data
deserts = list(csv.DictReader(open(PACK / "desert_access_contrast.csv")))
NAME = {"vilnius": "Vilnius", "ljubljana": "Ljubljana", "riga": "Rīga",
        "bucuresti": "București", "tallinn": "Tallinn"}

# -------------------------------------------------------------------- figure
plt.rcParams.update({
    "font.size": 9.5, "axes.titlesize": 10.5, "axes.spines.top": False,
    "axes.spines.right": False, "figure.dpi": 200,
})
fig, (ax, bx) = plt.subplots(
    1, 2, figsize=(11.2, 4.3), gridspec_kw={"width_ratios": [1.25, 1]})

# ---- panel A: forest plot of elasticities
ys = range(len(ORDER) - 1, -1, -1)
for y, key in zip(ys, ORDER):
    r = data[key]
    est, se, r2 = float(r["elasticity"]), float(r["se"]), float(r["r2"])
    is_dep = r["kind"] == "deprivation"
    c = C_DEP if is_dep else C_ACC
    ax.plot([est - Z * se, est + Z * se], [y, y], color=c, lw=2,
            solid_capstyle="round", zorder=2)
    ax.plot(est, y, "o", color=c, ms=7 if is_dep else 5.5, zorder=3)
    ax.text(0.135, y, f"$R^2$ = {r2:.2f}", va="center", ha="left",
            fontsize=8.5, color="#444444")
ax.axvline(0, color=C_REF, lw=1, zorder=1)
ax.set_yticks(list(ys))
ax.set_yticklabels([LABELS[k] for k in ORDER])
for tl, key in zip(ax.get_yticklabels(), ORDER):
    if data[key]["kind"] == "deprivation":
        tl.set_fontweight("bold")
        tl.set_color(C_DEP)
ax.text(-0.315, 6.55, "everyday regime (walk)", fontsize=9, style="italic",
        color="#444444")
ax.text(-0.315, 3.55, "emergency regime (car)", fontsize=9, style="italic",
        color="#444444")
ax.set_xlim(-0.36, 0.24)
ax.set_ylim(-0.6, 7.1)
ax.set_xlabel("size elasticity (log–log; 95% CI, country-clustered SE)")
ax.set_title("A    The claims survive in plain minutes;\n"
             "deprivation is the better-behaved outcome", loc="left")

# ---- panel B: desert dumbbells
yb = range(len(deserts) - 1, -1, -1)
for y, r in zip(yb, deserts):
    t = float(r["median_time_ratio_vs_sample"])
    d = float(r["deprivation_ratio_vs_sample"])
    bx.plot([t, d], [y, y], color="#cccccc", lw=1.5, zorder=1)
    bx.plot(t, y, "o", color=C_ACC, ms=7, zorder=2)
    bx.plot(d, y, "o", color=C_DEP, ms=8, zorder=3)
    bx.text(d + 0.13, y, f"{d:.1f}×", va="center", fontsize=8.5,
            color=C_DEP)
bx.axvline(1, color=C_REF, lw=1, ls="--", zorder=0)
bx.text(1, len(deserts) - 0.25, " sample\n parity", fontsize=8,
        color="#777777", va="top")
bx.set_yticks(list(yb))
bx.set_yticklabels([NAME[r["city"]] for r in deserts])
bx.set_xlim(0, 5.6)
bx.set_ylim(-1.6, len(deserts) - 0.4)
bx.set_xlabel("ratio to 67-city sample value")
bx.set_title("B    The emergency deserts are invisible\nto access averages",
             loc="left")
bx.plot([], [], "o", color=C_ACC, label="median drive minutes")
bx.plot([], [], "o", color=C_DEP, label="mean deprivation cost")
bx.legend(loc="lower right", frameon=False, fontsize=8.5)

fig.tight_layout(w_pad=2.5)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, bbox_inches="tight")
print("wrote", OUT)
