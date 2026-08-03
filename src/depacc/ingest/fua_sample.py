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


# --------------------------------------------------------------------------- #
# F.2 — the region x size stratified draw (the full sample)                   #
# --------------------------------------------------------------------------- #
def draw_region_strata(fuas: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The full-sample draw: 4 macro-regions x 4 size strata, seeded.

    Deterministic given ``city_definition.region_strata`` (seed, regions,
    pins) and the FUA population table, so the committed
    ``config/full_sample.csv`` is exactly reproducible. Rules, in order:

    1. **Pins** (pilot cities + validity probes) enter first and consume
       their cell's slots.
    2. **Country coverage**: every region-member country with an eligible
       FUA appears at least once (its largest) — the rule that guarantees
       e.g. EL and PT presence, which a pure random-within-region draw
       silently dropped.
    3. Cells fill to ``per_cell``: largest FUA first when the cell is still
       empty, then seeded random draws. DE+FR are capped (``max_de_fr``,
       the census-EMP gap, plan §5.7).
    4. Empty ``>5M`` cells (only the West and South have FUAs that large)
       backfill into their region's 1-5M cell.
    5. ``post_pins`` (reviewer pins) are appended AFTER the draw so they
       never perturb the seeded sequence.

    Countries without a Geofabrik extract mapping are excluded (reported).
    """
    import random

    from depacc.ingest.osm import GEOFABRIK_COUNTRY

    rs = cfg["city_definition"]["region_strata"]
    bounds = [float(b) for b in rs["strata_bounds"]] + [float("inf")]
    labels = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        def _fmt(v):
            return f"{v / 1e6:g}M" if v >= 1e6 else f"{v / 1e3:g}k"
        labels.append(f"{_fmt(lo)}-{_fmt(hi)}" if hi != float("inf")
                      else f">{_fmt(lo)}")
    region_of = {cc: rg for rg, ccs in rs["regions"].items() for cc in ccs}

    univ = []
    dropped_cc = set()
    for r in fuas.dropna(subset=["population"]).itertuples():
        cc, pop = r.country, float(r.population)
        if cc not in region_of or pop < bounds[0]:
            continue
        if cc not in GEOFABRIK_COUNTRY:
            dropped_cc.add(cc)
            continue
        idx = next(i for i, (lo, hi) in enumerate(zip(bounds[:-1], bounds[1:]))
                   if lo <= pop < hi)
        univ.append(dict(fua_code=r.fua_code, name=r.name, country=cc,
                         population=int(pop), region=region_of[cc],
                         stratum=labels[idx]))
    if dropped_cc:
        print(f"draw: countries without a Geofabrik mapping excluded: "
              f"{sorted(dropped_cc)}")

    by_cell: dict[tuple, list] = {}
    by_cc: dict[str, list] = {}
    by_code = {}
    for u in univ:
        by_cell.setdefault((u["region"], u["stratum"]), []).append(u)
        by_cc.setdefault(u["country"], []).append(u)
        by_code[u["fua_code"]] = u

    rng = random.Random(int(rs["seed"]))
    target = int(rs["per_cell"])
    max_de_fr = int(rs.get("max_de_fr", 12))
    sample, taken = [], set()
    de_fr = 0

    def _add(u, why):
        nonlocal de_fr
        sample.append({**u, "why": why})
        taken.add(u["fua_code"])
        if u["country"] in ("DE", "FR"):
            de_fr += 1

    for code, why in (rs.get("pins") or {}).items():
        if code in by_code and code not in taken:
            _add(by_code[code], str(why))
    for cc in sorted(by_cc):
        if not any(s["country"] == cc for s in sample):
            _add(max(by_cc[cc], key=lambda u: u["population"]),
                 "country coverage (largest)")

    order = [(rg, st) for rg in rs["regions"] for st in labels]
    shortfall = {}
    for key in order:
        cand = sorted(by_cell.get(key, []), key=lambda u: -u["population"])
        have = sum(1 for s in sample if (s["region"], s["stratum"]) == key)
        free = [u for u in cand if u["fua_code"] not in taken]
        if not have and free:
            _add(free.pop(0), "largest in cell")
            have += 1
        while have < target and free:
            pool = [u for u in free
                    if not (u["country"] in ("DE", "FR") and de_fr >= max_de_fr)]
            if not pool:
                break
            u = pool[rng.randrange(len(pool))]
            free.remove(u)
            _add(u, "seeded draw")
            have += 1
        if have < target:
            shortfall[key] = target - have

    top = labels[-1]
    mid = labels[-2]
    for (rg, st), n in shortfall.items():
        if st != top:
            continue
        free = sorted([u for u in by_cell.get((rg, mid), [])
                       if u["fua_code"] not in taken],
                      key=lambda u: -u["population"])
        for _ in range(n):
            if not free:
                break
            u = (free.pop(0) if rng.random() < 0.5
                 else free.pop(rng.randrange(len(free))))
            _add(u, f"backfill (no {top} FUA in {rg})")

    for code, why in (rs.get("post_pins") or {}).items():
        if code in by_code and code not in taken:
            _add(by_code[code], str(why))

    out = pd.DataFrame(sample)
    reg_order = {rg: i for i, rg in enumerate(rs["regions"])}
    st_order = {st: i for i, st in enumerate(labels)}
    out = out.sort_values(
        ["region", "stratum", "population"],
        key=lambda s: (s.map(reg_order) if s.name == "region"
                       else s.map(st_order) if s.name == "stratum"
                       else -s),
    ).reset_index(drop=True)
    print(f"draw: {len(out)} cities, {out.country.nunique()} countries, "
          f"DE+FR {int(out.country.isin(['DE', 'FR']).sum())}")
    return out


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
