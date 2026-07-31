"""Tier-1 city sampling from the harmonised FUA universe.

`list_fuas` loads the GISCO URAU FUA layer and joins FUA populations from a
CSV (config `city_definition.fua_population_csv`; columns fua_code,
population — compile from Eurostat Urban Audit population tables
(urb_lpop1) or by summing GHS-POP over each FUA polygon with
depacc.ingest.ghs). `sample_cities` applies the config sampling mode:

  - "all_eu_fua":  every FUA above `fua_size_threshold`;
  - "stratified":  within `stratified_countries`, up to `per_stratum` cities
                   per population stratum (`strata_bounds`), largest first —
                   the fast route to a cross-city figure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

#: Eurostat Urban Audit "population on 1 January by age groups and sex —
#: functional urban areas" (urb_lpop1), bulk TSV via the dissemination API.
#: This is the declared F.1 source for FUA populations (plan §3 F.1).
URB_LPOP1_URL = ("https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/"
                 "data/urb_lpop1?format=TSV")
URB_LICENCE = "CC BY 4.0 (© European Union, Eurostat, urb_lpop1)"

#: Total population on 1 January (the headline Urban Audit population code).
_POPULATION_INDICATOR = "DE1001V"


def list_fuas(cfg: dict, root: Path) -> pd.DataFrame:
    import geopandas as gpd

    from depacc.ingest.boundaries import URAU_FUA_URL, URAU_LICENCE
    from depacc.provenance import download

    raw = root / cfg["output"]["raw_root"] / "boundaries"
    path = download(URAU_FUA_URL, raw / "URAU_RG_100K_2021_3035_FUA.geojson",
                    licence=URAU_LICENCE)
    fuas = gpd.read_file(path)
    code_col = next(c for c in ("URAU_CODE", "urau_code", "FUA_CODE") if c in fuas.columns)
    name_col = next((c for c in ("URAU_NAME", "urau_name", "FUA_NAME") if c in fuas.columns),
                    code_col)
    out = pd.DataFrame({
        "fua_code": fuas[code_col].astype(str),
        "name": fuas[name_col].astype(str),
        "country": fuas[code_col].astype(str).str[:2],
    })
    pop_csv = cfg["city_definition"].get("fua_population_csv")
    if pop_csv and (root / pop_csv).exists():
        pops = pd.read_csv(root / pop_csv)
        out = out.merge(pops[["fua_code", "population"]], on="fua_code", how="left")
    else:
        out["population"] = pd.NA
        if pop_csv:
            print(f"NOTE: {pop_csv} not found — populations missing; build it "
                  f"with `depacc build-fua-population` (F.1).")
        else:
            print("NOTE: no fua_population_csv configured; populations missing — "
                  "compile from Eurostat urb_lpop1 or GHS-POP sums before sampling.")
    return out


# --------------------------------------------------------------------------- #
# F.1 — the FUA population table (config/fua_population.csv)                  #
# --------------------------------------------------------------------------- #
def _parse_urb_lpop1(text: str,
                     indicator: str = _POPULATION_INDICATOR) -> pd.DataFrame:
    """Parse the Eurostat bulk TSV into one row per spatial code.

    The bulk format: first column is the comma-separated dimension tuple with
    a ``\\TIME_PERIOD`` suffix on the last dimension name (e.g.
    ``freq,indic_ur,cities\\TIME_PERIOD``), remaining columns are years whose
    cells hold ``value``, ``value flag`` (e.g. ``123456 e``) or ``:`` for
    missing. For each code the LATEST year with a numeric value is kept —
    Urban Audit reporting years differ by country, so a fixed year would drop
    whole countries.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0].split("\t")
    dim_names = header[0].split("\\")[0].split(",")
    years = []
    for cell in header[1:]:
        m = re.search(r"\d{4}", cell)
        years.append(int(m.group(0)) if m else None)
    code_idx = dim_names.index("cities")
    indic_idx = dim_names.index("indic_ur")
    rows = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        dims = cells[0].split(",")
        if dims[indic_idx] != indicator:
            continue
        best = None
        for year, raw in zip(years, cells[1:]):
            if year is None:
                continue
            m = re.match(r"^\s*(\d+(?:\.\d+)?)", raw)
            if not m:
                continue  # ":" or flag-only cell
            if best is None or year > best[0]:
                best = (year, float(m.group(1)))
        if best is not None:
            rows.append({"code": dims[code_idx],
                         "year": best[0], "population": best[1]})
    return pd.DataFrame(rows, columns=["code", "year", "population"])


def _to_fua_code(code: str) -> str | None:
    """Map an urb_lpop1 spatial code onto a URAU 2021 FUA code.

    Recent vintages carry the F code directly (``DE002F``); older vintages
    used LUZ codes with L/L1/L2 suffixes on the same country+number root
    (``DE002L2`` -> ``DE002F``). City (…C), greater-city (…K…) and national
    aggregate codes are NOT FUAs and return None.
    """
    if re.fullmatch(r"[A-Z]{2}\d{3,4}F", code):
        return code
    m = re.fullmatch(r"([A-Z]{2}\d{3,4})L\d?", code)
    if m:
        return m.group(1) + "F"
    return None


def build_fua_population(cfg: dict, root: Path, out_csv: Path) -> pd.DataFrame:
    """F.1: compile the FUA population table from Eurostat urb_lpop1, keyed and
    cross-checked against the URAU 2021 FUA universe.

    Writes ``out_csv`` with columns fua_code, name, country, population, year
    (`list_fuas` consumes only fua_code + population; the rest is provenance
    for a human reader) and returns the table. Coverage against the URAU layer
    and any stale urb_lpop1 codes with no URAU FUA are printed, so a run log
    documents exactly what the sampler can and cannot see.
    """
    from depacc.provenance import download

    raw = root / cfg["output"]["raw_root"] / "boundaries"
    path = download(URB_LPOP1_URL, raw / "urb_lpop1.tsv", licence=URB_LICENCE)
    parsed = _parse_urb_lpop1(path.read_text(encoding="utf-8"))
    parsed["fua_code"] = parsed["code"].map(_to_fua_code)
    parsed = parsed.dropna(subset=["fua_code"])
    # An F-coded and a legacy L-coded series can map to the same FUA; keep the
    # most recent observation.
    parsed = (parsed.sort_values(["fua_code", "year"])
                    .drop_duplicates("fua_code", keep="last"))

    fuas = list_fuas(cfg, root)[["fua_code", "name", "country"]]
    joined = fuas.merge(parsed[["fua_code", "population", "year"]],
                        on="fua_code", how="left")
    matched = joined.population.notna()
    print(f"fua-population: {int(matched.sum())}/{len(joined)} URAU FUAs "
          f"matched from urb_lpop1"
          + (f" (observation years {int(joined.year.min())}–"
             f"{int(joined.year.max())})" if matched.any() else ""))
    unmatched = joined[~matched]
    if len(unmatched):
        print(f"{len(unmatched)} URAU FUAs with no urb_lpop1 population "
              f"(excluded from the sampler until filled, e.g. from GHS-POP "
              f"sums):")
        print(unmatched[["fua_code", "name", "country"]].to_string(index=False))
    stale = sorted(set(parsed.fua_code) - set(fuas.fua_code))
    if stale:
        print(f"{len(stale)} urb_lpop1 series match no URAU 2021 FUA "
              f"(superseded codes, dropped): {stale}")

    result = joined[matched].copy()
    result["population"] = result["population"].round().astype("int64")
    result["year"] = result["year"].astype(int)
    result = result.sort_values("fua_code").reset_index(drop=True)
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_csv, index=False)
    print(f"wrote {out_csv} ({len(result)} FUAs)")
    return result


def sample_cities(fuas: pd.DataFrame, cfg: dict, per_stratum: int = 2) -> pd.DataFrame:
    cd = cfg["city_definition"]
    threshold = float(cd["fua_size_threshold"])
    fuas = fuas.dropna(subset=["population"])
    fuas = fuas[fuas.population >= threshold]
    mode = cd["city_sample_mode"]
    if mode == "all_eu_fua":
        return fuas.sort_values("population", ascending=False).reset_index(drop=True)
    if mode != "stratified":
        raise ValueError(f"Unknown city_sample_mode '{mode}'")
    fuas = fuas[fuas.country.isin(cd["stratified_countries"])]
    bounds = list(cd["strata_bounds"]) + [float("inf")]
    picks = []
    for country, group in fuas.groupby("country"):
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            stratum = group[(group.population >= lo) & (group.population < hi)]
            picks.append(
                stratum.sort_values("population", ascending=False).head(per_stratum)
            )
    return (pd.concat(picks, ignore_index=True)
            .sort_values("population", ascending=False)
            .reset_index(drop=True))
