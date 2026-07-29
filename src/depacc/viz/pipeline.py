"""Viz stage: static matplotlib figures per city + cross-city plane.

Design conventions: sequential single-hue ramps for magnitude (Oranges =
everyday, Purples = emergency), the Stevens 2x2 bivariate scheme for the
compounding typology (labelled legend; population shares also written as CSV
for a non-color reading), recessive axes, no dual axes. Every figure carries
the cross-sectional (space-for-time) framing in its caption where relevant,
and synthetic fixtures are watermarked.

All per-cell maps go through ``_grid_scatter``, which draws every cell EXACTLY
ONCE with a marker sized to the (inferred) grid pitch. This matters most for
the categorical compounding map: the previous per-class loop drew the four
classes in a fixed order with oversized, overlapping markers, so at large cell
counts (e.g. Hamburg's ~176k cells) the last-drawn class (HH) overplotted the
others and the map showed ~80% HH regardless of the true ~30% population share.
A single sized draw removes that draw-order artifact. Note that even a faithful
map is AREA-weighted while the class shares are POPULATION-weighted: a dense,
low-deprivation core holds many people in few cells, so LL/HL occupy little
area even at a large population share. The percentile choropleths and the
on-figure share table make that distinction legible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from depacc.ingest.pipeline import derived_dir

# Stevens bivariate 2x2 corner scheme (LL near-neutral by construction;
# classes carry a labelled legend + CSV table, CVD ΔE validated).
TYPOLOGY_COLORS = {"LL": "#e8e8e8", "HL": "#5ac8c8", "LH": "#be64ac", "HH": "#3b4994"}
TYPOLOGY_LABELS = {
    "LL": "low both",
    "HL": "high everyday only",
    "LH": "high emergency only",
    "HH": "compounding (high both)",
}
REGIME_CMAP = {"everyday": "Oranges", "emergency": "Purples"}


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, linewidth=0.4, alpha=0.35)
    ax.set_axisbelow(True)


def _watermark(fig, cfg):
    if cfg["city"].get("synthetic"):
        fig.text(0.5, 0.5, "SYNTHETIC FIXTURE", fontsize=28, color="0.75",
                 alpha=0.35, ha="center", va="center", rotation=25, zorder=0)


def _infer_pitch(x: np.ndarray, y: np.ndarray) -> float:
    """Robust grid pitch = median nearest-neighbour distance over a sample.
    Works for reprojected (rotated/sheared, non-square) grids, unlike a raster
    snap."""
    pts = np.column_stack([np.asarray(x, float), np.asarray(y, float)])
    n = len(pts)
    if n < 2:
        return 100.0
    try:
        from scipy.spatial import cKDTree

        rng = np.random.default_rng(0)
        sample = pts[rng.choice(n, size=min(n, 4000), replace=False)]
        d, _ = cKDTree(pts).query(sample, k=2)
        nn = d[:, 1]
    except Exception:  # pragma: no cover - scipy always present with [geo]
        xs = np.unique(np.round(pts[:, 0], 3))
        nn = np.diff(xs) if xs.size > 1 else np.array([100.0])
    nn = nn[np.isfinite(nn) & (nn > 0)]
    return float(np.median(nn)) if nn.size else 100.0


def _grid_scatter(fig, ax, x, y, *, color=None, c=None, cmap=None,
                  vmin=None, vmax=None, pitch=None, overlap=1.3):
    """Draw every cell once, as a square marker sized to the grid pitch.

    Pass ``color`` (per-point RGBA/hex array, categorical) or ``c`` (+cmap/
    vmin/vmax, continuous). Returns the PathCollection (for colorbars). Points
    are drawn in a fixed shuffled order so no class systematically overplots.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if pitch is None:
        pitch = _infer_pitch(x, y)
    ax.set_aspect("equal")
    ax.set_xlim(x.min() - pitch, x.max() + pitch)
    ax.set_ylim(y.min() - pitch, y.max() + pitch)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    # Size the marker from the actually-rendered axes pixel box (points are
    # physical, so this stays correct through bbox_inches="tight" and any save
    # DPI).
    fig.canvas.draw()
    bb = ax.get_window_extent()
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    px_per_data = min(bb.width / (xlim[1] - xlim[0]),
                      bb.height / (ylim[1] - ylim[0]))
    side_pt = pitch * px_per_data * 72.0 / fig.dpi
    s = max((side_pt * overlap) ** 2, 1.0)
    order = np.arange(len(x))
    np.random.default_rng(0).shuffle(order)
    if c is not None:
        return ax.scatter(x[order], y[order], c=np.asarray(c)[order], cmap=cmap,
                          vmin=vmin, vmax=vmax, s=s, marker="s", linewidths=0)
    return ax.scatter(x[order], y[order], c=np.asarray(color)[order], s=s,
                      marker="s", linewidths=0)


def _choropleth(fig, ax, df, value_col, cmap, *, vmin=0.0, vmax=None,
                unreachable_col=None):
    dep = df[value_col].to_numpy(float)
    if vmax is None:
        vmax = float(np.nanquantile(dep, 0.98))
    sc = _grid_scatter(fig, ax, df.x.to_numpy(), df.y.to_numpy(),
                       c=dep, cmap=cmap, vmin=vmin, vmax=vmax)
    if unreachable_col and unreachable_col in df:
        unreach = df[df[unreachable_col]]
        if len(unreach):
            ax.scatter(unreach.x, unreach.y, s=5, marker="x", c="#666666",
                       linewidths=0.5, label=f"unreachable ({len(unreach)} cells)")
            ax.legend(loc="lower right", frameon=False, fontsize=8)
    return sc


def run_viz(cfg: dict, city: str, root: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = derived_dir(cfg, city, root)
    figdir = out / "figures"
    figdir.mkdir(exist_ok=True)
    surfaces = pd.read_parquet(out / "surfaces.parquet")
    typology = pd.read_parquet(out / "typology.parquet")
    name = cfg["city"].get("name", city)

    # --- 1. deprivation choropleths (one sequential hue per regime) ---------
    for regime in ("everyday", "emergency"):
        fig, ax = plt.subplots(figsize=(7, 6.5))
        sc = _choropleth(fig, ax, surfaces, f"deprivation_{regime}",
                         REGIME_CMAP[regime],
                         unreachable_col=f"unreachable_{regime}")
        kind = surfaces[f"deprivation_kind_{regime}"].iloc[0]
        ax.set_title(f"{name}: {regime} potential deprivation ({kind})", fontsize=11)
        cb = fig.colorbar(sc, ax=ax, shrink=0.75)
        cb.set_label(f"deprivation ({'dimensionless' if kind == 'DLF' else 'monetary'})",
                     fontsize=9)
        cb.outline.set_visible(False)
        _watermark(fig, cfg)
        fig.tight_layout()
        fig.savefig(figdir / f"deprivation_{regime}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

    # --- 1b. PERCENTILE choropleths (the surfaces the co-location split uses)
    # These are the population-weighted ranks; the typology thresholds cut them
    # at 0.50 / 0.75. Showing them bridges the magnitude maps and the class map.
    for regime in ("everyday", "emergency"):
        pcol = f"{regime}_pct"
        if pcol not in typology.columns:
            continue
        fig, ax = plt.subplots(figsize=(7, 6.5))
        sc = _grid_scatter(fig, ax, typology.x.to_numpy(), typology.y.to_numpy(),
                           c=typology[pcol].to_numpy(float),
                           cmap=REGIME_CMAP[regime], vmin=0.0, vmax=1.0)
        ax.set_title(f"{name}: {regime} deprivation — population-weighted "
                     f"percentile (rank)", fontsize=11)
        cb = fig.colorbar(sc, ax=ax, shrink=0.75)
        cb.set_label("percentile of population-weighted rank", fontsize=9)
        cb.outline.set_visible(False)
        _watermark(fig, cfg)
        fig.tight_layout()
        fig.savefig(figdir / f"percentile_{regime}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

    # --- 2. bivariate compounding maps (one per configured threshold) -------
    thresholds = cfg.get("typology", {}).get("thresholds", [0.5, 0.75])
    for thr in thresholds:
        key = f"{int(round(thr * 100)):02d}"
        typ_col = f"typology_{key}"
        if typ_col not in typology.columns:
            typ_col = "typology_50" if "typology_50" in typology.columns else "typology"
        _compounding_map(fig_out=figdir / f"compounding_map_{key}.png",
                         typology=typology, typ_col=typ_col, name=name,
                         threshold=thr, summary_csv=out / f"typology_summary_{key}.csv",
                         cfg=cfg, plt=plt)
    # Back-compat alias: the median-split map keeps its original filename.
    src = figdir / "compounding_map_50.png"
    if src.exists():
        import shutil
        shutil.copyfile(src, figdir / "compounding_map.png")

    # --- 3. per-service accessibility small multiples (travel time) ---------
    _service_accessibility_panel(surfaces, cfg, name, figdir, plt)

    # --- 4. sensitivity envelope (if the sweep has been run) ----------------
    _sensitivity_figure(cfg, city, root, name, figdir, plt)

    # --- 5. cross-city everyday-vs-emergency plane --------------------------
    plane_path = root / cfg["output"]["root"] / "cityplane.csv"
    if plane_path.exists():
        plane = pd.read_csv(plane_path)
        # Curvature envelope per city (min-max Gini across the deprivation-
        # function curvature variants), if the robustness sweep has been run —
        # drawn as error bars, the honest way to place a city on the plane.
        envelopes = {str(r.city): _curvature_envelope(root, cfg, str(r.city))
                     for _, r in plane.iterrows()}
        fig, ax = plt.subplots(figsize=(6.5, 6))
        hi_env = [max(e["ev_hi"], e["em_hi"]) for e in envelopes.values() if e]
        lim = max([plane.gini_everyday.max(), plane.gini_emergency.max(), *hi_env]) \
            * 1.15 + 1e-9
        ax.plot([0, lim], [0, lim], color="0.75", linewidth=1, linestyle="--",
                zorder=1)
        n_env = 0
        for _, r in plane.iterrows():
            e = envelopes.get(str(r.city))
            if not e:
                continue
            xerr = [[max(0.0, r.gini_everyday - e["ev_lo"])],
                    [max(0.0, e["ev_hi"] - r.gini_everyday)]]
            yerr = [[max(0.0, r.gini_emergency - e["em_lo"])],
                    [max(0.0, e["em_hi"] - r.gini_emergency)]]
            ax.errorbar(r.gini_everyday, r.gini_emergency, xerr=xerr, yerr=yerr,
                        fmt="none", ecolor="#3b4994", elinewidth=1.0,
                        capsize=2, alpha=0.45, zorder=2)
            n_env += 1
        ax.scatter(plane.gini_everyday, plane.gini_emergency,
                   s=20 + 40 * np.log10(plane.population.clip(lower=1) + 1),
                   c="#3b4994", alpha=0.85, linewidths=0, zorder=3)
        n_rho = 0
        for _, r in plane.iterrows():
            label = r["name"] + (" (synthetic)" if r.get("synthetic") else "")
            # Coupling ρ with its accessibility envelope (Layer-3, non-
            # degenerate variants), when the sweep has run: the point estimate
            # alone overstates the accessibility model's precision (on Hamburg
            # the congestion exponent alone spans ρ 0.39-0.56 around 0.43).
            renv = _rho_envelope(root, cfg, str(r.city))
            if renv and "spearman_rho" in plane.columns and np.isfinite(r.spearman_rho):
                label += (f"\nρ={r.spearman_rho:.2f} "
                          f"[{renv['lo']:.2f}, {renv['hi']:.2f}]")
                n_rho += 1
            ax.annotate(label, (r.gini_everyday, r.gini_emergency),
                        textcoords="offset points", xytext=(6, 4), fontsize=8,
                        color="0.25")
        ax.set_xlabel("Gini of everyday deprivation")
        ax.set_ylabel("Gini of emergency deprivation")
        env_note = ("\nbars = min-max Gini across curvature variants"
                    if n_env else "")
        if n_rho:
            env_note += "; ρ bands = min-max across accessibility variants"
        ax.set_title("Cities in the everyday-vs-emergency inequity plane\n"
                     "(cross-sectional; size ~ log population)" + env_note,
                     fontsize=10)
        ax.set_xlim(0, lim); ax.set_ylim(0, lim)
        _style(ax)
        fig.tight_layout()
        crossdir = root / cfg["output"]["root"] / "figures"
        crossdir.mkdir(parents=True, exist_ok=True)
        fig.savefig(crossdir / "cityplane.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

    print(f"figures written to {figdir} (+ cross-city cityplane)")


def _compounding_map(*, fig_out, typology, typ_col, name, threshold,
                     summary_csv, cfg, plt):
    """One bivariate co-location map with an on-figure population-share table."""
    colors = typology[typ_col].map(TYPOLOGY_COLORS).to_numpy()
    valid = typology[typ_col].notna().to_numpy()
    fig, ax = plt.subplots(figsize=(8.2, 6.5))
    _grid_scatter(fig, ax, typology.x.to_numpy()[valid],
                  typology.y.to_numpy()[valid], color=colors[valid])
    pct = int(round(threshold * 100))
    split = "median split" if pct == 50 else f"p{pct} split"
    ax.set_title(f"{name}: everyday x emergency co-location "
                 f"(pop-weighted {split} of percentiles)", fontsize=11)
    # Legend + population-share table (shares are population-weighted; the map
    # is area-weighted — see module docstring).
    import matplotlib.patches as mpatches

    shares = {}
    if summary_csv.exists():
        s = pd.read_csv(summary_csv).set_index("typology")
        shares = s["population_share"].to_dict()
    handles = []
    for cls in ("LL", "HL", "LH", "HH"):
        share = shares.get(cls)
        lab = f"{cls} — {TYPOLOGY_LABELS[cls]}"
        if share is not None and np.isfinite(share):
            lab += f"  ({share:.0%} pop)"
        handles.append(mpatches.Patch(color=TYPOLOGY_COLORS[cls], label=lab))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1),
              frameon=False, fontsize=8,
              title="class (share = % of population)", title_fontsize=8)
    fig.text(0.99, 0.02,
             "shares are population-weighted; map area is not\n"
             "(dense low-deprivation cores hold many people in few cells)",
             ha="right", va="bottom", fontsize=7, color="0.45")
    _watermark(fig, cfg)
    fig.tight_layout()
    fig.savefig(fig_out, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _service_accessibility_panel(surfaces, cfg, name, figdir, plt):
    """Small-multiple travel-time maps, one per infrastructure service."""
    services = list(cfg.get("everyday_services", {})) + list(cfg.get("emergency_services", {}))
    services = [s for s in services if f"t_regime_{s}" in surfaces.columns]
    if not services:
        return
    ncol = 3
    nrow = int(np.ceil(len(services) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.0 * ncol, 3.7 * nrow))
    axes = np.atleast_1d(axes).ravel()
    everyday = set(cfg.get("everyday_services", {}))
    for ax, service in zip(axes, services):
        regime = "everyday" if service in everyday else "emergency"
        t = surfaces[f"t_regime_{service}"].to_numpy(float)
        vmax = float(np.nanquantile(t, 0.95)) or 1.0
        sc = _grid_scatter(fig, ax, surfaces.x.to_numpy(), surfaces.y.to_numpy(),
                           c=t, cmap=REGIME_CMAP[regime], vmin=0.0, vmax=vmax)
        med = np.nanmedian(t)
        ax.set_title(f"{service}\n(median {med:.0f} min)", fontsize=9)
        cb = fig.colorbar(sc, ax=ax, shrink=0.7)
        cb.ax.tick_params(labelsize=7)
        cb.outline.set_visible(False)
    for ax in axes[len(services):]:
        ax.set_visible(False)
    fig.suptitle(f"{name}: accessibility by infrastructure — regime-representative "
                 f"travel time (min)", fontsize=12)
    _watermark(fig, cfg)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(figdir / "accessibility_by_service.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def _curvature_envelope(root, cfg, city):
    """Min-max within-regime Gini across the deprivation-function CURVATURE
    variants for one city, from its robustness table (form-swap variants are
    excluded — they sit on the separate ``form_swap`` axis). Returns
    {ev_lo, ev_hi, em_lo, em_hi} or None if the sweep has not been run."""
    p = root / cfg["output"]["root"] / "sensitivity" / f"{city}_deprivation_sensitivity.csv"
    if not p.exists():
        return None
    tbl = pd.read_csv(p)
    cur = tbl[tbl.axis == "curvature"]
    if cur.empty or cur.gini_everyday.dropna().empty:
        return None
    return {
        "ev_lo": float(cur.gini_everyday.min()), "ev_hi": float(cur.gini_everyday.max()),
        "em_lo": float(cur.gini_emergency.min()), "em_hi": float(cur.gini_emergency.max()),
    }


def _rho_envelope(root, cfg, city):
    """Min-max coupling ρ across the NON-DEGENERATE Layer-3 accessibility
    variants for one city, from its access-sensitivity table. Returns
    {lo, hi} or None if the sweep has not been run (mirrors
    :func:`depacc.sensitivity.access.rho_envelope`)."""
    p = root / cfg["output"]["root"] / "sensitivity" / f"{city}_access_sensitivity.csv"
    if not p.exists():
        return None
    tbl = pd.read_csv(p)
    ok = tbl[tbl.axis != "threshold"]
    if "degenerate" in ok.columns:
        ok = ok[~ok["degenerate"].fillna(False).astype(bool)]
    rho = pd.to_numeric(ok.get("spearman_rho"), errors="coerce").dropna()
    if rho.empty:
        return None
    return {"lo": float(rho.min()), "hi": float(rho.max())}


def _sensitivity_figure(cfg, city, root, name, figdir, plt):
    """Deprivation-assumption sensitivity for this city, if the sweep has run.

    Two panels: (left) compounding/typology shares as the "high" threshold is
    swept — how the split assumption moves the result; (right) the within-
    regime Gini range across deprivation-function curvature variants, next to
    the invariant typology (rank-based), making the scale-free property visible.
    """
    sens_dir = root / cfg["output"]["root"] / "sensitivity"
    tbl_path = sens_dir / f"{city}_deprivation_sensitivity.csv"
    if not tbl_path.exists():
        return
    tbl = pd.read_csv(tbl_path)
    thr = tbl[tbl.axis == "threshold"].sort_values("threshold")
    cur = tbl[tbl.axis == "curvature"]
    if thr.empty and cur.empty:
        return
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4.4))

    # Left: threshold sweep of the four class shares.
    for cls in ("LL", "HL", "LH", "HH"):
        axL.plot(thr.threshold, thr[f"share_{cls}"], marker="o", markersize=4,
                 color=TYPOLOGY_COLORS[cls], label=f"{cls} — {TYPOLOGY_LABELS[cls]}")
    axL.set_xlabel("\"high\" threshold (percentile of pop-weighted rank)")
    axL.set_ylabel("population share")
    axL.set_title("Class shares vs the split threshold\n(the \"how high is high\" assumption)",
                  fontsize=10)
    axL.legend(frameon=False, fontsize=7, loc="upper center", ncol=2)
    _style(axL)

    # Right: Gini range across curvature variants (baseline dot + min-max bar).
    regimes = ["everyday", "emergency"]
    xpos = np.arange(len(regimes))
    base = cur[cur.variant == "baseline"]
    for i, reg in enumerate(regimes):
        col = f"gini_{reg}"
        lo, hi = cur[col].min(), cur[col].max()
        b = float(base[col].iloc[0]) if not base.empty else np.nan
        axR.plot([i, i], [lo, hi], color="0.35", linewidth=6, solid_capstyle="round",
                 alpha=0.5, zorder=2)
        axR.scatter([i], [b], color=REGIME_CMAP[reg].lower().rstrip("s"), s=60,
                    zorder=3, edgecolor="k", linewidth=0.5)
    axR.set_xticks(xpos)
    axR.set_xticklabels([f"Gini\n{r}" for r in regimes], fontsize=9)
    axR.set_ylabel("within-regime Gini")
    hh_rng = cur["share_HH"].max() - cur["share_HH"].min()
    axR.set_title("Gini range across curvature variants\n"
                  f"(typology invariant: HH-share range = {hh_rng:.3f})", fontsize=10)
    _style(axR)

    fig.suptitle(f"{name}: sensitivity to deprivation-function assumptions",
                 fontsize=12)
    _watermark(fig, cfg)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(figdir / "sensitivity_deprivation.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
