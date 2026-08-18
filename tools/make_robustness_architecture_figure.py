"""Build the robustness-architecture overview figure (contribution claim 5).

One figure, four panels, each one pillar of the architecture the paper
offers as a template — drawn only from the audited tables in
``docs/paper-pack/data/`` so every mark traces to a citable file:

  A  rank agreement vs baseline across every deprivation variant
     (rank_agreement.csv) — ranks are near-invariant, with the two
     emergency escalation swaps shown as the scoped, named exceptions;
  B  median level-envelope widths per sweep axis
     (deprivation_sensitivity_summary.csv) — levels move by design,
     and the threshold dominates every functional-form knob;
  C  every size-elasticity headline re-estimated in plain minutes
     (deprivation_vs_access.csv) — the claims survive dropping the
     deprivation layer, which is what makes it a layer and not a result;
  D  per-cell flip shares vs city-level HH-share envelopes
     (flip_cells.csv, typology_share_envelope.csv) — cells are fragile,
     city summaries are not, with the engine cross-check quoted alongside.

Output: docs/paper-pack/figures/robustness_architecture.png
Style follows the pack conventions (recessive axes, orange = everyday,
purple = emergency, curvature #2a78d6 / form swap #eb6834 as in the
specification curve).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "paper-pack" / "data"
FIGDIR = ROOT / "docs" / "paper-pack" / "figures"

EVERYDAY = "darkorange"
EMERGENCY = "purple"
GAP = "0.45"
CURVATURE = "#2a78d6"
FORM_SWAP = "#eb6834"
THRESHOLD = "#3b4994"

TARGET_COLOUR = {"gini_everyday": EVERYDAY, "gini_emergency": EMERGENCY,
                 "divergence_gap": GAP}
TARGET_LABEL = {"gini_everyday": "Gini everyday",
                "gini_emergency": "Gini emergency",
                "divergence_gap": "divergence gap"}


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, linewidth=0.4, alpha=0.35)
    ax.set_axisbelow(True)


def _variant_label(v: str) -> str:
    if v.startswith("everyday_k"):
        k, t0 = v.removeprefix("everyday_k").split("_t0")
        return f"everyday k={k}, t0={int(t0)}"
    if v.startswith("emergency_lam"):
        return f"emergency λ={v.removeprefix('emergency_lam')}"
    return {"formswap_everyday_box_cox": "everyday form swap (Box-Cox)",
            "formswap_emergency_survival": "emergency escalation (bounded survival)",
            "formswap_emergency_exponential": "emergency escalation (exponential)",
            }.get(v, v)


def panel_rank_agreement(ax):
    """A: Spearman ρ vs baseline per variant × target."""
    ra = pd.read_csv(DATA / "rank_agreement.csv")
    swaps = ["formswap_everyday_box_cox", "formswap_emergency_survival",
             "formswap_emergency_exponential"]
    curvature = sorted(v for v in ra.variant.unique() if v not in swaps)
    order = curvature + swaps
    ypos = {v: len(order) - 1 - i for i, v in enumerate(order)}

    ax.axvspan(0.90, 1.005, color="0.92", zorder=0)
    ax.axvline(0.90, color="0.6", lw=0.8, ls=":", zorder=1)
    for _, r in ra.iterrows():
        ax.scatter(r.spearman_rho, ypos[r.variant],
                   color=TARGET_COLOUR[r.target], s=26, zorder=3,
                   alpha=0.9, linewidths=0)
    # Scoped exceptions: the emergency escalation swaps reorder the
    # emergency-Gini ranking because each changes what the Gini measures.
    exc = ra[(ra.variant.isin(swaps[1:])) & (ra.target == "gini_emergency")]
    for _, r in exc.iterrows():
        ax.scatter(r.spearman_rho, ypos[r.variant], facecolors="none",
                   edgecolors="#0b0b0b", s=110, linewidths=1.1, zorder=4)
    ax.annotate("scoped exceptions:\nescalation swaps change\nwhat the Gini measures",
                xy=(float(exc.spearman_rho.mean()), ypos[swaps[2]] + 0.5),
                xytext=(0.42, ypos[swaps[1]] + 3.6), fontsize=7, color="0.25",
                arrowprops=dict(arrowstyle="-", color="0.55", lw=0.8))

    ax.set_yticks([ypos[v] for v in order],
                  [_variant_label(v) for v in order], fontsize=6.5)
    ax.set_xlim(0.1, 1.02)
    ax.set_ylim(-0.7, len(order) - 0.3)
    ax.set_xlabel("Spearman ρ of city ranking vs baseline (67 cities)",
                  fontsize=8)
    handles = [plt.Line2D([], [], color=TARGET_COLOUR[t], marker="o", ls="",
                          markersize=5, label=TARGET_LABEL[t])
               for t in TARGET_COLOUR]
    ax.legend(handles=handles, frameon=False, fontsize=7, loc="upper left")
    ax.set_title("A  City rankings are near-invariant to the deprivation\n"
                 "parameterisation (shaded: ρ ≥ 0.90)", fontsize=9, loc="left")
    _style(ax)


def panel_envelopes(ax):
    """B: median level-envelope width per sweep axis × target."""
    s = pd.read_csv(DATA / "deprivation_sensitivity_summary.csv")
    med = s.groupby(["axis", "target"])["width"].median()
    rows = [  # (label, axis colour, [(target label, value)])
        ("curvature grid\n(Layer 1)", CURVATURE,
         [("Gini everyday", med["curvature", "gini_everyday"]),
          ("Gini emergency", med["curvature", "gini_emergency"]),
          ("HH share", med["curvature", "share_HH"])]),
        ("form swaps\n(Layer 2)", FORM_SWAP,
         [("Gini everyday", med["form_swap", "gini_everyday"]),
          ("Gini emergency", med["form_swap", "gini_emergency"]),
          ("HH share", med["form_swap", "share_HH"])]),
        ('"how high is high"\nthreshold', THRESHOLD,
         [("HH share", med["threshold", "share_HH"])]),
    ]
    ys, labels, group_centres = [], [], []
    y = 0.0
    for group_label, colour, bars in rows:
        y0 = y
        for lab, val in bars:
            ax.barh(y, val, height=0.72, color=colour,
                    alpha=0.85 if lab != "HH share" else 1.0, linewidth=0)
            ax.text(val + 0.008, y, f"{val:.3f}", va="center", fontsize=7,
                    color="0.2")
            ys.append(y)
            labels.append(lab)
            y -= 1.0
        group_centres.append(((y0 + y + 1.0) / 2, group_label))
        y -= 0.7
    ax.set_yticks(ys, labels, fontsize=7)
    for gy, glab in group_centres:
        ax.text(-0.30, gy, glab, ha="center", va="center", fontsize=7.5,
                transform=ax.get_yaxis_transform())
    ax.set_xlabel("median min–max envelope width across the 67 cities",
                  fontsize=8)
    ax.set_xlim(0, 0.78)
    thr = med["threshold", "share_HH"]
    curv = med["curvature", "share_HH"]
    ax.text(0.98, 0.97,
            f"threshold moves the HH share {thr / curv:.0f}× more than\n"
            "curvature — class shares always travel\n"
            "with a threshold sweep",
            transform=ax.transAxes, ha="right", va="top", fontsize=7,
            color="0.25")
    ax.set_title("B  Levels move, by design — the calibration carries\n"
                 "information, so slope claims ride the specification curve",
                 fontsize=9, loc="left")
    _style(ax)
    ax.grid(True, axis="x", linewidth=0.4, alpha=0.35)
    ax.grid(False, axis="y")


def panel_access_reestimation(ax):
    """C: size elasticities, deprivation vs plain-minutes re-estimation."""
    d = pd.read_csv(DATA / "deprivation_vs_access.csv")
    el = d[d.block == "size_elasticity"].copy()
    order = ["mean_everyday", "everyday_median_time", "everyday_mean_time",
             "mean_emergency", "emergency_median_time", "emergency_mean_time",
             "emergency_p90_time"]
    label = {"mean_everyday": "deprivation level",
             "everyday_median_time": "median walk time",
             "everyday_mean_time": "mean walk time",
             "mean_emergency": "deprivation cost",
             "emergency_median_time": "median drive time",
             "emergency_mean_time": "mean drive time",
             "emergency_p90_time": "p90 drive time"}
    el = el.set_index("outcome").loc[order].reset_index()
    x = np.arange(len(el), dtype=float)
    x[el.regime == "emergency"] += 0.6  # gap between the regime groups
    ax.axhline(0, color="0.75", lw=1, ls="--", zorder=1)
    for xi, (_, r) in zip(x, el.iterrows()):
        colour = EVERYDAY if r.regime == "everyday" else EMERGENCY
        t95 = stats.t.ppf(0.975, r.n_cities - 2)
        ax.vlines(xi, r.elasticity - t95 * r.se, r.elasticity + t95 * r.se,
                  color=colour, lw=1.4, zorder=2)
        if r.kind == "deprivation":
            ax.scatter(xi, r.elasticity, color=colour, s=42, zorder=3)
            ax.scatter(xi, r.elasticity, facecolors="none",
                       edgecolors="#0b0b0b", s=130, linewidths=1.1, zorder=4)
        else:
            ax.scatter(xi, r.elasticity, facecolors="white",
                       edgecolors=colour, s=42, linewidths=1.3, zorder=3)
    ax.set_xticks(x, [label[o] for o in el.outcome], rotation=35,
                  ha="right", fontsize=7)
    ax.set_ylabel("size elasticity (per log population)", fontsize=8)
    r2 = el.set_index("outcome").r2
    gini = d[d.block == "gini_correlation"].set_index("regime").elasticity
    ax.text(0.02, 0.05,
            "everyday gradient and emergency non-gradient both survive in\n"
            f"plain minutes; deprivation is the better-behaved outcome\n"
            f"(R² {r2['mean_everyday']:.2f} vs {r2['everyday_median_time']:.2f}); "
            f"Gini corr. r = {gini['everyday']:.3f} / {gini['emergency']:.3f}",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=7,
            color="0.25")
    handles = [
        plt.Line2D([], [], color="0.3", marker="o", ls="", markersize=6,
                   markeredgecolor="#0b0b0b", label="deprivation (ringed)"),
        plt.Line2D([], [], color="0.3", marker="o", ls="", markersize=6,
                   markerfacecolor="white", label="plain travel time"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=7, loc="upper right")
    ax.set_title("C  Every size headline re-estimated on plain minutes —\n"
                 "no headline depends on the deprivation functions",
                 fontsize=9, loc="left")
    _style(ax)


def panel_cells_vs_cities(ax):
    """D: per-cell flip shares vs the city-level HH-share envelope."""
    flips = pd.read_csv(DATA / "flip_cells.csv")
    env = pd.read_csv(DATA / "typology_share_envelope.csv")
    hh = env[env["class"] == "HH"].copy()
    hh["width"] = hh["max"] - hh["min"]

    f = np.sort(flips.sensitive_pop_share.to_numpy())[::-1] * 100
    w = np.sort(hh.width.to_numpy())[::-1] * 100
    xf = np.arange(1, len(f) + 1)
    ax.fill_between(xf, 0, f, color="0.82", zorder=1)
    ax.plot(xf, f, color="0.35", lw=1.2, zorder=2,
            label=f"population in flip cells (mean {f.mean():.1f} %)")
    ax.fill_between(np.arange(1, len(w) + 1), 0, w, color=THRESHOLD,
                    alpha=0.35, zorder=3)
    ax.plot(np.arange(1, len(w) + 1), w, color=THRESHOLD, lw=1.4, zorder=4,
            label=f"HH-share envelope (mean {w.mean():.1f} pp, "
                  f"max {w.max():.1f} pp)")
    ax.set_xlim(1, len(f))
    ax.set_xlabel("cities, ranked separately per series", fontsize=8)
    ax.set_ylabel("% of population / percentage points", fontsize=8)
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    ax.text(0.98, 0.52,
            "engine cross-check, same shape: friction levels off\n"
            "34–314 %, class shares move ≤ 0.7 pp (per-cell maps\n"
            "carry a ~24 % engine flip — read patterns, not cells)",
            transform=ax.transAxes, ha="right", va="center", fontsize=7,
            color="0.25")
    ax.set_title("D  Cells flip across variants; city-level class shares\n"
                 "barely move — maps are read as patterns, not cells",
                 fontsize=9, loc="left")
    _style(ax)


def main() -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 9.4))
    panel_rank_agreement(axes[0, 0])
    panel_envelopes(axes[0, 1])
    panel_access_reestimation(axes[1, 0])
    panel_cells_vs_cities(axes[1, 1])
    fig.suptitle(
        "The robustness architecture: levels carry the calibration; "
        "ranks, classes and headlines do not depend on it\n"
        "(rank agreement · sensitivity envelopes · access re-estimation · "
        "flip-cell vs class-share stability; 67 cities, all from "
        "docs/paper-pack/data)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = FIGDIR / "robustness_architecture.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
