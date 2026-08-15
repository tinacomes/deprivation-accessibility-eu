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
| Population | GHS-POP 100 m (analysis grid) | same |
| Demographics / SES | Eurostat Census 2021 1 km (age < 15 / ≥ 65, employment, foreign-born where published; **broadcast** onto the 100 m grid — `ses_census_*`) | + DE Zensus 2022 100 m, NL CBS 100 m, FR INSEE Filosofi 200 m, UK LSOA+IMD (native resolution — `ses_<layer>_*`) |
| Facilities | OSM (completeness-benchmarked per country) | same |
| Modes | walk + car (harmonised, OSM) | + public transit (r5py + R5 + GTFS) |

## Install

```bash
uv venv .venv && uv pip install -p .venv/bin/python -e ".[dev]"     # core + tests
uv pip install -p .venv/bin/python -e ".[full]"                     # full geospatial/routing stack
```

`r5py` (the primary r5 routing engine) requires a **JDK 21** Java runtime.

## Run

```bash
depacc validate --city hamburg          # config sanity check
depacc run --city hamburg               # full pipeline: ingest → access →
                                        # deprivation → divergence → equity → viz
depacc run --city hamburg --stage access
depacc make-city --fua-code DE002F --name Hamburg --country DE   # codes from `depacc list-fuas`
                                        # generate a Tier-1 fast-path config
depacc cross                            # cross-city clustering + size gradient
                                        # + inference, vulnerability synthesis,
                                        # deprivation-vs-access contrast
depacc sensitivity                      # deprivation-assumption robustness sweep (Layers 1/2)
depacc sensitivity --layer access --city hamburg   # accessibility sweep (Layer 3) from cached OD
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
  deprivation-function curvature (Ginis move; the rank-based typology does not)
  and with the "high" threshold. See methods §7a.
- `sensitivity/<city>_access_sensitivity.csv` +
  `sensitivity/<city>_access_flip_cells.png` — the Layer-3 **accessibility**
  sweep (`--layer access`): how the HH share, coupling ρ and Ginis move as the
  soft-min κ, 2SFCA γ, catchment bandwidth, `k_nearest`, unreachable treatment
  and everyday **mode set** vary — recomputed from the cached OD, no re-routing.
  For Hamburg, `sensitivity/hamburg_access_acceptance.csv` ranks each knob
  against the threshold axis.
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
├── cities/<city>/  cityplane_row.csv           one-row city summary
│                   typology_summary_*.csv      compounding population shares
│                   equity_*.csv                mean/Gini/CI, SES gradients,
│                                               vulnerability strata, coverage
│                   accessibility_by_*.csv      deprivation-free travel times
│                   figures/                    percentile + compounding maps
├── cross/          cityplane.csv, cityvector*.csv (+ _clustered, _peeled)
│                   scaling.csv, size_gradient.csv, regime_slope_difference.csv
│                   inference_*.csv             country-clustered/permutation/
│                                               TOST/paired/influence tests
│                   cluster_null*.csv           clustering diagnostics
│                   vulnerability*.csv          cross-city strata synthesis
│                   deprivation_vs_access.csv, desert_access_contrast.csv,
│                   scaling_by_grade.csv        deprivation-vs-access contrast
│                   cities_descriptives.csv     per-city appendix table
│                   figures/                    all cross-city figures
├── sensitivity/    <city>_deprivation_sensitivity.csv, rank_agreement.csv,
│                   specification_curve.csv/.png, flip_cells.csv, envelopes
└── validation/     engine cross-check tables/figures (E.1), QQ curves (E.4)
```

Browse it on GitHub:
<https://github.com/tinacomes/deprivation-accessibility-eu/tree/depacc-results>
— or locally: `git fetch origin depacc-results && git worktree add
../depacc-results origin/depacc-results`. The headline numbers, the
reading guide for every statistical test, and the glossary live in
[`docs/results-headlines.md`](docs/results-headlines.md).

On each run the collect step (batch) or the single-city job imports every
previously persisted city, runs `depacc cross` over the **union**, and pushes
the refreshed `cross/` outputs back — a rebase-retry loop makes concurrent
runs safe (`tools/persist_and_push.sh`). Synthetic fixtures (`demo`) are never
persisted. To read the accumulated study, check out `depacc-results` or open
`cross/` in it; the `depacc-cross-city` artifact on the batch run mirrors it.

## Two routing engines

| | `r5` (PRIMARY, every tier) | `friction` (sensitivity variant) |
|---|---|---|
| Travel times | R5 street routing (+ transit for Tier-2 deep-dives), reverse-routed facilities→cells | least-cost paths over Weiss et al. (2020) friction surfaces |
| Modes | walk, car (+ transit, Tier 2) | walk, car |
| Downloads per city | 0.5–5 GB .pbf, osmium-clipped to the FUA | a **few MB** (WCS raster window + JSON) |
| Needs Java | yes (JDK 21) | no |
| Resolution | street-level | ~1 km, harmonised Europe-wide |
| Cost per city | ~30–60 min (network build + minutes of routing) | minutes |

Facilities come from small Overpass API queries under **both** engines
(`sources.facilities`) — the engine choice never changes the facility set.
r5 was promoted from Tier-2 reference to primary after the engine cross-check
showed the friction error is city-specific and therefore uncorrectable
(methods.md §5, §7.1); run the friction sensitivity direction with
`depacc engine-check --city <id> --engine friction`.

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
