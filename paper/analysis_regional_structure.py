#!/usr/bin/env python3
"""Regional structure of the city indicators (revision round 2, R9).

Three additive analyses on the shipped 67-city tables, no re-derivation of
any indicator:

1. nested variance decomposition of each indicator into between-region,
   between-country-within-region and within-country sums of squares;
2. dispersion by region (sd, IQR, MAD) with a Fligner-Killeen test at the
   city level (anti-conservative reference) and a country-permutation p
   for the same statistic (whole countries permuted across regions, region
   country-counts held fixed, as in depacc.cityvector.inference);
3. the regional contrasts re-run without the five emergency-desert
   capitals, with the same country-permutation test.

Plus the South everyday-Gini split listed by country. Reads
docs/paper-pack/data/, writes four CSVs back into it.

    cd paper && python3 analysis_regional_structure.py
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats

PACK = pathlib.Path(__file__).resolve().parent.parent / "docs/paper-pack/data"
SEED = 20260803
N_PERM = 10_000
INDICATORS = ["spearman_rho", "gini_everyday", "gini_emergency",
              "divergence_gap", "compounding_pop_share_50",
              "compounding_intensity", "mean_emergency"]
REGIONS = ["North", "West", "South", "CEE"]


def load() -> pd.DataFrame:
    d = pd.read_csv(PACK / "cities_descriptives.csv")
    main = pd.read_csv(PACK / "cityvector_clustered.csv")
    peeled = pd.read_csv(PACK / "cityvector_clustered_peeled.csv")
    grade = pd.Series("covered", index=d["city"], dtype=object)
    small = peeled["cluster_kmeans"].value_counts().idxmin()
    grade[peeled.loc[peeled["cluster_kmeans"] == small, "city"]] = "partial desert"
    small = main["cluster_kmeans"].value_counts().idxmin()
    grade[main.loc[main["cluster_kmeans"] == small, "city"]] = "desert"
    d["coverage_grade"] = d["city"].map(grade)
    assert d["coverage_grade"].value_counts().to_dict() == {
        "covered": 48, "partial desert": 14, "desert": 5}
    d["log_mean_emergency"] = np.log(d["mean_emergency"])
    return d


# ------------------------------------------------------------- 1. nested SS
def nested_decomposition(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ind in INDICATORS:
        y = d[ind].astype(float)
        gm = y.mean()
        ss_tot = ((y - gm) ** 2).sum()
        rm = d.groupby("region")[ind].transform("mean")
        cm = d.groupby("country")[ind].transform("mean")
        ss_region = ((rm - gm) ** 2).sum()
        ss_country = ((cm - rm) ** 2).sum()
        ss_within = ((y - cm) ** 2).sum()
        rows.append({
            "indicator": ind, "n_cities": len(d),
            "n_countries": d["country"].nunique(),
            "share_between_regions": ss_region / ss_tot,
            "share_between_countries_within_region": ss_country / ss_tot,
            "share_within_country": ss_within / ss_tot,
            "share_country_level_total":
                (ss_region + ss_country) / ss_tot,
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------ 2. dispersion
def _fligner(values: pd.Series, groups: pd.Series) -> float:
    samples = [values[groups == g].values for g in REGIONS
               if (groups == g).sum() > 1]
    return float(stats.fligner(*samples).statistic)


def dispersion(d: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    countries = d.groupby("country")["region"].first()
    for ind in INDICATORS:
        y = d[ind].astype(float)
        obs = _fligner(y, d["region"])
        p_city = float(stats.fligner(
            *[y[d["region"] == g].values for g in REGIONS]).pvalue)
        labels = np.asarray(countries.values, dtype=object).copy()
        hits = 0
        for _ in range(N_PERM):
            rng.shuffle(labels)
            reg = d["country"].map(pd.Series(labels, index=countries.index))
            if _fligner(y, reg) >= obs:
                hits += 1
        p_perm = (hits + 1) / (N_PERM + 1)
        row = {"indicator": ind, "fligner_statistic": obs,
               "p_fligner_city_anticonservative": p_city,
               "p_permutation_countries": p_perm}
        for g in REGIONS:
            v = y[d["region"] == g]
            row[f"sd_{g}"] = v.std(ddof=1)
            row[f"iqr_{g}"] = v.quantile(.75) - v.quantile(.25)
            row[f"mad_{g}"] = float(stats.median_abs_deviation(v))
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------- 3. without the deserts
def _anova_f(values: pd.Series, groups: pd.Series) -> tuple[float, float]:
    samples = [values[groups == g].values for g in groups.unique()]
    res = stats.f_oneway(*samples)
    return float(res.statistic), float(res.pvalue)


def _perm_p(cm: pd.Series, cr: pd.Series, rng: np.random.Generator) -> float:
    obs, _ = _anova_f(cm, cr)
    labels = np.asarray(cr.astype(str).values, dtype=object).copy()
    hits = 0
    for _ in range(N_PERM):
        rng.shuffle(labels)
        F, _ = _anova_f(cm, pd.Series(labels, index=cm.index))
        if F >= obs:
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def regional_without_deserts(d: pd.DataFrame,
                             rng: np.random.Generator) -> pd.DataFrame:
    sub = d[d["coverage_grade"] != "desert"]
    rows = []
    for ind in INDICATORS:
        F_city, p_city = _anova_f(sub[ind], sub["region"])
        cm = sub.groupby("country")[ind].mean()
        cr = sub.groupby("country")["region"].first()
        F_c, p_c = _anova_f(cm, cr)
        rows.append({
            "outcome": ind, "n_cities": len(sub),
            "n_countries": len(cm),
            "F_city": F_city, "p_city_anova_anticonservative": p_city,
            "F_country_means": F_c, "p_country_anova": p_c,
            "p_permutation_countries": _perm_p(cm, cr, rng),
            "median_CEE": sub.loc[sub.region == "CEE", ind].median(),
            "median_rest": sub.loc[sub.region != "CEE", ind].median(),
            "note": "five desert capitals excluded; countries permuted "
                    "across regions",
        })
    return pd.DataFrame(rows)


# ------------------------------------------------ 4. South split by country
def south_split(d: pd.DataFrame) -> pd.DataFrame:
    s = d[d["region"] == "South"].sort_values("gini_everyday",
                                              ascending=False)
    return s[["city", "name", "country", "population", "gini_everyday",
              "mean_everyday", "coverage_grade"]]


def main() -> None:
    d = load()
    rng = np.random.default_rng(SEED)
    dec = nested_decomposition(d)
    dec.to_csv(PACK / "regional_variance_decomposition.csv", index=False)
    disp = dispersion(d, rng)
    disp.to_csv(PACK / "regional_dispersion.csv", index=False)
    nod = regional_without_deserts(d, rng)
    nod.to_csv(PACK / "inference_regional_no_deserts.csv", index=False)
    south = south_split(d)
    south.to_csv(PACK / "south_everyday_gini_by_country.csv", index=False)
    grade_region = pd.crosstab(d["region"], d["coverage_grade"])
    grade_region.to_csv(PACK / "coverage_grade_by_region.csv")
    pd.set_option("display.width", 200)
    print(dec.round(3).to_string(index=False))
    print(disp[["indicator", "fligner_statistic",
                "p_fligner_city_anticonservative",
                "p_permutation_countries"] +
               [f"sd_{g}" for g in REGIONS]].round(4).to_string(index=False))
    print(nod[["outcome", "n_cities", "p_country_anova",
               "p_permutation_countries", "median_CEE",
               "median_rest"]].round(4).to_string(index=False))
    print(south.round(3).to_string(index=False))
    print(grade_region)


if __name__ == "__main__":
    main()
