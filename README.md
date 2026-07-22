# depacc — potential-deprivation accessibility equity across European cities

A reproducible, config-driven pipeline measuring infrastructure accessibility
across European cities through the lens of **deprivation**, contrasting
**everyday-service access** against **emergency capability**:

- **Everyday services** (GP, pharmacy, supermarket, school, green space —
  chosen, repeated, substitutable): a potential/gravity measure. The effective
  deprivation time is a **soft-minimum** over reachable facilities of travel
  time inflated by a **2SFCA congestion factor** (supply capacity vs demand
  competition); deprivation = DLF(effective time).
- **Emergency capabilities** (emergency-department hospitals, ambulance
  stations — non-substitutable, time-critical): **nearest-facility** travel
  time only; deprivation = convex DCF(nearest time).

The deprivation function *is* the impedance function of a gravity model run in
the opposite direction — increasing and convex in travel time — with all
functional forms and parameters **transferred from the literature** via config
(`config/deprivation.yaml`; the pipeline refuses to run while parameters are
null placeholders and its error names the paper each value must come from).

The **central output** is the *relationship* between the two surfaces:

1. **Cell-level co-location** — a population-weighted bivariate typology
   (everyday hi/lo × emergency hi/lo) mapping *compounding* deprivation;
2. **City-level divergence** — each city as a point in an
   everyday-vs-emergency plane (e.g. Gini vs Gini), off-diagonal spread;
3. **Trajectory** — cities ordered along the size gradient, testing whether
   everyday and emergency deprivation co-evolve or diverge with city size.
   This is **space-for-time, cross-sectional inference** (after Musso et al.,
   PNAS 2026): trajectories are read from the cross-sectional city-size
   gradient, never from observed temporal change. There is deliberately no
   longitudinal component.

## Two-tier data architecture

| | Tier 1 (continental) | Tier 2 (deep dive) |
|---|---|---|
| Cities | all Eurostat-OECD FUAs above config threshold | DE, NL, FR, UK, Nordics + reliable-GTFS cities |
| Population | GHS-POP 100 m; Eurostat Census 2021 1 km | + DE Zensus 2022 100 m, NL CBS 100 m, FR INSEE Filosofi 200 m, UK LSOA+IMD |
| Facilities | OSM (completeness-benchmarked per country) | same |
| Modes | walk + car (harmonised, OSM) | + public transit (r5py + R5 + GTFS) |

## Install

```bash
uv venv .venv && uv pip install -p .venv/bin/python -e ".[dev]"     # core + tests
uv pip install -p .venv/bin/python -e ".[full]"                     # full geospatial/routing stack
```

`r5py` (Tier-2 transit routing) requires a **JDK 21** Java runtime.

## Run

```bash
depacc validate --city hamburg          # config sanity check
depacc run --city hamburg               # full pipeline: ingest → access →
                                        # deprivation → divergence → equity → viz
depacc run --city hamburg --stage access
depacc make-city --fua-code DE002F --name Hamburg --country DE   # codes from `depacc list-fuas`
                                        # generate a Tier-1 fast-path config
depacc cross                            # cross-city clustering + size gradient
depacc sensitivity                      # deprivation-assumption robustness sweep
pytest                                  # unit tests (no downloads needed)
```

### Per-city outputs (`data/derived/<city>/`)

Beyond the composite deprivation surfaces and the compounding map, each run
writes the **intermediary evidence** and **city-level indicators**:

- `accessibility_by_service.csv` / `accessibility_by_regime.csv` +
  `figures/accessibility_by_service.png` — per-infrastructure travel-time
  accessibility (facility counts, pop-weighted median/p90 minutes, shares
  beyond policy thresholds, unreachable share). Deprivation-function-free.
- `figures/percentile_{everyday,emergency}.png` — the population-weighted rank
  surfaces the co-location split actually cuts (bridge the magnitude maps and
  the class map).
- `figures/compounding_map_{50,75}.png` — median-split and acute-compounding
  maps, each with the class **population shares** on the legend. Note the map
  is area-weighted while the shares are population-weighted (methods §4.1).
- `sensitivity/<city>_deprivation_sensitivity.csv` +
  `figures/sensitivity_deprivation.png` — how the result moves with the
  deprivation-function curvature (Gins move; the rank-based typology does not)
  and with the "high" threshold. See methods §7a.
- `cityplane_row.csv` — the one-row city indicator sheet (Ginis, ρ,
  `divergence_gap`, compounding/Jaccard shares, level features).

## Running on GitHub (no local setup)

Two dispatch workflows run everything on GitHub's runners; results come back
as downloadable artifacts on the run page:

- **Actions → "depacc — run one city"** — type a city id (`hamburg`,
  `koeln`, `demo`); installs Python + JDK 21, caches raw downloads per city,
  uploads `depacc-<city>` (surfaces, typology, equity tables, figures).
- **Actions → "depacc — Tier-1 many-city batch"** — a JSON list of city ids
  and/or `"FUA_CODE,Name,CC; …"` triplets for cities with no config yet
  (generated on the fly). One parallel job per city on the fast path, then a
  collect job merges every city into `cityplane.csv`, runs `depacc cross`,
  and uploads `depacc-cross-city`.

## Accumulating results across runs (the `depacc-results` branch)

Every workflow run appends its per-city summaries to an orphan
**`depacc-results`** branch (small CSVs only — no raw data), so separate
runs build one growing cross-city dataset instead of each seeing only its own
cities:

```
depacc-results
├── cities/<city>/cityplane_row.csv      one-row city summary
│                 typology_summary.csv    compounding population shares
│                 equity_indices.csv      weighted mean / Gini / CI
│                 equity_regressions.csv  density + SES gradients
└── cross/        cityplane.csv, cityvector*, scaling.csv,
                  regime_slope_difference.csv, size_gradient.csv, figures/
```

On each run the collect step (batch) or the single-city job imports every
previously persisted city, runs `depacc cross` over the **union**, and pushes
the refreshed `cross/` outputs back — a rebase-retry loop makes concurrent
runs safe (`tools/persist_and_push.sh`). Synthetic fixtures (`demo`) are never
persisted. To read the accumulated study, check out `depacc-results` or open
`cross/` in it; the `depacc-cross-city` artifact on the batch run mirrors it.

## Two routing engines (the many-city bypass)

| | `r5` (Tier-2 reference) | `friction` (Tier-1 fast path) |
|---|---|---|
| Travel times | R5 street/transit routing | least-cost paths over Weiss et al. (2020) friction surfaces |
| Modes | walk, car, transit | walk, car |
| Facilities | .pbf + pyrosm | small Overpass API queries |
| Downloads per city | 0.5–2 GB (.pbf, GTFS) | a **few MB** (WCS raster window + JSON) |
| Needs Java | yes (JDK 21) | no |
| Resolution | street-level | ~1 km, harmonised Europe-wide |

Set `routing.engine: friction` + `sources.facilities: overpass` in a city
config (or use `depacc make-city`, which does both). Tier-2 r5 runs
cross-check whether the coarse engine changes city rankings (methods.md §7).

No raw data is committed; everything under `data/` is reproduced by the ingest
stage with cached downloads and JSON provenance sidecars (URL, SHA-256,
timestamp, licence). See `data/README.md` for every source, licence,
resolution and native CRS, and `methods.md` for every modelling choice and the
literature source of every parameter.

## Repository layout

```
config/            defaults + services + deprivation functions + per-city YAML
src/depacc/
  ingest/          cached downloaders + provenance logging
  quality/         OSM completeness benchmarking per country
  access/          travel-time matrices (walk/car everywhere; +transit Tier 2)
  deprivation/     DLF/DCF forms · soft-min reducer · 2SFCA congestion · surfaces
  divergence/      bivariate typology · city-level everyday-vs-emergency plane
  equity/          weighted mean · Gini · concentration index · regressions
  cityvector/      per-city features · clustering · size-gradient trajectory
  viz/             maps and cross-city figures
tests/             unit tests on the model mathematics (synthetic fixtures)
data/              (gitignored) raw + derived data, reproduced by ingest
docs/              static results site
```

## Note on hosting

This is a standalone repository, extracted with full commit history from the
subproject where it was originally developed (a development branch of
`tinacomes/DisasterAI`) via `git subtree split`.

To finish repository setup: enable GitHub Pages from `docs/`, connect the
repository to Zenodo via the GitHub–Zenodo integration before tagging the first
release (this yields a DOI; `CITATION.cff` is already in place), and configure a
DVC remote for the heavy derived artefacts (`dvc remote add -d <name> <url>`).

## Licence

MIT for code. Derived data redistributed with releases: CC-BY-4.0, with
attribution to JRC/GHSL, Eurostat/GISCO, © OpenStreetMap contributors (ODbL),
national statistical offices and transit agencies. See `LICENSE` and
`data/README.md`.
