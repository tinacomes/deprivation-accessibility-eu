"""OSM facility completeness per country.

Benchmarks OSM counts of registry-comparable services (default: hospital,
pharmacy) against national registry counts, producing a completeness table

    country, service, osm_count, registry_count, completeness_ratio,
    facilities_per_100k (intrinsic density metric)

Registry counts are supplied as a CSV (config `quality.registry_counts_csv`,
columns: country, service, registry_count, source, year) compiled from
national sources (e.g. DE Krankenhausverzeichnis, national pharmacy
chambers) — each row's `source` is kept in the output so the table is
auditable. Where no registry row exists the ratio is NaN and only the
intrinsic density metric (facilities per 100k inhabitants vs the sample
median) is reported.

`filter_cities` restricts a Tier-1 city sample to countries at or above
`quality.completeness_threshold` (population-weighted mean ratio over the
benchmark services).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def build_country_count_query(country: str, rules: list[dict],
                              timeout_s: int = 600) -> str:
    """Overpass QL counting every element matching ``rules`` inside one
    country (ISO3166-1 area at admin_level 2). ``out count`` returns totals
    only — a few bytes for a country-wide answer."""
    from depacc.ingest.overpass import _rule_clause

    clauses = "".join(f"nwr{_rule_clause(rule)}(area.country);" for rule in rules)
    return (f"[out:json][timeout:{timeout_s}];"
            f'area["ISO3166-1"="{country}"]["admin_level"="2"]->.country;'
            f"({clauses});out count;")


def parse_count_payload(payload: dict) -> int:
    """Total element count from an Overpass ``out count`` response."""
    for el in payload.get("elements", []):
        if el.get("type") == "count":
            return int(el.get("tags", {}).get("total", 0))
    return 0


def osm_country_count(country: str, rules: list[dict], cfg: dict) -> int:
    """Country-wide OSM count for one benchmark service, via the same
    mirror-rotating Overpass client the facility extraction uses."""
    from depacc.ingest.overpass import _endpoints, _post_overpass

    query = build_country_count_query(country, rules)
    resp, endpoint = _post_overpass(query, _endpoints(cfg), timeout=650)
    total = parse_count_payload(resp.json())
    print(f"  osm[{country}]: {total} elements for {rules} (via {endpoint})")
    return total


def run_completeness(cfg: dict, root: Path, countries: list[str],
                     out_dir: Path | None = None) -> pd.DataFrame:
    """E.2 driver: build and write the per-country completeness table.

    For every country: one Overpass count per benchmark service (tag rules
    from ``quality.benchmark_osm``), joined against the hand-compiled registry
    counts (``quality.registry_counts_csv`` — each row carries its source, so
    the table is auditable) and the intrinsic facilities-per-100k metric.
    Writes ``completeness_<CC>.csv`` per country under ``out_dir`` (default
    ``data/derived/quality``) and returns the combined table.
    """
    q = cfg.get("quality", {}) or {}
    services = list(q.get("benchmark_services", []))
    benchmark_osm = q.get("benchmark_osm", {}) or {}
    out_dir = Path(out_dir) if out_dir else root / cfg["output"]["root"] / "quality"

    registry = None
    reg_csv = q.get("registry_counts_csv")
    if reg_csv and (root / reg_csv).exists():
        registry = pd.read_csv(root / reg_csv)
    else:
        print(f"NOTE: no registry counts at {reg_csv!r} — ratios will be NaN "
              f"and only the intrinsic density metric is reported")

    rows = []
    for country in countries:
        for service in services:
            rules = benchmark_osm.get(service)
            if not rules:
                print(f"WARNING: no quality.benchmark_osm rules for "
                      f"'{service}'; skipped")
                continue
            rows.append({"country": country, "service": service,
                         "osm_count": osm_country_count(country, rules, cfg)})
    osm_counts = pd.DataFrame(rows, columns=["country", "service", "osm_count"])
    pop = pd.Series(q.get("country_population", {}) or {}, dtype=float)
    table = completeness_table(osm_counts, pop, registry)

    out_dir.mkdir(parents=True, exist_ok=True)
    for country, block in table.groupby("country"):
        path = out_dir / f"completeness_{country}.csv"
        block.to_csv(path, index=False)
        print(f"wrote {path}")
    score = country_completeness(table)
    for country, s in score.items():
        print(f"completeness[{country}]: score {s:.3f} "
              f"(threshold: {q.get('completeness_threshold')})")
    return table


def completeness_table(
    osm_counts: pd.DataFrame,
    country_population: pd.Series,
    registry_counts: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the per-country completeness table.

    ``osm_counts``: columns country, service, osm_count.
    ``country_population``: inhabitants per country code.
    ``registry_counts``: columns country, service, registry_count[, source, year].
    """
    table = osm_counts.copy()
    pop = country_population.reindex(table.country).to_numpy()
    table["facilities_per_100k"] = table.osm_count / pop * 1e5
    if registry_counts is not None and not registry_counts.empty:
        table = table.merge(
            registry_counts, on=["country", "service"], how="left", validate="1:1"
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            table["completeness_ratio"] = table.osm_count / table.registry_count
    else:
        table["registry_count"] = np.nan
        table["completeness_ratio"] = np.nan
    med = table.groupby("service")["facilities_per_100k"].transform("median")
    table["density_vs_sample_median"] = table.facilities_per_100k / med
    return table


def country_completeness(table: pd.DataFrame) -> pd.Series:
    """Mean completeness ratio per country over the benchmark services;
    falls back to the intrinsic density metric where no registry exists."""
    ratio = table.groupby("country")["completeness_ratio"].mean()
    intrinsic = table.groupby("country")["density_vs_sample_median"].mean()
    return ratio.fillna(intrinsic)


def filter_cities(cities: pd.DataFrame, table: pd.DataFrame,
                  threshold: float | None) -> pd.DataFrame:
    """Restrict a city sample (needs a `country` column) to countries whose
    completeness score meets `threshold`. threshold=None disables filtering.
    Always reports what was dropped."""
    if threshold is None:
        return cities
    score = country_completeness(table)
    ok = score[score >= threshold].index
    dropped = cities[~cities.country.isin(ok)]
    if len(dropped):
        print(f"completeness filter (>= {threshold}): dropping "
              f"{len(dropped)} cities in {sorted(dropped.country.unique())}")
    return cities[cities.country.isin(ok)].copy()
