#!/usr/bin/env python3
"""Check every number quoted in the paper pack against the tables it cites.

The pack's prose (``docs/paper-pack/BRIEF.md``, ``docs/results-headlines.md``)
quotes ~60 numbers. They were hand-copied from tables that have been
regenerated many times, and drift is exactly what happened before: a
regional p from an older run, a cluster diagnostic from the peeled pass
quoted as the main pass, a grade split no rule in the repo reproduces.

This script re-reads each number from the CSV it is sourced from and
compares it to what the prose claims, at the precision the prose uses. It
does NOT re-run any analysis — it is a consistency check between the
written claims and the shipped tables, not a reproduction of them (for
that, run ``depacc cross`` over the persisted union).

    python tools/audit_paper_pack.py            # audit docs/paper-pack/data
    python tools/audit_paper_pack.py --data DIR

Exit code 1 if any check fails, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_DATA = Path("docs/paper-pack/data")


class Audit:
    def __init__(self, data: Path) -> None:
        self.data = data
        self.rows: list[tuple[str, str, object, object, bool]] = []
        self._cache: dict[str, pd.DataFrame] = {}

    def table(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            self._cache[name] = pd.read_csv(self.data / f"{name}.csv")
        return self._cache[name]

    def check(self, claim: str, source: str, actual: object,
              expected: object, tol: float = 0.0) -> None:
        if isinstance(expected, (int, float)) and isinstance(
                actual, (int, float)):
            ok = abs(float(actual) - float(expected)) <= tol
        else:
            ok = actual == expected
        self.rows.append((claim, source, expected, actual, ok))

    def cell(self, table: str, where: dict, column: str) -> float:
        df = self.table(table)
        for col, val in where.items():
            df = df[df[col].astype(str) == str(val)]
        if len(df) != 1:
            raise AssertionError(
                f"{table}: {where} matched {len(df)} rows, expected 1")
        return float(df[column].iloc[0])

    def report(self) -> int:
        width = max(len(r[0]) for r in self.rows) + 2
        failed = 0
        for claim, source, expected, actual, ok in self.rows:
            flag = "ok  " if ok else "FAIL"
            if not ok:
                failed += 1
            shown_e = (f"{expected:.6g}" if isinstance(expected, float)
                       else expected)
            shown_a = f"{actual:.6g}" if isinstance(actual, float) else actual
            print(f"{flag} {claim:<{width}} claimed {shown_e!s:>12} | "
                  f"table {shown_a!s:>12}   ({source})")
        print(f"\n{len(self.rows) - failed}/{len(self.rows)} checks passed")
        return 1 if failed else 0


def run(data: Path) -> int:
    a = Audit(data)

    # ---- sample -----------------------------------------------------------
    plane = a.table("cityplane")
    a.check("sample: n cities", "cityplane", len(plane), 67)
    a.check("sample: n countries", "cityplane", plane.country.nunique(), 24)
    a.check("sample: population (M)", "cityplane",
            round(plane.population.sum() / 1e6, 1), 113.9, 0.05)
    a.check("sample: smallest FUA", "cityplane",
            int(plane.population.min()), 101050, 500)
    a.check("sample: largest FUA (M)", "cityplane",
            round(plane.population.max() / 1e6, 1), 12.9, 0.05)
    desc = a.table("cities_descriptives")
    a.check("descriptives rows", "cities_descriptives", len(desc), 67)

    # ---- facilities and travel times (methods table) ----------------------
    pooled = a.table("accessibility_by_service_pooled").set_index("service")
    for service, facilities, minutes in (("gp", 93, 7.9),
                                         ("pharmacy", 228, 4.9),
                                         ("supermarket", 325, 4.7),
                                         ("school_primary", 409, 4.4),
                                         ("green_space_local", 636, 3.8),
                                         ("emergency_dept_hospital", 6, 12.0),
                                         ("ambulance_station", 6, 12.0)):
        a.check(f"facilities per FUA: {service}",
                "accessibility_by_service_pooled",
                round(float(pooled.loc[service, "n_facilities_median"])),
                facilities, 0.5)
        a.check(f"median travel time: {service}",
                "accessibility_by_service_pooled",
                round(float(pooled.loc[service,
                                       "pop_median_time_min_median"]), 1),
                minutes, 0.05)
    a.check("single-emergency-service cities", "cities_descriptives",
            int((desc.n_emergency_services < 2).sum()), 8)
    a.check("single-emergency-service cities named", "cities_descriptives",
            sorted(desc.loc[desc.n_emergency_services < 2, "city"]),
            ["athina", "braila", "helsinki", "lahti", "norrkoping", "szeged",
             "talavera_de_la_reina", "zilina"])
    a.check("no city missing an everyday service",
            "accessibility_by_service_pooled",
            int(pooled.loc[pooled.regime == "everyday", "n_cities"].min()), 67)
    svc = a.table("accessibility_by_service_cities")
    gp = svc[svc.service == "gp"].merge(plane[["city", "population"]],
                                        on="city")
    gp = gp.assign(per100k=gp.n_facilities / (gp.population / 1e5))
    a.check("GP per 100k: sample median",
            "accessibility_by_service_cities",
            round(float(gp.per100k.median()), 1), 10.9, 0.05)
    by_country = gp.groupby("country").per100k.median().round(1)
    for country, expected in (("SE", 2.1), ("PT", 2.3), ("FI", 2.6),
                              ("IT", 3.5)):
        a.check(f"GP per 100k: {country} median",
                "accessibility_by_service_cities",
                float(by_country[country]), expected, 0.05)
    # The regional lookup is defined further down for H3; build it here too
    # so the completeness limitation is checked in one place.
    _regions = {"North": ["SE", "NO", "DK", "FI"],
                "West": ["DE", "NL", "FR", "BE", "AT", "LU"],
                "South": ["ES", "IT", "PT", "EL"],
                "CEE": ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR",
                        "EE", "LV", "LT"]}
    _lookup = {c: r for r, cs in _regions.items() for c in cs}
    a.check("GP per 100k: West median", "accessibility_by_service_cities",
            round(float(gp[gp.country.map(_lookup) == "West"]
                        .per100k.median()), 1), 24.6, 0.05)
    thin = desc.n_emergency_services < 2
    em = desc.set_index("city").mean_emergency
    a.check("single-service cities: median mean_emergency",
            "cities_descriptives",
            round(float(em[desc.loc[thin, "city"]].median()), 4), 1.3237,
            5e-4)
    a.check("two-service cities: median mean_emergency",
            "cities_descriptives",
            round(float(em[desc.loc[~thin, "city"]].median()), 4), 1.1372,
            5e-4)
    a.check("no single-service city is a desert",
            "cities_descriptives vs cityvector_clustered",
            bool(set(desc.loc[thin, "city"]).isdisjoint(
                set(a.table("cityvector_clustered")
                    .pipe(lambda d: d.loc[d.cluster_kmeans
                          == d.cluster_kmeans.value_counts().idxmin(),
                          "city"])))), True)

    # ---- H1: regime-specific agglomeration --------------------------------
    sc = {"table": "inference_scaling_clustered", "where_key": "outcome"}
    a.check("H1 everyday elasticity", sc["table"],
            a.cell(sc["table"], {"outcome": "mean_everyday"}, "elasticity"),
            -0.196, 0.0005)
    a.check("H1 everyday clustered SE", sc["table"],
            a.cell(sc["table"], {"outcome": "mean_everyday"},
                   "se_cluster_country"), 0.023, 0.0005)
    a.check("H1 everyday wild p", sc["table"],
            a.cell(sc["table"], {"outcome": "mean_everyday"},
                   "p_wild_cluster_bootstrap"), 0.0002, 1e-9)
    a.check("H1 emergency elasticity", sc["table"],
            a.cell(sc["table"], {"outcome": "mean_emergency"}, "elasticity"),
            -0.059, 0.0005)
    a.check("H1 emergency clustered p", sc["table"],
            a.cell(sc["table"], {"outcome": "mean_emergency"},
                   "p_cluster_country"), 0.16, 0.005)
    a.check("H1 emergency wild p", sc["table"],
            a.cell(sc["table"], {"outcome": "mean_emergency"},
                   "p_wild_cluster_bootstrap"), 0.21, 0.005)
    a.check("H1 TOST smallest bound", "inference_equivalence",
            a.cell("inference_equivalence", {"outcome": "mean_emergency"},
                   "smallest_passing_bound"), 0.132, 0.001)
    a.check("H1 paired mean diff", "inference_regime_paired",
            a.cell("inference_regime_paired", {"measure": "mean"},
                   "gradient_difference_emergency"), 0.137, 0.0005)
    a.check("H1 paired mean wild p", "inference_regime_paired",
            a.cell("inference_regime_paired", {"measure": "mean"},
                   "p_wild_cluster_bootstrap"), 0.002, 5e-4)
    infl = a.table("inference_influence")
    ev = infl[infl.outcome == "mean_everyday"].iloc[0]
    a.check("H1 LOO envelope min", "inference_influence",
            round(float(ev.loo_min), 3), -0.204, 0.0005)
    a.check("H1 LOO envelope max", "inference_influence",
            round(float(ev.loo_max), 3), -0.185, 0.0005)
    a.check("H1 Huber re-estimate", "inference_influence",
            round(float(ev.elasticity_huber), 3), -0.196, 0.0005)
    a.check("H1 excl-desert re-fit", "inference_influence",
            round(float(ev.elasticity_excl_desert), 3), -0.203, 0.0005)

    # ---- H2: inequality scaling -------------------------------------------
    a.check("H2 gini_everyday slope", sc["table"],
            a.cell(sc["table"], {"outcome": "gini_everyday"}, "elasticity"),
            0.062, 0.0005)
    a.check("H2 gini_everyday wild p", sc["table"],
            a.cell(sc["table"], {"outcome": "gini_everyday"},
                   "p_wild_cluster_bootstrap"), 0.0012, 5e-4)
    a.check("H2 gini_emergency slope", sc["table"],
            a.cell(sc["table"], {"outcome": "gini_emergency"}, "elasticity"),
            0.004, 0.0005)
    a.check("H2 gini_emergency wild p", sc["table"],
            a.cell(sc["table"], {"outcome": "gini_emergency"},
                   "p_wild_cluster_bootstrap"), 0.84, 0.005)
    a.check("H2 paired gini diff", "inference_regime_paired",
            a.cell("inference_regime_paired", {"measure": "gini"},
                   "gradient_difference_emergency"), -0.058, 0.0005)
    a.check("H2 paired gini wild p", "inference_regime_paired",
            a.cell("inference_regime_paired", {"measure": "gini"},
                   "p_wild_cluster_bootstrap"), 0.029, 5e-4)
    spec = a.table("specification_curve")
    ev_spec = spec[spec.outcome == "gini_everyday"].drop_duplicates("variant")
    a.check("H2 spec-curve variants", "specification_curve",
            len(ev_spec), 13)
    a.check("H2 spec-curve all positive", "specification_curve",
            bool((ev_spec.elasticity > 0).all()), True)
    a.check("H2 spec-curve min slope", "specification_curve",
            round(float(ev_spec.elasticity.min()), 3), 0.026, 0.0005)
    a.check("H2 spec-curve max slope", "specification_curve",
            round(float(ev_spec.elasticity.max()), 3), 0.075, 0.0005)
    a.check("H2 spec-curve significant", "specification_curve",
            int((ev_spec.p < 0.05).sum()), 12)
    box = ev_spec[ev_spec.variant == "formswap_everyday_box_cox"].iloc[0]
    a.check("H2 Box-Cox exception p", "specification_curve",
            round(float(box.p), 3), 0.082, 0.0005)
    em_spec = spec[spec.outcome == "gini_emergency"].drop_duplicates("variant")
    sig = em_spec[em_spec.p < 0.05]
    a.check("H2 emergency spec: exactly one significant variant",
            "specification_curve", len(sig), 1)
    a.check("H2 emergency spec: the exception is the benchmark exponential",
            "specification_curve", list(sig.variant),
            ["formswap_emergency_exponential"])
    a.check("H2 exception slope", "specification_curve",
            round(float(sig.elasticity.iloc[0]), 3), 0.098, 0.0005)
    a.check("H2 exception p", "specification_curve",
            round(float(sig.p.iloc[0]), 4), 0.0003, 0.0002)
    non_exp = em_spec[em_spec.variant != "formswap_emergency_exponential"]
    a.check("H2 emergency null holds outside the exception",
            "specification_curve", int((non_exp.p < 0.05).sum()), 0)

    # ---- H3: regional structure -------------------------------------------
    reg = "inference_regional"
    a.check("H3 gini_emergency Cohen f", reg,
            a.cell(reg, {"outcome": "gini_emergency"}, "cohen_f_city"),
            0.74, 0.005)
    a.check("H3 gini_emergency p_perm", reg,
            a.cell(reg, {"outcome": "gini_emergency"},
                   "p_permutation_countries"), 0.0024, 0.0002)
    a.check("H3 divergence_gap p_perm", reg,
            a.cell(reg, {"outcome": "divergence_gap"},
                   "p_permutation_countries"), 0.010, 0.0005)
    a.check("H3 spearman_rho p_perm", reg,
            a.cell(reg, {"outcome": "spearman_rho"},
                   "p_permutation_countries"), 0.0015, 0.0002)
    a.check("H3 HH share p_perm", reg,
            a.cell(reg, {"outcome": "compounding_pop_share_50"},
                   "p_permutation_countries"), 0.0008, 0.0002)
    a.check("H3 intensity p_perm", reg,
            a.cell(reg, {"outcome": "compounding_intensity"},
                   "p_permutation_countries"), 0.0023, 0.0002)
    a.check("H3 gini_everyday NOT regional (p_perm)", reg,
            a.cell(reg, {"outcome": "gini_everyday"},
                   "p_permutation_countries"), 0.27, 0.005)
    a.check("H3 gini_everyday city-level p", reg,
            a.cell(reg, {"outcome": "gini_everyday"},
                   "p_city_anova_anticonservative"), 0.0007, 0.0001)
    regions = {"North": ["SE", "NO", "DK", "FI"],
               "West": ["DE", "NL", "FR", "BE", "AT", "LU"],
               "South": ["ES", "IT", "PT", "EL"],
               "CEE": ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR",
                       "EE", "LV", "LT"]}
    lookup = {c: r for r, cs in regions.items() for c in cs}
    plane = plane.assign(region=plane.country.map(lookup))
    med = plane.groupby("region")[["gini_emergency", "spearman_rho",
                                   "divergence_gap"]].median()
    a.check("H3 CEE median gini_emergency", "cityplane",
            round(float(med.loc["CEE", "gini_emergency"]), 2), 0.54, 0.005)
    a.check("H3 CEE median rho", "cityplane",
            round(float(med.loc["CEE", "spearman_rho"]), 2), 0.55, 0.005)
    a.check("H3 West median divergence_gap", "cityplane",
            round(float(med.loc["West", "divergence_gap"]), 2), -0.12, 0.005)
    a.check("H3 North median divergence_gap", "cityplane",
            round(float(med.loc["North", "divergence_gap"]), 2), 0.09, 0.005)

    # ---- H4: clustering ---------------------------------------------------
    clus = a.table("cityvector_clustered")
    km = clus.cluster_kmeans.value_counts().sort_values()
    a.check("H4 k-means split (small group)", "cityvector_clustered",
            int(km.iloc[0]), 5)
    a.check("H4 k-means split (large group)", "cityvector_clustered",
            int(km.iloc[-1]), 62)
    small = set(clus.loc[clus.cluster_kmeans == km.index[0], "city"])
    a.check("H4 desert cities", "cityvector_clustered", sorted(small),
            ["bucuresti", "ljubljana", "riga", "tallinn", "vilnius"])
    ward = clus.cluster_ward.value_counts().sort_values()
    a.check("H4 Ward small group size", "cityvector_clustered",
            int(ward.iloc[0]), 2)
    a.check("H4 Ward nests in k-means", "cityvector_clustered",
            set(clus.loc[clus.cluster_ward == ward.index[0], "city"])
            <= small, True)
    cn = a.table("cluster_null").iloc[0]
    a.check("H4 main silhouette", "cluster_null",
            round(float(cn.observed_silhouette), 2), 0.65, 0.005)
    a.check("H4 main null p", "cluster_null", float(cn.p_null_gaussian),
            0.001, 1e-9)
    a.check("H4 main bootstrap ARI", "cluster_null",
            round(float(cn.stability_ari), 2), 0.87, 0.005)
    cnp = a.table("cluster_null_peeled").iloc[0]
    a.check("H4 peeled n removed", "cluster_null_peeled",
            int(cnp.n_removed), 5)
    a.check("H4 peeled silhouette", "cluster_null_peeled",
            round(float(cnp.silhouette), 2), 0.38, 0.005)
    a.check("H4 peeled bootstrap ARI", "cluster_null_peeled",
            round(float(cnp.stability_ari), 2), 0.74, 0.005)
    a.check("H4 peeled null p", "cluster_null_peeled",
            float(cnp.p_null_gaussian), 0.001, 1e-9)
    a.check("H4 peeled ARI vs region", "cluster_null_peeled",
            round(float(cnp.ari_vs_region), 2), 0.07, 0.005)
    peeled = a.table("cityvector_clustered_peeled")
    pk = peeled.cluster_kmeans.value_counts().sort_values()
    a.check("H4 peeled split (small)", "cityvector_clustered_peeled",
            int(pk.iloc[0]), 14)
    a.check("H4 peeled split (large)", "cityvector_clustered_peeled",
            int(pk.iloc[-1]), 48)
    pw = peeled.cluster_ward.value_counts().sort_values()
    a.check("H4 peeled Ward nests", "cityvector_clustered_peeled",
            set(peeled.loc[peeled.cluster_ward == pw.index[0], "city"])
            <= set(peeled.loc[peeled.cluster_kmeans == pk.index[0], "city"]),
            True)

    # ---- H5: who carries it -----------------------------------------------
    vs = a.table("vulnerability_summary").set_index("stratum")
    a.check("H5 children median ratio", "vulnerability_summary",
            round(float(vs.loc["children_census",
                               "median_everyday_ratio_covered"]), 2),
            1.27, 0.005)
    a.check("H5 children share > 1", "vulnerability_summary",
            round(float(vs.loc["children_census",
                               "share_cities_everyday_ratio_gt1"]), 2),
            0.88, 0.005)
    a.check("H5 children median HH gap", "vulnerability_summary",
            round(float(vs.loc["children_census",
                               "median_hh_share_gap_covered"]), 2),
            0.13, 0.005)
    a.check("H5 elderly median ratio", "vulnerability_summary",
            round(float(vs.loc["elderly_census",
                               "median_everyday_ratio_covered"]), 2),
            0.96, 0.005)
    a.check("H5 elderly share > 1", "vulnerability_summary",
            round(float(vs.loc["elderly_census",
                               "share_cities_everyday_ratio_gt1"]), 2),
            0.37, 0.005)
    vuln = a.table("vulnerability")
    vuln = vuln.assign(region=vuln.country.map(lookup))
    kids = vuln[vuln.stratum == "children_census"]
    a.check("H5 CEE children ratio", "vulnerability",
            round(float(kids[kids.region == "CEE"]
                        .mean_dep_everyday_ratio_covered.median()), 2),
            1.44, 0.005)

    # ---- H6: compounding --------------------------------------------------
    a.check("H6 mean HH share", "cityplane",
            round(float(plane.compounding_pop_share_50.mean()), 2), 0.33,
            0.005)
    a.check("H6 cities above independence", "cityplane",
            int((plane.compounding_pop_share_50 > 0.25).sum()), 66)
    a.check("H6 rho minimum", "cityplane",
            round(float(plane.spearman_rho.min()), 2), -0.02, 0.005)
    a.check("H6 rho maximum", "cityplane",
            round(float(plane.spearman_rho.max()), 2), 0.74, 0.005)

    # ---- H7: deprivation vs access ----------------------------------------
    dva = a.table("deprivation_vs_access")
    a.check("H7 everyday median-time elasticity", "deprivation_vs_access",
            round(float(dva[dva.outcome == "everyday_median_time"]
                        .elasticity.iloc[0]), 3), -0.237, 0.0005)
    a.check("H7 access R2", "deprivation_vs_access",
            round(float(dva[dva.outcome == "everyday_median_time"]
                        .r2.iloc[0]), 2), 0.16, 0.005)
    a.check("H7 deprivation R2", "deprivation_vs_access",
            round(float(dva[dva.outcome == "mean_everyday"].r2.iloc[0]), 2),
            0.44, 0.005)
    gini_corr = dva[dva.block == "gini_correlation"]
    a.check("H7 everyday Gini correlation", "deprivation_vs_access",
            round(float(gini_corr[gini_corr.regime == "everyday"]
                        .elasticity.iloc[0]), 3), 0.965, 0.0005)
    a.check("H7 emergency Gini correlation", "deprivation_vs_access",
            round(float(gini_corr[gini_corr.regime == "emergency"]
                        .elasticity.iloc[0]), 3), 0.976, 0.0005)
    dac = a.table("desert_access_contrast").set_index("city")
    a.check("H7 Bucharest access ratio", "desert_access_contrast",
            round(float(dac.loc["bucuresti", "median_time_ratio_vs_sample"]),
                  2), 0.71, 0.005)
    a.check("H7 Bucharest deprivation ratio", "desert_access_contrast",
            round(float(dac.loc["bucuresti", "deprivation_ratio_vs_sample"]),
                  2), 2.81, 0.005)
    a.check("H7 desert rows", "desert_access_contrast", len(dac), 5)
    a.check("H7 desert access-ratio range (min)", "desert_access_contrast",
            round(float(dac.median_time_ratio_vs_sample.min()), 2), 0.71,
            0.005)
    a.check("H7 desert access-ratio range (max)", "desert_access_contrast",
            round(float(dac.median_time_ratio_vs_sample.max()), 2), 1.92,
            0.005)
    a.check("H7 desert deprivation-ratio range (min)",
            "desert_access_contrast",
            round(float(dac.deprivation_ratio_vs_sample.min()), 2), 2.45,
            0.005)
    a.check("H7 desert deprivation-ratio range (max)",
            "desert_access_contrast",
            round(float(dac.deprivation_ratio_vs_sample.max()), 2), 4.72,
            0.005)
    grade = a.table("scaling_by_grade").set_index("grade")
    a.check("H7 covered n", "scaling_by_grade",
            int(grade.loc["covered", "n_cities"]), 48)
    a.check("H7 partial desert n", "scaling_by_grade",
            int(grade.loc["partial desert", "n_cities"]), 14)
    a.check("H7 desert n", "scaling_by_grade",
            int(grade.loc["desert", "n_cities"]), 5)
    a.check("H7 grade level shift p < 1e-10", "scaling_by_grade",
            bool(float(grade.loc["grade level shift (at mean size)", "p"])
                 < 1e-10), True)
    a.check("H7 grade interaction p", "scaling_by_grade",
            round(float(grade.loc["interaction (slope x grade)", "p"]), 3),
            0.010, 0.0005)

    # ---- size gradient of divergence --------------------------------------
    a.check("gap slope per log10 pop", "size_gradient",
            a.cell("size_gradient", {"outcome": "divergence_gap"},
                   "slope_per_log10_pop"), -0.066, 0.0005)
    a.check("gap slope p", "size_gradient",
            round(a.cell("size_gradient", {"outcome": "divergence_gap"},
                         "p"), 3), 0.012, 0.0005)
    a.check("gap slope R2", "size_gradient",
            round(a.cell("size_gradient", {"outcome": "divergence_gap"},
                         "r2"), 2), 0.06, 0.005)

    # ---- robustness inventory ---------------------------------------------
    ra = a.table("rank_agreement")
    scoped = ra[ra.variant != "formswap_emergency_exponential"]
    mins = scoped.groupby("target").spearman_rho.min().round(2)
    a.check("rank agreement min rho (gini_everyday, scoped)",
            "rank_agreement", float(mins["gini_everyday"]), 0.90, 0.005)
    a.check("rank agreement min rho (divergence_gap, scoped)",
            "rank_agreement", float(mins["divergence_gap"]), 0.95, 0.005)
    a.check("rank agreement min rho (gini_emergency, scoped)",
            "rank_agreement", float(mins["gini_emergency"]), 0.98, 0.005)
    exp_em = ra[(ra.variant == "formswap_emergency_exponential")
                & (ra.target == "gini_emergency")]
    a.check("rank agreement: the flagged exception (emergency, exponential)",
            "rank_agreement", round(float(exp_em.spearman_rho.iloc[0]), 2),
            0.19, 0.005)
    a.check("rank agreement covers the sample", "rank_agreement",
            int(ra.n_cities.max()), 67)
    cfr = a.table("cluster_feature_robustness").iloc[0]
    a.check("feature-set robustness: main partition ARI",
            "cluster_feature_robustness",
            round(float(cfr.ari_vs_published), 2), 1.0, 1e-9)
    a.check("feature-set robustness: same small group",
            "cluster_feature_robustness",
            bool(cfr.small_group_matches_published), True)
    a.check("feature-set robustness: peeled ARI",
            "cluster_feature_robustness",
            round(float(cfr.peeled_ari_vs_published), 2), 0.97, 0.005)
    fc = a.table("flip_cells")
    a.check("flip cells: cities covered", "flip_cells", len(fc), 67)
    a.check("flip cells: mean sensitive share", "flip_cells",
            round(float(fc.sensitive_pop_share.mean()), 3), 0.158, 0.0005)
    a.check("flip cells: min", "flip_cells",
            round(float(fc.sensitive_pop_share.min()), 3), 0.052, 0.0005)
    a.check("flip cells: max", "flip_cells",
            round(float(fc.sensitive_pop_share.max()), 3), 0.361, 0.0005)
    env = a.table("typology_share_envelope")
    hh = env[env["class"] == "HH"]
    a.check("typology envelope: cities covered", "typology_share_envelope",
            hh.city.nunique(), 67)
    a.check("typology envelope: mean HH width", "typology_share_envelope",
            round(float((hh["max"] - hh["min"]).mean()), 3), 0.019, 0.0005)
    a.check("typology envelope: max HH width", "typology_share_envelope",
            round(float((hh["max"] - hh["min"]).max()), 3), 0.057, 0.0005)
    dss = a.table("deprivation_sensitivity_summary")
    a.check("deprivation envelope: cities covered",
            "deprivation_sensitivity_summary", dss.city.nunique(), 67)
    curv_hh = dss[(dss.axis == "curvature") & (dss.target == "share_HH")]
    thr_hh = dss[(dss.axis == "threshold") & (dss.target == "share_HH")]
    a.check("threshold dominates curvature on HH (ratio)",
            "deprivation_sensitivity_summary",
            round(float(thr_hh.width.median() / curv_hh.width.median())), 21,
            1)
    fs_hh = dss[(dss.axis == "form_swap") & (dss.target == "share_HH")]
    a.check("HH envelope: curvature median width (pp)",
            "deprivation_sensitivity_summary",
            round(float(curv_hh.width.median()), 3), 0.014, 0.0005)
    a.check("HH envelope: form-swap median width (pp)",
            "deprivation_sensitivity_summary",
            round(float(fs_hh.width.median()), 3), 0.007, 0.0005)
    a.check("HH envelope: threshold median width (pp)",
            "deprivation_sensitivity_summary",
            round(float(thr_hh.width.median()), 3), 0.298, 0.0005)
    curv_gini = dss[(dss.axis == "curvature")
                    & (dss.target == "gini_everyday")]
    a.check("curvature moves gini_everyday (median width)",
            "deprivation_sensitivity_summary",
            round(float(curv_gini.width.median()), 2), 0.24, 0.005)

    # ---- internal consistency across tables -------------------------------
    a.check("cityplane HH mean == envelope baseline mean",
            "cityplane vs typology_share_envelope",
            round(float(hh.baseline.mean()), 4),
            round(float(plane.compounding_pop_share_50.mean()), 4), 5e-4)
    a.check("descriptives population == cityplane",
            "cities_descriptives vs cityplane",
            int(desc.population.sum()), int(round(plane.population.sum())),
            67)
    a.check("every city has a per-city map",
            "figures/cities",
            sum((data.parent / "figures" / "cities" / f"{c}.png").exists()
                for c in plane.city), 67)
    return a.report()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA,
                    help="paper-pack data directory")
    args = ap.parse_args()
    if not args.data.exists():
        print(f"no such directory: {args.data}", file=sys.stderr)
        return 2
    return run(args.data)


if __name__ == "__main__":
    raise SystemExit(main())
