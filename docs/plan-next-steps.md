# Hamburg run review and next-steps plan

Status: reviewed against run [29920161315](https://github.com/tinacomes/deprivation-accessibility-eu/actions/runs/29920161315)
(first successful full Hamburg run, friction fast path, 49 min wall time) and the
code at `5a4ad66`. This document is (1) a results review, (2) a critical code
review, and (3) an implementation plan for the next iteration, organised in
workstreams (A–F) with concrete files and acceptance criteria.

---

## 1. What the Hamburg run says

Headline numbers (`cities/hamburg/cityplane_row.csv` on `depacc-results`,
stage logs of the run):

| indicator | value | reading |
|---|---|---|
| FUA population | 3.16 M, 176 137 populated 100 m cells | |
| mean everyday deprivation (DLF) | 0.205 | core well below the 15-min inflection |
| gini everyday / emergency | 0.602 / 0.621 | both high; see caveats below |
| divergence gap (gini_em − gini_ev) | 0.020 | regimes nearly equally unequal |
| Spearman ρ (everyday vs emergency pct) | 0.384 | moderate positive coupling |
| HH share @ p50 / @ p75 | 30.8 % / 11.6 % | vs 25 % / 6.25 % under independence |
| pop beyond 15 / 30 min everyday (walk) | 19.6 % / 13.7 % | the 13.7 % is mostly the *unreachable-capped* mass, see §2.2 |
| pop beyond 30 min emergency (car) | 0.005 % | essentially universal <30-min car access to ED/ambulance |
| everyday unreachable (30-min walk cutoff) | gp 12.1 %, pharmacy 12.5 %, supermarket 8.0 %, school 6.4 %, green 7.0 % | the car-dependent periphery |
| facilities | gp 1591, pharmacy 610, supermarket 1199, school 1120, green 2022, ED hospital 27, ambulance 124 | plausible orders of magnitude for the FUA |
| curvature sensitivity | gini_ev range **0.233**, gini_em range 0.176 across the k/t0/λ sweep; typology shares move 0.0000 | see §2.4 — this is the central sensitivity finding |

Substantive reading: within-Hamburg emergency access by car is near-universal
and fast (median 3.9 min to an ED, p90 14.4 min); the emergency *inequality*
(Gini 0.62, p90/p50 = 6.6) is inequality between "very fast" and "extremely
fast", not between served and unserved. Everyday walk access splits the FUA
into a well-served core (median effective times 2–7 min) and a ~12 % periphery
with no walkable GP/pharmacy at all. The positive ρ and HH = 31 % > 25 % say
the two deprivations co-locate in the periphery — but the two "high" sets are
qualitatively different things (walk deserts vs relatively-slower-car-access),
which is exactly the asymmetry the mode choice per regime builds in. That
should be stated in methods, and walk+car everyday is a needed sensitivity
(Workstream C).

### 1.1 A typology accounting identity that must be documented

With population-weighted percentile surfaces cut at their own quantile q, the
marginals are fixed at (1−q) "high" per regime (up to ties). Hence:

- at p50: HL = LH = 0.5 − HH and LL = HH — **the whole 4-class share table has
  one degree of freedom (the HH share)**. Hamburg's "balanced split"
  (30.7/19.2/19.2/30.8) is therefore mechanical symmetry, not a finding; the
  informative content is HH = 30.8 % vs 25 % independence.
- at p75: HL = LH = 0.25 − HH, LL = 0.5 + HH (observed 61.6/13.4/13.4/11.6 ✓).

methods.md §4.1 currently reads "a balanced split" as if informative — fix.
The *map* retains full spatial information; the share *table* does not. The
headline scalars should be HH share (+ Jaccard, ρ), and the plan adds a
continuous compounding measure (Workstream D) so the result does not hinge on
one threshold.

---

## 2. Critical code review

### 2.1 Bugs / mismatches (fix first — Workstream A)

1. **Persist filename mismatch.** `tools/persist_results.py` `SUMMARY_FILES`
   lists `typology_summary.csv`, but divergence writes
   `typology_summary_50.csv` / `_75.csv` (`src/depacc/divergence/pipeline.py:47`).
   Result: typology shares are silently never persisted to `depacc-results`
   (verified: absent from the branch). Also missing from persistence:
   `accessibility_by_service.csv`, `accessibility_by_regime.csv`, and the
   `data/derived/sensitivity/` tables — the run's most reusable outputs.
2. **~35 min of the 49-min run computes unused OD matrices.**
   `access/matrices.py:62` loops every service × every `routing.modes`, but the
   deprivation stage consumes only `regimes.<regime>.modes` per service
   (walk for everyday, car for emergency). The five everyday×car matrices
   (5.3 M pairs each; green_space,car alone took 13 min) and two
   emergency×walk matrices are dead weight. Restrict to the union of modes of
   the regime(s) each service belongs to. This is the single biggest
   cost lever for the many-city batch.
3. **Unreachable cap uses the global 120-min cutoff, not the per-mode cutoff.**
   Matrices are truncated at `max_time_min_by_mode` (walk 30, car 60), but
   `_apply_unreachable_policy` caps unreachable cells at
   `routing.max_time_min` = 120 (`deprivation/pipeline.py:51`). A cell at a
   31-min walk jumps to t = 120. Consequences visible in the outputs:
   `pop_p90_time_min` = 120.0 for gp and pharmacy in
   `accessibility_by_service.csv` (an artifact, not a travel time); the
   `t_regime_*` distribution is bimodal (0–30, then a 120 spike); level
   features `pop_share_beyond_everyday_30` ≈ unreachable share; and the
   everyday Gini partially measures the size of the capped mass. Fix: cap at
   the *effective per-mode cutoff* for the regime (min over the regime's
   modes' cutoffs is wrong when modes differ — use the cutoff of the mode
   whose matrix the cell exhausted; simplest correct rule: cap at
   `max(max_time_min_by_mode[m] for m in regime modes)`), and in the
   accessibility summary report quantiles on *reachable* cells only, with the
   unreachable share as its own column (it already exists). Make the cap
   value an explicit sensitivity axis (§C).
4. **`catchment.congestion_factor` is called without `reference_weights`**
   (`deprivation/surfaces.py:106`) although the docstring and config promise a
   demand-weighted median reference. Currently the unweighted median of R_j is
   used. Either pass each facility's weighted demand or fix the docs; prefer
   passing weights.
5. **Artifact bloat**: 167 MB is mostly `od_*.parquet`. After (2) it shrinks;
   also consider excluding OD matrices from the uploaded artifact (keep in the
   Actions cache only) so many-city artifacts stay small.

### 2.2 Methodological caveats surfaced by the run

- **The everyday Gini conflates three things**: the DLF curvature (sensitivity
  range 0.233!), the capped-unreachable mass, and genuine spatial inequality.
  It is the y-axis of the "central result" city plane, so this must be tamed:
  report alongside it a deprivation-function-free inequality measure per
  regime (Gini of the *travel time* `t_regime_*` on reachable cells, or of the
  percentile-free level shares), and lean on rank-agreement across cities
  (already designed, needs ≥ 3 cities) before reading the plane's geometry.
- **Walk-only everyday at 1 km friction resolution.** A 30-min walk is
  ~2.4 km ≈ 2 pixels of the Weiss walking surface; sub-pixel times for the
  100 m cells inside one pixel are near-identical, so intra-core variation is
  quantised. Fine for city-level indicators; do not over-read the everyday
  percentile map's fine structure. The r5 cross-check (Workstream E) bounds
  this.
- **2SFCA demand truncation**: demand for R_j only accumulates over the
  k_nearest = 30 retained pairs per cell. With gaussian bandwidth 15 min this
  is nearly complete, but state it in methods §2.1 and include k_nearest in the
  Layer-3 sweep.

### 2.3 What is sound

Spot-checked and correct: the softmin log-sum-exp (NaN-aware, bounds match the
docstring), the weighted Gini covariance form, the weighted ECDF with proper
tie handling in `standardize/surface.py`, the scale-state guard system (no
bypass found; typology genuinely cannot see raw magnitudes), the NaN-
renormalising composite mean, the flip-cell logic, and the p50/p75 double
reporting. The zero-anchored logistic and the Box-Cox validation are also fine.

### 2.4 Sensitivity harness: what exists vs what is missing

Exists and worked in this run: Layer 1 curvature sweep (11 variants) with the
correct headline — *typology invariant by construction, Ginis move a lot* —
plus the threshold sweep (0.40–0.75) and flip-cells. Missing:

- Layer 2 form-swap is configured but inert (alternative specs have null
  params).
- Layer 3 (the axis that *can* move ranks: kappa, gamma, bandwidth, k_nearest,
  mode set, supply model, unreachable policy) is documented but not
  implemented — and the run proves it is the only axis that matters spatially.
- Cross-city rank agreement returned NaN (needs ≥ 3 cities) — expected;
  becomes meaningful with the pilot sample (Workstream F).

---

## 3. Implementation plan (for the next coding iteration)

### Workstream A — correctness fixes (do first, small)

1. Fix `SUMMARY_FILES` to persist `typology_summary_*.csv` (glob),
   `accessibility_by_service.csv`, `accessibility_by_regime.csv`; add a
   `sensitivity/` passthrough for `<city>_deprivation_sensitivity.csv`,
   `rank_agreement.csv`, `flip_cells.csv`, `typology_share_envelope.csv`
   (files: `tools/persist_results.py`; test: `tests/test_persist.py`).
2. Compute OD matrices only for (service, mode) pairs consumed by the
   service's regime (`access/matrices.py`; derive the needed set from
   `regimes.*.modes` ∪ any modes named in the sensitivity accessibility axis
   so Layer-3 variants stay cheap). Acceptance: Hamburg re-run drops to
   ~15 min with identical `surfaces.parquet`.
3. Cap-at-cutoff fix + reachable-only quantiles in `access/summary.py`
   (§2.2 item 3). Report both `pop_p90_time_min_reachable` and
   `unreachable_pop_share`. Update `methods.md` §2.4.
4. Pass `reference_weights` (facility weighted demand) into
   `congestion_factor`.
5. `methods.md` §4.1: replace the "balanced split" reading with the
   accounting identity of §1.1 above; declare HH share, Jaccard and ρ the
   informative scalars.

### Workstream B — deprivation-function sensitivity, completed (question a)

The run answers half of question (a): *the co-location result does not need a
curvature sensitivity analysis* (rank-invariance is structural), while the
plane axes (Ginis) do, and the "high" threshold does. Remaining work:

1. **Activate Layer 2 (form swap)** with anchor-calibrated parameters, not
   invented ones: calibrate the alternative everyday Box-Cox to the same
   g(15) = 0.5·g(45) anchors as the logistic, and the alternative emergency
   exponential to the same g(60)/g(45) ≈ 1.66 clinical-threshold ratio used
   for λ = 1.8 (document the anchor equations in `config/deprivation.yaml`
   `alternatives.*.note`). This tests *form*, holding the anchors fixed —
   the honest counterpart of "form transferred, curvature calibrated".
2. **Add a travel-time-based inequality column** to the city row
   (`gini_t_everyday`, `gini_t_emergency` on reachable `t_regime_*`), so the
   city plane can be drawn in a deprivation-function-free variant. Files:
   `divergence/cityplane.py`, `cityvector/features.py`.
3. **Report the curvature envelope on the plane**: error bars (min–max Gini
   across curvature variants) per city point in `viz` — this is the honest
   way to draw the plane given the 0.23 spread.

### Workstream C — accessibility-assumption sensitivity (Layer 3, the axis that moves ranks)

Implement `depacc sensitivity --layer access` operating from cached inputs:

1. Cheap variants (re-run deprivation stage only, from saved OD parquets —
   no re-routing): `softmin.kappa` ∈ {0.1, 0.25, 0.5, 1, 2}, `catchment.gamma`
   ∈ {0, 0.25, 0.5, 1}, bandwidth ∈ {10, 15, 20} walk, `k_nearest` ∈ {10, 30}
   (subset the saved k = 30 OD), nearest-only vs softmin (κ→∞), unreachable
   cap value, and **everyday modes walk vs walk+car** (car ODs exist once A.2
   keeps the ones a declared variant needs). Each variant: recompute
   `t_regime_*` → percentiles → typology → HH share, ρ, Ginis, flip-cells vs
   baseline. Store as `sensitivity/<city>_access_sensitivity.csv` and a
   flip-cell map figure.
2. Expensive variants (per-variant re-routing; defer until the pilot sample
   exists): friction vs r5 engine (Workstream E does this for Hamburg),
   transit inclusion for Tier-2.
3. Acceptance: for Hamburg, a table showing which Layer-3 knobs move the HH
   share / ρ by more than the threshold axis does (expectation from §1: the
   everyday mode set will dominate everything else).

### Workstream D — population vulnerability (question b)

Two levels, matching the two-tier design:

1. **EU-harmonised (all cities): Eurostat Census 2021 1 km grid.** New
   `ingest/census.py` fetching the GISCO census-grid layers (already the
   declared Tier-1 demographics source in `config/defaults.yaml`) and joining
   onto cells by 1 km grid id: population by broad age (share < 15, share ≥ 65),
   employment share, foreign-born share where published. Prefix `ses_census_*`.
   These flow automatically into the existing `equity/pipeline.py` (it picks up
   every `ses_*` column) — but extend the concentration-index column picker to
   accept an explicit `equity.ses_rank_column` config key instead of the
   name-substring heuristic at `equity/pipeline.py:31`.
2. **National fine grids (Tier 2): activate the DE Zensus 2022 path for
   Hamburg.** The loader (`ingest/ses.py`) is done; what is missing is
   (i) concrete per-layer download URLs under `sources.ses.urls` in
   `config/cities/hamburg.yaml` (resolve the exact zensus2022.de zip URLs at
   implementation time and record them — the provenance sidecar captures
   them; do not guess), (ii) un-gating the SES fetch on the friction fast
   path (the gate added in `2e80594` skips SES for friction runs — make it
   conditional on `sources.ses.urls` being present instead of on the engine),
   and (iii) a `tests/` fixture exercising `join_ses_to_cells` on a synthetic
   INSPIRE CSV.
3. **New outputs** once `ses_*` columns exist: concentration index per regime
   (already coded, currently dormant), SES gradient regressions (dormant),
   `slope_ses_*` features joining the city vector (already wired in
   `cityvector/features.py:97`), and one new cut: **vulnerability-stratified
   deprivation** — pop-weighted mean deprivation and HH share within the
   65+/low-income strata vs overall (new small function in `equity/`,
   reported in `equity_indices.csv`). Age is the layer available everywhere;
   income only in Tier-2 countries — never mix the two levels in one
   cross-city comparison.

#### Workstream D — status (implemented)

All three items above are in the code. What was built, and the three places
where the implementation deliberately departs from the plan text:

**D.1 — EU-harmonised census, all cities.** `ingest/census.py` fetches the
GISCO census-2021 1 km grid, parses INSPIRE `GRD_ID` in both published
spellings (`CRS3035RES1000mN…E…` and `1kmN2696E4341`) to cell centres, reads
the continental CSV in chunks clipped to the FUA bbox (plain or zipped, `,`/`;`
sniffed, `:` → NaN), and derives `share_u15`, `share_ge65`,
`employment_share` (over the **working-age** base, not the total) and
`foreign_born_share`, prefixed `ses_census_*`. Everything file-shaped — URL,
CSV member, id column, variable codes, share definitions — is config
(`sources.census` in `config/defaults.yaml`); shares whose source columns are
absent are skipped with a note, which is how "where published" works for the
voluntary variables, and the loaded column list is printed so a first run
names the corrections needed. A missing/moved URL degrades that city's
covariates with a warning instead of killing an all-city batch.
`join_ses_to_cells` is generalised to per-layer resolutions (explicit
`resolutions=`, else the frame's `attrs["resolution_m"]`, else 100 m), so the
1 km→100 m **broadcast** and the native 100 m Zensus join happen in one pass;
`ses_resolutions.json` records per layer which columns are broadcast. The fetch
gate is now all-tier (gated on `sources.census.url`, not on tier or engine).
`equity.ses_rank_column` was already in place; the same picker problem in
`cityvector/features.py` is fixed via a *separate* key,
`equity.cityvector_ses_column` — the cross-city `slope_ses_*` feature must be
ONE variable in every city, whereas `ses_rank_column` is per-city and Tier-2
cities point it at their rent grid. The covariate actually used is recorded as
`slope_ses_column`.

> **Deviation 1 (partly verified upstream).** The implementation environment's
> egress policy blocks `gisco-services.ec.europa.eu`, so nothing about the
> published file could be confirmed at implementation time; the config carried
> the search-resolved URL plus `verify: TODO`. A subsequent run **confirmed the
> URL** and, by failing, the archive's real shape:
>
> ```
> CENSUS_INS21ES_A_IT_2021_0000_TOTAL _POPULATION.zip   nested INSPIRE delivery
> ESMS_Census_Grid 2021.pdf                             metadata
> ESTAT_Census_2021_V1-0.gpkg                           <- the attribute table
> ESTAT_OBS-VALUE-T_2021_V1-0.tiff                      total-population raster
> read.me
> ```
>
> The tabular data is a **GeoPackage**, not a CSV. `_data_member` now picks it
> by extension preference (`.gpkg` > `.geoparquet`/`.parquet` > `.csv`, never the
> raster or the docs), extracts it once, and `_load_census_geo` reads it
> bbox-filtered through the layer's spatial index, taking cell centres from
> `GRD_ID` and falling back to polygon representative points. The CSV path is
> retained because the landing page also advertises CSV and GeoParquet
> distributions. The extraction goes under `output.cache_root`, **not**
> `data/raw`: the workflows cache `data/raw` wholesale per city, so an unpacked
> continental GeoPackage there would be stored once per city and could evict the
> far more expensive OSM extracts.
>
> **Resolved: we were reading a superseded release.** V1-0 has no CSV at all and
> its GeoPackage's default layer holds only `['GRD_ID', 'OBS_VALUE_T']` — total
> population, which GHS-POP already gives us at 100 m. The current release is
> **V3** (`Eurostat_Census-GRID_2021_V3.zip`; V2-0 of 16-06-2024 is what the JRC
> 100 m disaggregation was built from), and it ships **one wide table** in
> GeoPackage, CSV, Parquet and GeoTIFF with every variable of Reg. 2018/1799.
> Config now points there, and three details from its read.me are wired in:
>
> - **`Y_1564`, not `Y_15-64`** — the employment-share denominator was wrong.
> - **The CSV member is read, not the GeoPackage** (`sources.census.member:
>   ESTAT_Census_2021_V3.csv`): same wide table, streams out of the zip in
>   chunks, no 1.3 GB extraction, no geometry stack. The extension preference
>   would otherwise take the GeoPackage. The GeoTIFF is int64 and so cannot carry
>   `GRD_ID`, `CNTR_ID` or `LAND_SURFACE` at all — never a substitute.
> - **Reserved missing-data codes `-8888` (confidential) and `-9999`
>   (unavailable)** are stripped to NaN (`sources.census.missing_values`). This
>   one is not cosmetic: left in place, `share_ge65` for a withheld cell reads
>   −17.8, which is not an outlier a reader would catch — it is an extreme
>   vulnerability score that would pull the cell into a stratum tail.
> - Rows keyed `CC_unallocated` (FR, IT, FI, BG, EL, SE, DK, NO, BE, LV, LU, SI)
>   hold population that could not be placed in any cell. They have no geometry
>   and are dropped with a reported count.
>
> The layer-enumeration and `OBS_VALUE_` unwrapping machinery built for V1-0 is
> kept: it costs nothing and covers a future release reorganising again.

> **Row-level suppression must not become a zero.** Found while wiring the
> sentinels, and it affected the *published* D.3 numbers. Both share helpers
> filled a missing count with 0 before dividing, so a cell whose elderly count is
> withheld got `share_ge65 = 0.0` — not merely lost but placed at the **bottom**
> of the distribution, inside the "low elderly share" comparison group of the
> stratification. Both now use `min_count=1`: a share summing several categories
> keeps its partial sum when some are withheld (foreign-born survives one
> confidential origin group), but a share whose categories are ALL withheld is
> NaN. Hamburg's Zensus bands are a single column each, so this was every
> suppressed cell in `equity_vulnerability.csv`.

**D.2 — DE Zensus for Hamburg.** Already landed in `e541b0c`/`d3c92a4`: the six
per-layer zensus2022 URLs are in `config/cities/hamburg.yaml`, the SES fetch is
gated on `sources.ses.urls` (not the engine), and `tests/test_ses.py` exercises
`join_ses_to_cells` on a synthetic INSPIRE CSV. This iteration adds
`sources.ses.resolution_m: 100` so the fine grid is explicitly *not* broadcast,
a collision guard if a national layer is ever named `census`, and the
member-selection fix below.

**Bug found in the persisted results: two Zensus layers joined to nothing.**
`cities/hamburg/equity_regressions.csv` on `depacc-results` carries gradients
for only three SES covariates — `ses_ownership_rate_Eigentuemerquote` and
`ses_vacancy_rate_Leerstandsquote` are absent, and
`cities/hamburg/equity_vulnerability.csv` has a dead `low_ownership` row
(`pop_share = 0.0`, every metric NaN). Cause: each destatis "Gitterdaten" zip
bundles the same theme at **10 km, 1 km and 100 m** plus a
`Datenzusatzbeschreibung` readme, and `load_inspire_csv_zip` took
`next(... endswith(".csv"))` — the first member in archive order. For those two
themes that is a coarser grid, so every 100 m join key missed and the columns
arrived all-NaN, then dropped out of the univariate regressions and emptied the
stratum without a single error. Fixed three ways: the member is selected by
resolution token (`sources.ses.resolution_m`, with per-layer `resolutions` /
`members` overrides) and a multi-grid archive with no selector now raises rather
than guessing; the resolution is re-derived from the loaded file's own
`x_mp_<res>` / `GITTER_ID_<res>` columns, cross-checked against the config, and
used for the join (the data wins over the config promise); and
`join_ses_to_cells` reports coverage instead of yielding a silent empty
covariate.

**…and the member was only half of it — the rest was a decimal comma.** With the
member fix in place the run loaded the right files and the split diagnostic
showed the true shape: ownership covered **43.9 %** of analysis cells and vacancy
**44.3 %** (comparable to household_size's 44.5 %), yet *every joined value was
missing*. Not a grid mismatch, and not credibly suppression either.

The cause: `read_csv(decimal=",")` only converts a column it can parse **entirely**
as numeric. These two themes mark suppressed cells with an en dash rather than
leaving the field empty, so the column arrived as **strings** — and
`pd.to_numeric("41,2")` is NaN. Every value in both themes was destroyed on load.
Net-rent and household-size were unaffected because their suppressed cells are
empty, which lets the whole column parse as numeric on read. `_parse_values` now
normalises a string column properly (decimal comma to point, plus percent sign
and non-breaking/thin spaces) and, if a column still yields nothing while holding
non-marker text, prints the **raw sample values** so the format is identifiable
from one run rather than inferred over three. Two follow-ups also landed:

- The coverage diagnostic conflated two different failures. It now reports
  **grid coverage** (`key.isin(layer index)`) separately from **value presence**
  (a covered cell whose value is withheld), and prints the value columns that
  were actually joined — so the next run says whether these layers miss the grid
  or are simply suppressed across the whole FUA, rather than leaving it to
  inference.
- The joined column name no longer depends on how many value columns a release
  publishes. It was `ses_<layer>_<col>` for a multi-column layer and
  `ses_<layer>` for a single-column one, so dropping the
  `werterlaeuternde_Zeichen` annotation column silently renamed
  `ses_net_rent_durchschnMieteQM` to `ses_net_rent` — breaking every config key
  that named it. Now **always** `ses_<layer>_<col>`. The same run showed the
  consequence: stale and fresh spellings coexisted in the cached
  `cells.parquet` (`ses_net_rent` beside `ses_net_rent_durchschnMieteQM`,
  `ses_household_size_werterlaeuternde_Zeichen` from before the annotation
  filter), and since `equity.ses_covariates` defaults to *every* `ses_*` column,
  the regressions would have run on last week's data under names nothing
  produces any more. Ingest now drops every `ses_*` column from the cached cells
  before re-joining, and the annotation filter also catches umlaut/`_Zeichen`
  spellings.

**National and continental sources are fetched once, not once per city.** Both
demographic levels are published as whole territories — one EU census grid, one
Zensus theme file covering all 3.09 M German 100 m cells — so a many-city batch
that fetches them per runner does the same multi-hundred-MB download N times.
`depacc prefetch --city … --city …` (new) downloads exactly the shared set —
URAU boundaries, the census grid, the national SES grids per *country*, the
GHS-POP tiles — deduplicated across the cities named, and the Tier-1 batch runs
it in a `warm` job before the matrix fans out. The raw cache is split to match:
a shared cache (`boundaries`, `census`, `ghs`, `ses`, keyed on the committed
configs, not the city) and a per-city one (`friction`, `gtfs`, `osm`,
`overpass`). That split matters beyond bandwidth: one `data/raw` cache per city
stored the continental archives once per city and could push the repo past
GitHub's 10 GB cache limit, evicting the far more expensive OSM extracts. The
split is declared in `depacc.ingest.prefetch` and regression-tested against both
workflow files so code and YAML cannot drift. National grids are additionally
clipped to the FUA bbox *as they are read*, so one city's ingest no longer puts
~18 M rows (six Zensus themes) through memory.

**D.3 — new outputs.** Concentration index, SES gradient regressions,
`slope_ses_*` and vulnerability-stratified deprivation are all live.

> **Deviation 2 (separate file).** The stratified table is written to
> `equity_vulnerability.csv`, not into `equity_indices.csv` as the plan text
> says: its grain is one row per *stratum*, not per regime, and merging two
> grains into one CSV would make both harder to read. Both files are persisted.

> **Deviation 3 (three levels, not two).** The plan's rule "age everywhere,
> income only in Tier-2" understates the hazard: Hamburg's Zensus age cut is
> under-**18** at 100 m while the census cut is under-**15** at 1 km, so a
> naive "age" level would silently pool two different variables across cities.
> Strata now carry `age_census` / `age_national` / `income_tier2`, the
> census-harmonised strata are the shipped default for every city, and Hamburg
> carries both levels side by side.

**Off-scale emergency mean (~15.76) — fixed as a reporting-units problem, not a
bug.** The unbounded escalating DCF is behaving exactly as specified: with
λ = 1.8, shift = 1, scale = 1, g(45) = (46^1.8 − 1)/1.8 ≈ 545, so a mean of
15.76 is the population-weighted average of Box-Cox-transformed minutes in
arbitrary relative units — not a value that ever belonged in [0, 1]. Nothing
downstream was wrong (every rank-based output is scale-invariant), but the
*reported* level was uninterpretable and sat in the same tables as the
everyday 0–1 DLF, which D.3's vulnerability table made prominent.
`deprivation.emergency.reference_time_min: 45.0` now divides g by g(t_ref) at
the same clinical time-to-care anchor the curvature was calibrated to, so the
surface reads in **multiples of the deprivation of arriving at the 45-minute
threshold** (1.0 = at it, > 1 = worse; escalation preserved, not bounded).
Because it is division by a positive constant, percentiles, typology, ρ,
Jaccard, both Ginis, p90/p50 and the concentration index are unchanged
*exactly* (regression-tested); only levels move — 15.76 → 0.0289, and the
vulnerability table's 15–22 → ~0.029–0.040. The Layer-2 form-swap alternative
carries the same anchor, so the two forms coincide at 1.0 and its free `scale`
cancels. `equity_indices.csv` gained a `units` column so no reported level is
scale-anonymous again. See methods.md §3c.

### Workstream E — validation

1. **Engine cross-check (highest value):** run Hamburg Tier-2 with
   `routing.engine: r5` (config already documents the switch; the pbf/GTFS
   sources are configured) and compare against the friction run: cell-level
   Spearman of `t_regime_*`, city-row indicator deltas, typology flip share.
   This bounds the 1-km-friction error for the whole Tier-1 programme. Output:
   `validation/hamburg_engine_check.csv` + a scatter figure. Budget 1–3 h of
   runner time (per the workflow's own note).
2. **OSM completeness benchmark (DE first):** implement the
   `quality/completeness.py` benchmark against national registries —
   hospitals: the federal Krankenhausverzeichnis; pharmacies: ABDA count per
   Land. Acceptance: a `quality/completeness_DE.csv` with OSM/registry ratios
   per service, wired to `quality.completeness_threshold`.
3. **External benchmark:** compare `accessibility_by_service.csv`
   (pop-weighted median walk/car minutes to supermarket, pharmacy, GP) against
   the published BBSR accessibility indicators for German municipalities —
   direction + magnitude check, documented in `docs/validation.md`.
4. **Resolution sanity check:** for ~200 random Hamburg cells, compare
   friction walk times against OSM-network walk times (r5 walk) —
   quantile-quantile plot; goes into the same validation doc.
5. **Face validation:** one page in `docs/` with the percentile +
   compounding maps annotated against known Hamburg geography (Elbe barrier,
   Harburg, the rural Kreise) — the compounding map should trace the
   commuter belt.

### Workstream F — the many-city sample (question: an interesting European sample)

Design principle: the study's central claims are (i) a size gradient and
(ii) everyday–emergency divergence types — so the sample must maximise spread
along **size** while covering the axes that plausibly *shift the coupling*:
welfare/health-system regime, morphology, and data quality.

1. **Populate the FUA universe.** Build `config/fua_population.csv`
   (fua_code, population) from Eurostat `urb_lpop1` (or GHS-POP sums over FUA
   polygons via the existing `ingest/ghs.py` fallback); wire as
   `city_definition.fua_population_csv`. The `list-fuas` workflow already
   exists to inspect the result.
2. **Stratified design (~48 cities to start):** 4 macro-regions
   (North: SE/NO/DK/FI, West: DE/NL/FR/BE/AT, South: ES/IT/PT/EL,
   CEE: PL/CZ/RO/HU/SK + Baltics) × 4 size strata
   (100–250 k, 250 k–1 M, 1–5 M, > 5 M) × ~3 cities, filling sparse cells
   (few > 5 M FUAs outside West) with extra mid-size draws. Within a stratum
   pick the largest plus one randomised draw (seeded) to avoid capital-city
   bias. Implementation: extend `ingest/fua_sample.py` with a
   `region_strata` mode; keep the existing config keys.
3. **Deliberate contrast cases (validity probes, flagged in config):** a
   shrinking city (e.g. eastern DE), a polycentric conurbation (Ruhr or
   Randstad — tests the FUA definition), a tourist-coastal city (seasonal
   population mismatch — expect anomalies), an island/peripheral city
   (Palermo class). These test whether the typology sees known structure.
4. **Data-quality gate:** run the sample only in countries with an OSM
   completeness ratio above threshold (Workstream E.2 extended beyond DE via
   OSM-intrinsic proxies where registries are hard) — and report per-country
   completeness alongside every cross-city figure.
5. **Pilot first (this unlocks the dormant machinery):** a batch of ~10:
   hamburg + koeln (existing configs) + 8 `make-city` Tier-1 configs spread
   over the four regions and three sizes. Everything ≥ 5 cities activates:
   clustering, rank-agreement, scaling regressions, cityplane geometry.
   Acceptance: `cross/` on `depacc-results` with 10 rows, clustering not
   skipped, `rank_agreement.csv` non-NaN, and a first honest look at whether
   city rankings survive the Layer-3 sweep.
6. **Runtime guard before launching the batch:** A.2 (skip unused ODs) plus a
   per-city wall-time line in the batch logs; extrapolate before scaling to
   ~48. Current Hamburg cost (~15 min post-fix, dominated by green_space car
   Dijkstra) suggests the pilot is ~2 h of runner time.

### Sequencing

1. **A** (fixes) — small, unblocks everything, re-run Hamburg to confirm
   identical science outputs (modulo the cap fix, which changes the level
   features as intended).
2. **F.1 + F.5** (pilot batch) in parallel with **B** — the pilot gives the
   multi-city sample every other analysis needs.
3. **C** (Layer-3) and **D** (vulnerability) next — both per-city, cheap on
   cached data.
4. **E** (validation) once the pilot exists; the r5 cross-check (E.1) can run
   any time.
5. Scale F to the full stratified sample only after C shows rankings are
   robust on the pilot and E.2 clears the countries involved.

---

## 4. Direct answers to the three review questions

**(a) Do the deprivation cost functions need a sensitivity analysis?**
Partly done, and the run demonstrates the crucial structural result: every
rank-based output (typology, HH share, ρ, flip-cells: 0 %) is invariant to
DLF/DCF curvature by construction, so no further curvature analysis of the
*co-location* result is needed. What still needs it: the Gini-based city plane
(curvature moves gini_ev by 0.23 — Workstream B adds the form-swap layer,
travel-time Ginis, and envelope error bars), and the genuinely consequential
assumptions, which are the *accessibility* ones (Workstream C), led by the
everyday mode set and the unreachable policy.

**(b) Population vulnerability.** Available and half-wired: the equity module
already computes concentration indices and SES gradients the moment `ses_*`
columns exist — none do today (the DE Zensus path is gated and lacks URLs;
nothing EU-wide is ingested). Plan: EU census 2021 1 km (age/employment,
harmonised, all cities) as the cross-city vulnerability layer + national fine
grids (DE Zensus for Hamburg first) for Tier-2 depth, plus
vulnerability-stratified deprivation as a new indicator (Workstream D).

**(c) Aggregation and comparison mechanisms.** Current chain: per service,
g(effective time) → **regime composite = equal-weight mean over services'
deprivation surfaces** (NaN-renormalised) → regimes meet **only** through
population-weighted percentiles (typology, ρ, Jaccard) and through
within-regime Ginis on the city plane; raw magnitudes are never combined
(guard-enforced, verified). Critique and plan: equal weights across five
correlated everyday services are an untested assumption → add leave-one-
service-out and weight-perturbation sweeps (report HH-share/ρ envelopes);
the *mean* is compensatory, which fits substitutable everyday services but
contradicts the emergency regime's own non-substitutability framing → add a
weakest-link (max) emergency composite as a variant, and consider the
physically meaningful chain-time alternative g(t_ambulance + t_hospital)
(response + transport ≈ total pre-hospital time) as the primary emergency
specification; and document the p50 typology's single degree of freedom
(§1.1) so the class-share table is not over-read. A continuous compounding
intensity (e.g. pop-weighted min(ev_pct, em_pct)) removes the threshold's
leverage on the headline number.

---

## 5. Review of run 30158804263 (Hamburg, 25 Jul 2026, commit `d200e4e`)

Run succeeded, 6.5 min wall (everything but ingest served from the derived
cache). Reviewed against the artifact and against `depacc-results` @ `6796401`.

### 5.1 What the run confirms as landed

- **A.1 persist** — `typology_summary_50/75.csv`, `accessibility_by_*.csv` and
  seven `sensitivity/` tables are all on `depacc-results`. Fixed.
- **A.3 reachability split** — the two meanings are now genuinely separate:
  `routability: 0/176137 cells have no network path`, so `unreachable_pop_share`
  is 0.00 % for every service and the old 12.1 % appears where it belongs, as
  `pop_service_deprived_share` for gp. `pop_p90_time_min_reachable` is a travel
  time again (gp 12.1 min, not 120).
- **A.4** — `congestion_factor(..., reference_weights=demand)` is passed
  (`deprivation/surfaces.py:172`).
- **B.2** — `gini_t_everyday` (0.740) / `gini_t_emergency` (0.420) are on the
  city row.
- **D.1–D.3** — the census CSV member is read and parsed
  (`['GRD_ID','T','M','F','Y_LT15','Y_1564','Y_GE65','EMP','NAT','EU_OTH','OTH',…]`),
  13 `CC_unallocated` rows dropped, the census layer joins 100 % of analysis
  cells with 94.3 % carrying a value, the stale-`ses_*`-column purge fires
  (21 columns dropped before re-joining), and the decimal-comma fix works:
  `ownership_rate` went from 0 % to **35.1 %** value presence and now carries a
  gradient (β = 0.260, n = 61 903) instead of an empty stratum.
- **Emergency units** — `weighted_mean` 0.0289 with
  `units = "DCF: multiples of g(45 min) [anchored]"`. The typology identity of
  §1.1 also checks out exactly at both cuts (p75: HL = LH = 0.25 − HH = 0.122,
  LL = 0.5 + HH = 0.628 ✓).

So **D is done** in the sense the plan meant. What follows are defects the run
*newly exposes* — two of them in the Layer-3 machinery that landed with C, and
they invalidate C's headline before E or F can build on it.

### 5.2 Defects, ranked

**(1) BLOCKER — the Layer-3 sweep evaluates a different model than the pipeline.**
The pipeline composites *deprivations*: `deprivation_everyday = Σ w_s g(t_s) / Σ w_s`
(`deprivation/pipeline.py:137`). The sweep composites *times* and then applies g
once: `RegimeSurface(g_ev(t_everyday), …)` where `t_everyday` is the weighted
mean of per-service `t_eff` (`sensitivity/access.py:312`). g is nonlinear, so
these are not the same estimator, and the sweep's own "baseline" row does not
reproduce the run:

| | pipeline | Layer-3 "baseline" |
|---|---|---|
| gini_everyday | 0.657 | 0.705 |
| gini_emergency | 0.621 | 0.603 |
| spearman ρ | 0.426 | 0.462 |
| HH @ p50 | 0.3155 | 0.3224 |

Every Layer-3 number, including the acceptance table, is measured against a
fixed point that is not the model's. Fix: build per-service deprivation inside
`everyday_t_regime` / `access_variant_targets` and take the weighted row mean of
`g(t_s)`, exactly as `deprivation/pipeline.py` does; assert in a test that the
`baseline` variant reproduces `surfaces.parquet` to within float tolerance.
Emergency has the same mismatch (it applies g to the mean of the two nearest
times rather than averaging the two deprivations) — that is why
`gini_emergency` is a constant 0.603 across the sweep instead of 0.621.

**(2) BLOCKER — "kappa is the knob that moves HH most" is a tie-handling
artifact.** `hamburg_access_acceptance.csv` reports `kappa` (HH range 0.1778)
and `everyday_mode` (0.1778 — the *same* number) as the movers. Both ranges come
from a single degenerate value: `kappa_0.1` and `everyday_modes_walk+car` each
return `share_LL = share_LH = 0.0`, `share_HL ≈ share_HH ≈ 0.4999`, i.e. **100 %
of the population classified everyday-high**, with `flip_pop_share = 0.4998`.

Two independent causes meet:

- `to_percentile` assigns each tie group the **top** of its cumulative weight
  (`standardize/surface.py:82`, "ties share the group's top cumulative weight").
  So a tie block holding ≥ 50 % of the population is labelled "high" *whatever
  its value* — including when that value is the minimum. A bottom-heavy tie
  block is the one case where the upper-inclusive rank inverts the meaning of
  the cut. Mid-rank (average) ties would place a 90 % zero-block at 0.45 → low,
  which is what "population-weighted percentile" should mean.
- The tie block is manufactured by the softmin floor. `softmin ≥ min − ln(n)/κ`,
  and `t_eff` is clipped at 0 (`deprivation/surfaces.py:184`). At κ = 0.1 with
  k_nearest = 30 the substitutability bonus is ln(30)/0.1 ≈ **34 minutes**, so
  effectively every cell in the core floors to exactly 0 for every service.
  `gini_everyday` = 0.826 at κ = 0.1 (vs 0.705 baseline) is the same fact seen
  from the other side: most of the mass is at zero.

  The walk+car variant reaches the same place by a different route: Hamburg runs
  the **friction** engine (`config/cities/hamburg.yaml:154`), whose car surface
  is 1 km, so a cell sharing its pixel with a facility gets car time 0; `min` over
  modes then zeroes ~95 % of the FUA (`gini_everyday` 0.955). That variant is
  measuring friction-raster quantisation, not the everyday mode set.

Fix, in order: (a) mid-rank ties in `to_percentile` (and a test with a >50 %
tie block); (b) guard the softmin — reject or warn on κ where `ln(k)/κ` exceeds
a fraction of the mode's cutoff, and record the clipped share per variant;
(c) drop or re-label the walk+car variant until E.1 says what the friction car
surface is worth at 100 m. Until then, **the honest reading of the Layer-3
sweep is `gamma` (ρ range 0.147) and nothing else** — every knob's ρ already
"exceeds threshold" only because the threshold axis has ρ range 0.0 by
construction (ρ is computed on percentiles, which the threshold does not touch),
so `rho_exceeds_threshold` is a vacuous test and should be dropped.

**(3) The `unreachable` sensitivity axis tests a knob that affects zero cells.**
The grid varies `policy ∈ {cap_at_max_time, exclude}` (`sensitivity/access.py:69`),
but after A.3 that policy only governs genuinely-unroutable cells, of which
Hamburg has **0** — hence the identical rows and `hh_share_range = 0.0`. The knob
that now sets the deprivation of 12–13 % of Hamburg's population is
`unreachable.finite_fill_min` (`config/defaults.yaml:238`, null → 120 min), and
it is not swept. It also leaks into the supposedly deprivation-function-free
level features: `pop_share_beyond_everyday_30` = 0.134 ≈ the gp service-deprived
share, because a cell missing one service has its composite *time* pulled toward
120. As the cross-city comparable level feature for F, that is a problem — it
reads "share missing ≥ 1 everyday service", not "share beyond 30 minutes".
Fix: sweep `finite_fill_min ∈ {60, 90, 120, 180}` as the `unreachable` axis, and
either compute the level features on per-service times with an explicit
"service-deprived" count column, or state plainly in methods that they are
composite-time features containing the fill constant.

**(4) The EU-harmonised SES covariate is dead in Germany, and fails silently
across cities.** `ses_census_employment_share` is non-null on **295** analysis
cells and constant 0.0 there — EMP is voluntary under Reg. 2018/1799 and DE did
not report it. Both regressions were correctly skipped with a NOTE (the
`37e1b10` guard doing its job). But it is the default for *both*
`equity.ses_rank_column` and `equity.cityvector_ses_column`
(`config/defaults.yaml:250,256`), and the fallback chain in
`cityvector/features.py:94-102` quietly substituted the German rent grid:
`slope_ses_column = ses_net_rent_durchschnMieteQM`. That is exactly what the
separate key was created to prevent — in a 10-city pilot each city falls back to
whatever it has, and `slope_ses_everyday` pools incommensurable betas in one
cross-city column. Fix before F.5: make the harmonised slope **NaN + a recorded
reason** when the harmonised column is unusable, never a per-city substitute;
add a coverage gate (`min_valid_share`, e.g. 0.20) so a covariate on 295 cells
never enters a regression at all; and pick the replacement harmonised covariate
— `foreign_born_share` is already ingested at 94.3 % coverage and used nowhere
(it is absent from Hamburg's `ses_covariates` allow-list).

**(5) Vulnerability ratios compare a covered subsample against the whole FUA.**
`equity_vulnerability.csv` reports `low_ownership` with
`mean_dep_everyday_ratio = 0.273` and `hh_share_gap = −0.232` — a huge effect.
But `ownership_rate` carries a value on only 35.1 % of cells, and Destatis
publishes it where there are enough dwellings, i.e. preferentially in the dense
core. The stratum is the bottom quartile of *that* subsample; the reference
(`overall`) is all 176 137 cells including the car-dependent periphery. The
ratio therefore mostly measures "cells with published tenure data are urban".
Same defect, smaller, for `low_rent` (25.3 % coverage). The census strata
(94.3 %) are unaffected. Fix: compute every stratum's ratio against the
**covered-cell** reference for that column, and add `coverage_pop_share` and `n`
columns to the table.

**(6) Minor — `vacancy_rate` is reported on 2.6 % of cells.** Grid coverage is
44.3 % but only 2.6 % carry a value, and it still produces the largest everyday
gradient in the table (β = 0.521, p = 8.6e-48, **n = 4633**). Not wrong — `n` is
reported — but it is the headline coefficient of a 2.6 % selected subsample and
needs the coverage gate of (4). Worth one check that the residual 94 % really is
Destatis suppression rather than a second parse issue: the fix diagnostic prints
raw samples only when a column yields *nothing*, and this one yields something.

### 5.3 Revised next steps

The plan's sequencing (§3) put F.1+F.5 next and E "once the pilot exists". The
run changes that: F.5 would multiply defect (4) across ten cities and would draw
its comparable level features through defect (3), while defect (2) means the
one thing C was supposed to settle — *do city rankings survive the accessibility
sweep?* — is not yet settled. Revised order:

1. **A′ — the six fixes above** (small, all in code already written; ~1 day).
   Acceptance: the Layer-3 `baseline` row reproduces `cityplane_row.csv` to
   1e-9; no variant returns a degenerate 0/0/½/½ split; `hamburg_access_acceptance.csv`
   re-read to see which knob actually moves HH once κ = 0.1 and walk+car are
   sound. Re-run Hamburg (6 min from cache).
2. **E.1 — r5 engine cross-check on Hamburg**, now the highest-value validation
   rather than the last. Defect (2) showed the friction car surface zeroes ~95 %
   of the FUA at 1 km, which is precisely the quantity E.1 was designed to bound,
   and it decides whether walk+car everyday (Workstream C's expected dominant
   knob) is even askable on the Tier-1 fast path. Runs any time, Hamburg-only,
   1–3 h of runner budget, blocks nothing.
3. **F.1 in parallel** — `config/fua_population.csv` is pure data assembly, no
   compute, no dependency on any of the above.
4. **F.5 pilot (~10 cities)** once A′ lands and F.1 exists. E.1's result feeds
   the pilot's mode-set decision but does not gate it.
5. E.2–E.5 and the full stratified F.2 sample after the pilot, unchanged.

Recommendation: **A′ then E.1**, with F.1 alongside. E before F, contrary to the
original sequencing, because E.1 answers a question the pilot would otherwise
inherit ten times over.

### 5.4 A′ — the six fixes, implemented

All six landed; the full suite passes and a demo end-to-end run plus Layer-3
sweep is clean. Per defect:

1. **Layer-3 composite.** `sensitivity/access.py` now builds the everyday
   per-service deprivations and composites them with the same weighted row mean
   the pipeline uses (`everyday_t_regime` → `everyday_regime`, returning
   deprivation, the deprivation-free composite time, and a zero-floor
   diagnostic). Emergency is read straight from `surfaces.parquet`'s
   `deprivation_emergency` rather than re-derived as `g` of the mean nearest
   time. `test_baseline_recompute_matches_pipeline` now pins **both** the
   deprivation composite and `t_regime_everyday` to the saved columns at 1e-9 —
   the acceptance criterion of §5.3.
2. **Tie handling.** `to_percentile` is mid-rank: a tie group sits at the
   midpoint of its own weight span, not the top. New tests cover a 90 % bottom
   tie block (0.45, reads low — it read 0.90 and "high" before) and the property
   §1.1's identity actually needs, that cutting at q leaves (1−q) above the cut.
   Degeneracy is now detected on its own terms: `max_tie_pop_share` in
   `standardize/`, and any variant whose largest tie block exceeds 50 % of the
   population is printed, marked `degenerate` in the per-variant table alongside
   `max_tie_everyday` / `zero_floor_pop_share`, excluded from the acceptance
   ranges, and excluded from the union flip-cell map. On the demo fixture the
   mechanism reproduces exactly as diagnosed — *κ = 0.1: a single tie block holds
   95.2 % of the population, 99.9 % floored at t_eff = 0* — and with it removed
   the top mover becomes `gamma`, as §5.2 predicted for Hamburg.
3. **`unreachable` axis.** Now sweeps `finite_fill_min` ∈ {60, 90, 180} instead
   of a policy that governs zero cells; `finite_fill` is a first-class variant
   parameter and `finite_fill_min` a column in the table. String grid entries
   still expand to policy variants for an unroutable-heavy city. The vacuous
   `rho_exceeds_threshold` column is gone (`n_variants` / `n_degenerate` replace
   it); `rho_range` is still reported as a magnitude.
4. **SES support gate.** `equity.min_covariate_valid_share` (default 0.2) gates
   every `ses_*` column — including constants — *before* anything selects one, so
   it governs the gradient covariates, the concentration-index rank column and
   the strata alike. `equity_ses_coverage.csv` (n_cells, cell_share, pop_share,
   n_distinct) is written every run and persisted to `depacc-results`.
   `equity.cityvector_ses_strict` (default true) stops the cross-city
   `slope_ses_*` from silently substituting a per-city column: a city without the
   harmonised covariate now gets no feature and a NOTE. `ses_census_foreign_born_share`
   is added to Hamburg's covariate list — at 94.3 % coverage it is the live
   candidate to replace the employment share as `cityvector_ses_column`, and the
   next run's gradient should inform that choice. **That choice is the one open
   decision left from A′** — the default still points at the dead column, which
   under strict mode means Tier-1 cities get no `slope_ses_*` until it moves.
5. **Vulnerability reference.** Each stratum now carries both references:
   `*_ratio` against the whole FUA and `*_ratio_covered` against the cells where
   its own column is published, plus `coverage_pop_share`, `n_cells` and the
   `ref_*` levels. New test: a covariate published only on the low-deprivation
   half reads 0.2 against the FUA and ~1.0 against its own support.
6. **Vacancy.** Covered by the gate (2.6 % ≪ 20 %, so it no longer supplies the
   largest everyday gradient). The SES join also gained the in-between warning
   the two existing branches missed — a layer that reaches the grid but keeps a
   value on under a quarter of the cells it covers now says so explicitly,
   instead of leaving "genuine suppression or a second parse bug?" to inference.

`methods.md` §5 (percentile transform), §6.1 (support gate, strict cross-city
covariate), §6.2 (two references) and §7 (Layer-3) are updated to match.

**Next:** re-run Hamburg (~6 min from cache) and read the corrected
`hamburg_access_acceptance.csv` and `equity_ses_coverage.csv` before choosing
between E.1 and the F pilot.

### 5.5 Verification run 30160444058 — A′ confirmed, and two results changed

Re-run on `main` at `567e194` (6.7 min). All six fixes verify on real data, and
two of them **changed a published Hamburg result**.

**Fix 1 verified exactly.** The Layer-3 `baseline` row now equals the pipeline:

| | pipeline (`cityplane_row.csv`) | Layer-3 baseline | before A′ |
|---|---|---|---|
| gini_everyday | 0.656795 | 0.656795 | 0.705 |
| spearman ρ | 0.427702 | 0.427702 | 0.462 |
| HH @ p50 | 0.315440 | 0.315440 | 0.3224 |

**Fix 2 costs the headline nothing.** Mid-rank moved the city row by
HH 0.31545 → 0.31544 and ρ +0.0017; both Ginis, both travel-time Ginis and every
level feature are bit-identical. The tie rule only bites when a tie block is
large, and Hamburg's baseline composite has none (largest block 10.1 %). So this
is correctness insurance, not a revision — the published Hamburg numbers stand.

**The corrected acceptance table, and C's actual answer.**

| knob | HH range | ρ range | degenerate |
|---|---|---|---|
| **threshold_axis** | **0.3030** | 0 | — |
| gamma | 0.0509 | 0.1686 | 0 / 3 |
| kappa | 0.0183 | 0.0558 | 1 / 4 |
| k_nearest | 0.0067 | 0.0244 | 0 / 1 |
| nearest_only | 0.0051 | 0.0174 | 0 / 1 |
| bandwidth | 0.0015 | 0.0069 | 0 / 2 |
| unreachable (finite fill) | 0.0000 | 3e-6 | 0 / 3 |
| everyday_mode | — | — | **1 / 1** |

Four things follow.

1. **No accessibility knob beats the threshold axis.** The "how high is high"
   choice moves the HH share ~6× more than the strongest accessibility
   assumption. That is Workstream C's acceptance question answered, and the
   answer is the reassuring one: the co-location result is not hostage to the
   accessibility model. It also sharpens §4(c) — the threshold is the dominant
   lever on the headline, so the continuous compounding intensity is the fix that
   matters, not more accessibility sweeps.
2. **`gamma` is the mover, as §5.2 predicted once the artifact was removed** —
   and it moves ρ a lot: 0.389 (γ=1) to 0.558 (γ=0) around a baseline 0.428. The
   reported "moderate positive coupling ρ = 0.43" should be **ρ ∈ [0.39, 0.56],
   congestion-exponent envelope**. κ, having supplied the old headline, is now
   fifth at 0.018.
3. **The finite fill is immaterial to the deprivation targets** — 60/90/180
   minutes move gini_everyday by 1.5e-5. The DLF saturates well before 60 min, so
   `finite_fill_min`'s justification in `config/defaults.yaml` is now *tested*
   rather than asserted. One caveat survives: the level features
   (`pop_share_beyond_everyday_30` = 0.134) are built from the composite
   **time**, which is fill-dependent, and the sweep reports only
   deprivation-based targets. Cheap to close by adding the level features to the
   variant table.
4. **`everyday_mode` has no reading at all.** Its only variant is degenerate —
   a tie block holding **87.9 %** of the population, with **99.0 %** floored at
   t_eff = 0. Walk+car everyday, which the plan expected to dominate Layer 3, is
   simply not askable on the friction fast path: the 1 km car surface puts a
   facility at zero minutes for almost every cell. κ = 0.1 is the other
   degenerate (65.7 % tie block, 90.3 % zero-floored). Both are now flagged and
   excluded instead of setting the headline.

   Worth noting even at baseline: **68.9 %** of Hamburg's population has t_eff = 0
   for at least one everyday service (green space, median time 0.0). Not
   degenerate — the 7-service composite de-ties it to a 10.1 % block — but it is
   the friction resolution showing through, and it is the same quantity E.1
   bounds.

**Fix 5 changed the D.3 result, and the sign flips.** With each stratum compared
against the cells where its own column is published:

| stratum | coverage | ratio vs FUA | **ratio vs covered** | HH gap vs FUA | **vs covered** |
|---|---|---|---|---|---|
| elderly_census | 0.96 | 0.890 | 0.986 | +0.035 | +0.046 |
| children_census | 0.96 | 1.081 | 1.199 | +0.055 | +0.067 |
| elderly (national) | 0.66 | 0.886 | **1.374** | +0.024 | +0.096 |
| children (national) | 0.63 | 0.946 | **1.516** | +0.036 | +0.117 |
| low_rent | 0.54 | 0.843 | **1.606** | −0.011 | **+0.114** |
| low_ownership | 0.57 | 0.273 | 0.352 | −0.232 | −0.214 |

The Tier-2 reading of the previous run — *the elderly, children and low-rent
populations experience LESS everyday deprivation than the city average* — was an
artifact of comparing a core-biased published subsample against the whole FUA.
On the correct base they experience **more** (1.37×, 1.52×, 1.61×), and
`low_rent`'s compounding gap flips from −0.011 to **+0.114**. The
census-harmonised strata (96 % coverage) barely move, so the cross-city layer was
never affected — which is exactly the argument for keeping `age_census` the
shipped default. `low_ownership` stays genuinely low on both bases.

**Fix 4: the gate works, and it leaves a hole that must be filled before F.**
`equity_ses_coverage.csv` (now persisted):

- `ses_census_employment_share`: **295 cells, 0.17 %, 1 distinct value** — gated,
  confirmed dead in DE.
- `ses_vacancy_rate_Leerstandsquote`: 4633 cells, **2.6 %** — gated; it no longer
  supplies the largest everyday gradient.
- `ses_net_rent_durchschnMieteQM`: 25.3 %, only just over the 20 % gate — and it
  is Hamburg's `ses_rank_column` for the concentration index. Worth a look.
- `ses_census_foreign_born_share`: **94.2 % coverage, 165 878 cells, 2307
  distinct** — healthy, and now regressed for the first time.

`cross/cityvector.csv` has **no `slope_ses_*` columns at all**, only
`slope_density_*`: strict mode doing its job. That is the hole. Which brings the
open decision to a head, with data:

> `ses_census_foreign_born_share` is the strongest SES-flavoured covariate in the
> everyday table — β = −0.339, **r² = 0.106 on n = 165 878**, higher r² than
> ownership (0.080), age (0.055) or net rent (0.042); emergency β = −0.254,
> r² = 0.059. On coverage and signal it is the obvious replacement for the
> employment share as `equity.cityvector_ses_column`.
>
> The caution: its sign matches net rent's (higher share → *lower* deprivation),
> so both are plausibly reading urbanity, and `slope_density_*` is already in the
> city vector as a separate feature. A country-of-birth share is also a
> composition variable rather than an SES one, and its meaning is not identical
> across European cities. Adopting it is a defensible, documented choice; the
> alternative is to accept that Tier-1 cities carry no cross-city SES gradient
> and drop `slope_ses_*` from the feature set.

### 5.6 Where this leaves E and F

C is now answered and E.1 has moved from "highest-value validation" to the thing
blocking a stated axis: the friction car surface zeroes 99 % of the FUA for
everyday services and 68.9 % of the population is already at t_eff = 0 at
baseline. Two consequences the plan did not anticipate:

- Walk+car everyday cannot be tested at all until the engine question is settled.
- **The emergency regime runs entirely on that same car surface.** Its
  facilities are sparse (27 EDs, 124 ambulance stations) so the zero-floor does
  not bite the same way, but the 1 km quantisation applies to a median-3.9-minute
  distribution, and nothing has bounded that error. E.1 covers both.

Recommended order, unchanged from §5.3 minus the now-completed A′:

1. **E.1** — r5 engine cross-check on Hamburg. Hamburg-only, 1–3 h runner, blocks
   nothing, and now answers two questions instead of one.
2. **F.1 in parallel** — `config/fua_population.csv`, pure data assembly.
3. **Settle `cityvector_ses_column`** before F.5, or the pilot ships without a
   cross-city SES gradient.
4. **F.5 pilot**, then E.2–E.5 and the full F.2 sample.

Two cheap items to fold into the next code pass: add the level features to the
Layer-3 variant table (closes the fill-dependence gap in point 3 above), and
report the ρ envelope alongside the point estimate on the city plane.

### 5.7 `cityvector_ses_column` resolved — and the silent imputation it uncovers

**Resolved: keep `ses_census_employment_share`.** The GISCO population-grids page
records EMP as missing for **two** countries only, DE and FR; the other 25 report
it. That changes the calculus completely from §5.5's framing. A cross-city
feature that is *missing* for two countries is far better than one that means
something slightly different in each — so the default stays, and DE/FR cities
carry NaN on `slope_ses_*` by design rather than by accident. No config change is
needed; what was missing was the knowledge that the gap is bounded.

`ses_census_foreign_born_share` stays where it is: a regular covariate in
Hamburg's `ses_covariates` (and the strongest everyday gradient in the table,
β = −0.339, r² = 0.106), but **not** the harmonised cross-city slope.

**Why the German Zensus employment grid is not the answer**, even if destatis
publishes one at 100 m (the six themes we configure do not include employment,
and the Zensus 2022 grid release is centred on population/household/dwelling
attributes — employment status is primarily a Gemeinde-level result there):

- *Definition.* "Erwerbstätige" and Reg. 2018/1799's `EMP` are not guaranteed to
  be the same construct — age bounds, marginal employment, self-employed,
  reference week. The regulation harmonises deliberately; a national census
  answers national needs.
- *Spatial support.* The census layer is 1 km **broadcast** onto 100 m cells; a
  Zensus layer is native 100 m. A regression coefficient's magnitude depends on
  its covariate's variance, and a broadcast covariate has systematically less
  within-city variance than a native one — so the two β are not on the same scale
  even if the concept were identical. This project already ruled on exactly this
  in Deviation 3: `age_census` (under-15 at 1 km) and `age_national` (under-18 at
  100 m) are kept as separate levels precisely so they are never pooled. Feeding
  a national grid into the harmonised column re-commits that error inside a
  single number, where nothing labels it.
- *It generalises badly.* Patching country by country ends in a column that is a
  patchwork of national definitions — the pooling failure strict mode exists to
  prevent, reached one country at a time.

If a national employment gradient is wanted, it belongs as a **separate,
level-labelled Tier-2 feature** (`slope_ses_employment_national` beside
`slope_ses_employment_census`), reusing the machinery age already uses. Not in
scope now.

**The finding this uncovered, which matters more than the decision.**
`cityvector/scaling_features.py:65` imputes any residual NaN at the scaled centre:

```python
Z = np.where(np.isfinite(Z), Z, 0.0)   # a city missing a feature -> the median
```

A feature is only *dropped* when fewer than two cities carry it, or its spread is
zero. So in a pilot where 8 of 10 cities have `slope_ses_*`, the two DE/FR cities
are not excluded from that dimension — they are placed at the sample **median**,
i.e. made to look exactly typical on a variable that was never measured for them,
and then clustered on it. That is worse than either option §5.5 was weighing, and
it is silent: the existing log line only names features that were dropped, never
cities that were imputed.

Three consequences to handle before F.5:

1. **Bound and report the imputation.** Add `cityvector.max_missing_share`
   (suggest 0.25): a feature missing for more than that share of cities is
   dropped rather than imputed, and the log names which cities were imputed on
   which features. Small change in `scaling_features.py`, plus a test.
2. **The pilot's country mix.** `city_definition.stratified_countries` is
   `["DE", "NL", "FR"]` — **two of the three are the EMP gaps** — and both
   existing city configs (`hamburg`, `koeln`) are German. As configured, the
   pilot would be blind on `slope_ses_*` for most of its cities and silently
   median-imputed there. F.5's draw needs revisiting with this in mind; the
   four-macro-region design in F.2 already fixes it if the pilot follows that
   shape rather than the current stratified-countries list.
3. **The concentration index has the same default.** `equity.ses_rank_column` is
   also `ses_census_employment_share`. Hamburg overrides it with its rent grid,
   but a Tier-1 DE or FR city with no national rent grid falls through the
   income/rent heuristic and loses the concentration index entirely. Bounded and
   now expected — it should be stated in methods §6.1 alongside the DE/FR gap
   rather than discovered per city.

### 5.8 E.1 implemented

`depacc engine-check --city <id> --engine r5` (module
`src/depacc/quality/engine_check.py`, workflow
`.github/workflows/engine-check.yml`, methods.md §7.1).

What it does: re-routes one city under an alternative engine and reports
per-regime and per-service travel-time medians/p90 with the population-weighted
Spearman between engines, the city-row indicators (both Ginis, ρ, the four class
shares) recomputed identically on each, and the typology flip share. Outputs
`validation/<city>_engine_check.csv` plus a hexbin scatter; both are now
persisted to `depacc-results` alongside the sensitivity tables.

Three design choices worth stating, because each of them is a way the check
could have quietly measured the wrong thing:

- **Facilities are inherited, not re-extracted.** Hamburg's friction config takes
  facilities from Overpass while an r5 config takes them from the .pbf. Letting
  that vary would confound engine disagreement with facility-set disagreement,
  which is E.2's separate question. The shadow run copies `cells.parquet` and
  every `facilities_*.parquet` verbatim; only the OD matrices and what follows
  are recomputed.
- **It calls `run_access` / `run_deprivation`, not a re-implementation.** The
  Layer-3 sweep shipped for one run with its own composite and therefore its own
  baseline (§5.2). A validation module that re-derived surfaces would be the same
  trap. The self-test pins it: running the check with the city's *own* engine must
  give every delta exactly zero, ρ = 1 and a 0 % flip share.
- **The shadow is nested at `data/derived/<city>/engine_<engine>/`.** A sibling
  directory would be picked up by `tools/persist_results.py`, which walks
  `data/derived/*` and treats each entry as a city, and published as a phantom
  city. Nested, it is invisible to that walk and rides in the same per-city
  derived cache as the baseline it is compared against. Divergence and equity are
  never run for it, so it cannot reach `cityplane.csv`.

Rank agreement is the headline the table is built around, not the level delta:
every output in this study is rank-based, so an engine that shifts all times by a
constant costs nothing while one that *reorders* cells invalidates the typology.
The tests assert exactly that contrast — a monotone +5 min shift gives ρ = 1 with
a 5-minute median delta and a 0 % flip share; a reversal gives ρ = −1 with no
median movement and a flip share above 50 %.

**To run it:** Actions → "engine cross-check (E.1)" → Run workflow, `city:
hamburg`, `engine: r5`. The shadow surfaces are cached, so a re-dispatch that
only re-runs the comparison is minutes; `reuse: false` forces a full re-route.
Nothing is pushed to `depacc-results` from the workflow itself — the outputs
come back as the `depacc-engine-check-hamburg` artifact.

**Runtime — the 1–3 h estimate above was wrong by roughly a factor of four**
(§5.9). It is now measured, and the workflow is built to be resumed rather than
to finish in one dispatch.

### 5.9 E.1's real cost, and why the first attempt returned nothing

Run 30164334307 was dispatched with the estimate above and produced no outputs
at all. Two separate failures, one of measurement and one of mechanism.

**Measurement.** Timestamps from that run, on Hamburg's 176 137 origins:

| phase | wall clock |
| --- | --- |
| .pbf fetch + osmium clip of 3 Geofabrik extracts + merge | ~1.3 min |
| R5 network build (`hamburg_merged.osm.pbf`) | ~12 min (inside the first matrix) |
| `gp`, walk (30 min cutoff) | ~32 min incl. the network build |
| `pharmacy`, walk | 21.5 min |
| `supermarket`, walk | 26.3 min |
| `school_primary`, walk (`school_secondary` aliases, free) | 25.9 min |
| `green_space_local`, walk (`green_space_district` aliases, free) | 35.2 min |
| **five walk services** | **~2 h 22** |
| `emergency_dept_hospital`, car (60 min cutoff) | **> 2 h 37, unfinished when the job was cancelled** |

The everyday regime is walk-only and the emergency regime is car-only, so the
two emergency services carry a 60-minute cutoff rather than 30. The R5 street
search is superlinear in the cutoff — doubling it over a road network, not a
footpath network, explores far more of the graph per origin — so each car
matrix costs multiples of a walk one. A complete Hamburg r5 cross-check is
therefore **~8–12 h, not 1–3**. That is more than the 6 h hard cap on a
GitHub-hosted job: **E.1 was never completable in a single run**, at any
timeout setting.

**Mechanism.** The job's own `timeout-minutes: 300` fired at exactly 5 h and
GitHub *cancelled* the job. A cancelled job skips post steps, so
`actions/cache` never saved — and the 2 h 22 of finished walk matrices went
with it. `depacc engine-check` had not reached `compare_engines`, so
`data/derived/validation/` did not exist, which is the whole content of the
"No files were found with the provided path" artefact warning. That warning was
the symptom; the cancellation was the disease.

**What changed.** The access stage is now resumable at two levels and stops
itself before the runner can cancel it:

- `routing.time_budget_min` / `DEPACC_ROUTING_BUDGET_MIN` (unlimited by
  default, 240 min in the workflow) makes `run_access` stop cleanly and raise
  `RoutingBudgetExhausted` while the job is still alive, so the cache *is*
  written. The CLI reports it as exit code 2 — a resumable stop, distinct from
  a failure — and refuses to run later stages, because deprivation surfaces
  built on a half-routed city would mark every unrouted cell service-deprived.
- Inside a matrix, each finished origin chunk is written to
  `od_<service>_<mode>.partial/chunk_NNNNN.parquet` and reused on re-entry.
  Whole-matrix granularity is not enough when one car matrix outlives a job.
- The workflow gives the routing step its own `timeout-minutes` *below* the
  job timeout (a step timeout fails the step, and post steps still run), always
  writes a status file into the upload path, and treats exit 2 as a notice.

So the operating procedure is: dispatch, let it stop on budget, dispatch again.
Each run is strictly forward progress. For a single-dispatch answer covering
the everyday regime only, dispatch with `modes: walk` (~2.5 h), then re-dispatch
with `modes` blank to add the emergency car regime.

One comparison bug was fixed alongside it: the travel-time medians and p90s
summarised each engine over *its own* reachable cells, which mixes a level
difference with a composition one — an engine that gives up on the far
periphery would post a lower median for that reason alone. They are now paired
on the cells both engines reach, with the composition difference reported
separately as `coverage` rows (`<item>_reachable_pop_share`).

The questions it should answer, in order of what they block:

1. Is `t_regime_emergency` rank-stable between engines? If not, `gini_emergency`
   and the divergence gap — axes of the central result — are resting on a 1 km
   raster artefact.
2. How far does the everyday walk surface move? §2.2 of this plan predicted
   intra-core quantisation at ~2 pixels per 30-min walk; this measures it.
3. Does walk+car everyday stop being degenerate under r5? If it does, the
   Layer-3 `everyday_mode` axis becomes evaluable and Workstream C's expected
   dominant knob can finally be tested.

### 5.10 E.1 answered — run 30275890587 (Hamburg, friction vs r5)

Complete in 8 minutes after reverse routing (§5.9): 27 hospital searches and
124 ambulance-station searches instead of 176 137 cell searches, 2.2 and 4.0 min
respectively. The direction approximation was validated against the 234 788
pairs the abandoned forward run had already checkpointed — **median |Δ| 1.0 min,
p90 2.0, max 8.0, mean signed +0.22 min** on an 11-minute median. R5 returns
whole minutes, so part of that 1-minute median is quantisation rather than true
asymmetry. No directional bias worth correcting for.

#### The answer, in one line

**Levels are badly wrong under friction, ranks are moderately wrong, aggregate
typology shares are robust, and cell-level class assignment is not.**

#### Levels

Population-weighted, over the cells both engines reach:

| item | friction | r5 | rel. Δ | ρ |
| --- | --- | --- | --- | --- |
| emergency median | 2.96 | 8.50 | **+187 %** | 0.881 |
| emergency p90 | 12.72 | 20.00 | +57 % | |
| everyday median | 3.95 | 6.67 | +69 % | 0.867 |
| `emergency_dept_hospital` median | 3.89 | 11.00 | +183 % | 0.890 |
| `ambulance_station` median | 1.96 | 6.00 | +207 % | 0.783 |
| `green_space_*` median | 1.23 | 5.10 | **+314 %** | 0.792 |
| `school_*` median | 3.69 | 6.68 | +81 % | **0.732** (worst) |
| `gp` median | 5.18 | 7.42 | +43 % | 0.865 |
| `pharmacy` median | 5.33 | 7.14 | +34 % | 0.838 |
| `supermarket` median | 3.30 | 5.52 | +68 % | 0.788 |

The friction surface is fast everywhere, and worst where facilities are dense —
green space (+314 %) and ambulance stations (+207 %) are exactly the services a
1 km pixel is most likely to contain, and a pixel containing a facility is a
~0-minute trip for everything inside it. This is §5.8's zero-floor, quantified.

#### Indicators

| indicator | friction | r5 | Δ |
| --- | --- | --- | --- |
| `gini_emergency` | 0.621 | 0.437 | **−0.185 (−30 %)** |
| `gini_everyday` | 0.657 | 0.545 | −0.112 (−17 %) |
| `spearman_rho` (everyday↔emergency) | 0.428 | 0.402 | −0.026 (−6 %) |
| `share_LL_50` | 0.3152 | 0.3188 | +0.4 pp |
| `share_LH_50` | 0.1848 | 0.1812 | −0.4 pp |
| `share_HL_50` | 0.1846 | 0.1791 | −0.5 pp |
| `share_HH_50` | 0.3154 | 0.3209 | +0.5 pp |
| `flip_pop_share_50` | — | **0.237** | 23.7 % of population |

The four class shares move by at most 0.5 pp while **23.7 % of the population
changes class**. Those two facts together mean the cells are swapping
*symmetrically*: the typology's aggregate composition is engine-robust, its
per-cell assignment is not. Any map of the typology is a map of the engine as
much as of the city; any cross-city comparison of the shares is defensible.

The divergence relationship itself — ρ between the everyday and emergency
percentile surfaces, the central city-plane axis — survives at 0.428 → 0.402.

#### Two artefacts in the table that are NOT findings

**Every everyday `p90_min` row reads `120.0 → 120.0, delta 0`.** That is
`max_time_min`, the `cap_at_max_time` finite fill, not agreement. A p90 of
exactly 120 means at least 10 % of the population is capped on *all five*
everyday categories under both engines — consistent with the 12–17 %
per-service `pop_service_deprived_share`, i.e. the rural commuting-zone ring is
beyond a 30-minute walk of everything. The everyday p90 comparison carries no
information and must not be quoted as robustness.

**The everyday scatter is a lattice, and the lattice is the cap.** The hexbin
shows six discrete bands on both axes at ~24-minute intervals. That is
`finite_fill / total_composite_weight = 120 / 5`: the everyday composite is a
weighted mean over five categories (gp, pharmacy, supermarket, school 0.5+0.5,
green space 0.5+0.5), so a cell cut off from *j* of them sits at ≈ 24 *j*. The
visible clusters are (friction *j*, r5 *j*) pairs, and the off-diagonal ones are
cells where the engines disagree on **how many categories are out of reach** —
not on travel time. So the everyday ρ = 0.867 is substantially a measure of
agreement on that count. The emergency panel, which has no cap in play, is the
clean and interpretable one: a dense unimodal cloud sitting almost entirely
above the 1:1 line.

That is a finding about `t_regime_everyday` as a *metric*, independent of E.1:
above the deprivation threshold it stops behaving like a travel time and starts
behaving like a count of unmet categories.

#### What this blocks, and what it does not

Safe to report from the Tier-1 friction sample:
- typology **class shares** and their cross-city variation (≤ 0.5 pp engine
  sensitivity);
- the everyday↔emergency divergence **ρ** (−6 %);
- rank-based city orderings, with the caveat that ρ = 0.73–0.89 is not a
  constant shift.

Not safe without an engine correction or an explicit caveat:
- **absolute travel times** in minutes (understated by 34–314 % by service);
- **`gini_emergency` and `gini_everyday` as levels** (−30 % and −17 %);
- **per-cell typology class**, hence any published choropleth of it.

Open question for the next iteration: `gini_emergency` is an axis of the central
city-plane result and it moves 30 % between engines on the one city where both
have been run. Either the Tier-1 Ginis get an explicit engine-error band, or the
cross-city Gini claims need a second r5 city to establish whether the −30 % is a
stable offset (correctable) or city-specific (not). One more city under E.1 now
costs ~10 minutes of runner time, so this is cheap to settle.

### 5.11 A–D completeness audit, and what run 30275890587 changes (review pass)

An independent audit of workstreams A–D against the code at `c500c1c` and the
run's own job logs (the comparison CSV is printed by the "Show the comparison"
step, so every §5.10 number was re-verified against the artifact's source
rather than trusted). Verdict first: **A–D are implemented as §5.4–§5.7
describe** — all six A′ fixes, the anchor-calibrated Layer-2 swap, the
Layer-3 sweep with degeneracy handling, the census/Zensus ingest, the support
gate, the two-reference vulnerability table, and the `max_missing_share`
imputation bound are all in the code and confirmed by runs. Four elements the
plan called for were still missing; all four are now landed:

1. **The continuous compounding intensity** (§1.1 assigned it to D; §5.5
   called it "the fix that matters"): `compounding_intensity` — pop-weighted
   mean of `min(ev_pct, em_pct)`, anchors 1/3 independent, 1/2 coupled,
   1/4 divergent — joins `cityplane_row.csv`, the coupling feature group and
   the scaling outcomes (`divergence/colocation.py`, methods §4.1).
2. **Level features per Layer-3 variant** (§5.5 point 3, §5.6): the sweep was
   computing and discarding the composite time; `pop_share_beyond_everyday_*`
   is now a per-variant column and its per-knob range joins the acceptance
   table, with the threshold axis pinned at exactly 0. The baseline test also
   pins these to the pipeline's own level features.
3. **The ρ envelope** (§5.5 point 2, §5.6): `rho_envelope` over the
   non-degenerate variants, printed by the sweep and annotated per city on
   the plane figure — "ρ = 0.43" becomes "ρ = 0.43 [0.39, 0.56]".
4. **`spearman_uncapped` in the engine check** (§5.10's own caveat about
   itself): the headline ρ = 0.867 partly measures agreement on who is capped;
   the comparison table now also reports the rank agreement with every
   fill-capped cell removed from both engines, per item.

Still deliberately open (F-scoped, unchanged from §5.7): `config/
fua_population.csv` (F.1), the pilot's country mix vs the DE/FR EMP gap, and
E.2–E.5. The §4(c) aggregation sweeps (leave-one-service-out, weight
perturbation, weakest-link emergency composite) remain unassigned to any
workstream — they should be scheduled with the pilot, where their envelopes
first become comparable across cities.

#### The "not great" intermediate results are a finding, not a failure

The E.1 numbers deserve a plain statement, because they read badly on first
contact: the comparison machinery is sound (the self-test pins same-engine
deltas to zero, the comparison is paired, the reverse-routing error is
measured at median |Δ| 1.0 min, and the §5.10 table reproduces from the logs
exactly). What the numbers say is that the **friction fast path, not the
pipeline, is the weak link**: levels understated 34–314 %, both Ginis
understated as levels, 23.7 % of people changing typology class — while the
aggregate class shares (≤ 0.5 pp), the divergence ρ (−6 %) and rank orderings
hold. §5.10's read-out stands.

#### Reverse routing changed E's economics — and possibly Tier-1's engine

The premise "friction is what makes a 48-city sample affordable" predates
reverse routing. Measured on this run, the two emergency car matrices cost
2.2 + 4.0 min as 151 facility searches; the same transpose applies to the five
walk services (600–2 000 facilities each, all past the 20× guard, and walking
is symmetric — no one-way streets), which the workflow now defaults on. A
complete r5 city is therefore roughly the R5 network build plus minutes of
routing — **~30 min, comparable to a friction run**, where §5.9 measured
8–12 h forward. Two consequences, in order:

1. **Run E.1 on a second city now** (koeln has a config; ~30 min end to end)
   to settle §5.10's open question — whether the −30 % `gini_emergency` offset
   is a stable engine bias or city-specific.
2. **If the second city confirms the offset is not stable, promote r5 to the
   Tier-1 primary engine** rather than carrying an uncorrectable caveat
   through the whole programme. At ~30 min/city the 48-city sample is ~24 h of
   runner time, parallelisable by the existing batch matrix; friction remains
   as the sensitivity variant instead of the baseline — which also un-blocks
   the walk+car everyday axis (degenerate on friction, evaluable on r5) and
   retires the zero-floor artefact (68.9 % of population at t_eff = 0) at the
   source. The decision needs the second-city evidence, not this paragraph.

### 5.12 Why run 30476375657 hung: four settings defects, not a slow pipeline

Dispatched after merging PR #16 and still inside step 11, "Ensure the baseline
surfaces exist", after 1 h 10 — never reaching the cross-check it was for.
The step timings tell the story: the shared raw cache restored in 6 s (hit),
while **both per-city caches returned in 0 s (miss)**. So the job was not
cross-checking anything; it was rebuilding a city's entire baseline from
scratch, and doing it on the slowest possible path.

**(1) The baseline-rebuild step had neither of the two guards the cross-check
step has.** `DEPACC_ROUTING_BUDGET_MIN` and `timeout-minutes` were both set
only on "Cross-check against r5". Step 11 runs plain `depacc run --stage
deprivation`, so its routing budget was unlimited and nothing could stop it
before the **job** timeout — which *cancels*, and a cancelled job skips the
`if: always()` cache saves, discarding every matrix built. That is exactly the
run-30164334307 failure §5.9 diagnosed; the fix was applied to one step and not
the other. Fixed: the baseline step now carries the budget and a 165-min
timeout, and a budget stop (exit 2) is treated as forward progress — caches
save, the cross-check is skipped, a re-dispatch resumes.

**(2) The step timeouts could not fit inside the job timeout.** 320 min for the
cross-check plus an unbounded baseline, inside a 355-min job. The arithmetic
never worked; it was simply never exercised until a cache missed. Now 165 + 165
= 330, leaving ~25 min for setup, cache saves and upload, with `budget_min`
(default lowered 240 → 150) documented as **per step**.

**(3) `config/cities/koeln.yaml` never declared `routing.engine`, so it
inherited `r5` from the defaults** — and its `modes` included `transit`. Hamburg
states `engine: "friction"` explicitly; Köln's omission meant the *baseline*
being rebuilt was a full forward-R5 three-mode Tier-2 routing, the ~47-h path
of §5.9, with no budget. Tier 2 is about the data sources, not the engine.
Fixed: Köln now mirrors Hamburg (`friction`, `["walk", "car"]`), and
`test_every_city_declares_its_routing_engine` fails any city config that omits
the engine or pairs friction with transit.

**(4) The run could not have answered anything even if it had finished.** With
Köln inheriting `r5`, an `--engine r5` cross-check compares r5 against **itself**:
every delta is zero by construction, and the job pays for a second full routing
to prove it. `run_engine_check` printed a NOTE and continued — a warning at
minute zero of a multi-hour job is not a guard. It now **raises**, naming the
fix, unless `--self-test` is passed.

One more gap closed while here: the baseline rebuild ignored reverse routing
entirely, because `--reverse-modes` is an `engine-check` flag and the baseline
goes through `depacc run`. `routing.reverse_direction` now falls back to
`DEPACC_REVERSE_MODES`, which the workflow sets on both steps.

**What this run cost, and what to do.** Nothing is recoverable from it: it will
either be cancelled at the job timeout or stopped by hand, and in both cases the
saves are skipped. Cancel it. Then, with these fixes on main, re-dispatch for
`koeln` — the baseline is friction (minutes), the r5 shadow reverses both car
and walk, and the whole cross-check is one dispatch. That is the second-city
run §5.10 asked for, and it is what decides whether the −30 % `gini_emergency`
offset is a stable engine bias or city-specific.

### 5.13 Cross-check of run 30484261519 — the Köln baseline lands; E.1's second city is now a warm dispatch

Run facts: "run one city", `koeln`, dispatched from `main` at `ea3b038` (the
§5.12 fixes, merged as PR #17), **7.3 min wall, success**, results accumulated
to `depacc-results` at `6fbddcf`. This is the friction baseline the §5.12
postmortem called for: `koeln.yaml` now pins `engine: friction`, and the run
wrote the per-city caches whose absence sent run 30476375657 into a forward-R5
baseline rebuild. To be explicit about what it is *not*: the engine cross-check
for Köln has **not** been dispatched since the fixes — this run is the setup
for it, not the answer to it.

#### What the second city row says

| indicator | Hamburg | Köln |
|---|---|---|
| gini_everyday / gini_emergency | 0.657 / 0.621 | 0.559 / 0.531 |
| spearman ρ | 0.428 | 0.448 |
| HH @ p50 | 0.3154 | 0.3237 |
| compounding_intensity | **(empty — see below)** | 0.381 |
| divergence_gap | −0.035 | −0.028 |
| pop beyond 30-min everyday | 0.134 | 0.139 |

Köln is less unequal in both regimes and slightly more coupled; the class
shares and the capped periphery mass are nearly identical. Both cities are
German friction runs, so nothing about the plane's geometry should be read yet —
`rank_agreement.csv` is still all-NaN (needs ≥ 3 cities, by design).

**Workstream C's answer replicates on city 2.** `koeln_access_acceptance.csv`:
threshold_axis HH range **0.304** (Hamburg 0.303) dominates every accessibility
knob; `gamma` is again the strongest accessibility mover (ρ range 0.164 vs
Hamburg 0.169); one κ variant degenerate, flagged and excluded. And the
per-variant level features added in §5.11 item 2 earn their keep on their first
outing: the `unreachable` axis moves the deprivation targets by ~2e-6 (§5.5
point 3 again) but moves `pop_share_beyond_everyday_30` by **0.100** — the
fill-dependence of the level features is now measured rather than asserted, and
it is material. That column must carry its fill caveat wherever it is used as a
cross-city comparable.

**SES behaves exactly as §5.7 predicted for a second German city.**
`ses_census_employment_share`: 88 cells, 1 distinct value — gated, dead in DE
again. Foreign-born and both age shares: 94.5 % coverage. `cross/cityvector.csv`
has no `slope_ses_*` column (strict mode; both cities are in the EMP gap), and
clustering ran on two cities without imputation.

#### Two gaps the run exposes

1. **Hamburg's cross-table row is stale.** `compounding_intensity` is empty for
   Hamburg in `cross/cityplane.csv` and `cityvector.csv`: the feature landed
   (§5.11) after Hamburg's last run (30160444058), and the cross tables carry
   whatever each city's last run produced. Any newly added feature silently
   NaNs for cities not re-run since — the general hazard behind this instance.
   A ~6-min cached Hamburg re-dispatch refreshes the row (and gives Hamburg its
   per-variant level features and ρ envelope too).
2. **Köln ran Tier-2 without its national SES layer.** `koeln.yaml` declares the
   Zensus provider and layers but no `sources.ses.urls`, so the URL-gated fetch
   (D.2, by design) skipped it: only the census-harmonised strata exist for
   Köln. Hamburg's six theme URLs point at *national* files already in the
   shared per-country cache, so giving Köln the same URLs is nearly free — and
   given that fix 5 flipped the sign of Hamburg's Tier-2 vulnerability reading,
   Köln should have the national strata before any Tier-2 narrative is written.

#### Next steps, in order

1. **Dispatch "engine cross-check (E.1)"** for `koeln`, engine `r5`, from
   `main` (cache scoping — the workflow header says why). The baseline restores
   from this run's cache; reverse routing covers both modes; ~30 min. This
   settles §5.10's open question — stable −30 % `gini_emergency` offset
   (correctable caveat) vs city-specific (promote r5 to Tier-1 primary,
   §5.11) — which gates the pilot's engine choice.
2. **Re-dispatch "run one city" for `hamburg`** (~6 min from cache) to de-stale
   the cross tables.
3. **F.1** (`config/fua_population.csv`) in parallel — still pure data
   assembly, still open.
4. **Add the Zensus URLs to `koeln.yaml`** (small config change, next code
   pass).
5. **F.5 pilot** after the engine decision, with the DE/FR EMP country-mix
   concern (§5.7) applied to the draw.

### 5.14 Why the Köln cross-check died at 80 min with no log: reverse routing's dense side was unchunked

Run 30526795903 (Köln, r5) failed at 09:48 after 80 minutes with the one
annotation GitHub gives a dead runner: *"The hosted runner lost communication
with the server."* The forensics identify the failure class before any log is
read: step 12 is stuck `in_progress` with no conclusion, every later step —
including the `if: always()` cache saves — is `pending`, the job log archive
404s, and the check-run output is empty. A script failure records a step
conclusion and still runs the always() saves; a step timeout does too; a job
cancellation says `cancelled`. A failure with *no* step forensics means the
runner process itself was killed — resource exhaustion, and on this job's
profile, memory. Everything the run built (NRW download, clip, R5 network,
finished matrices) went with it, because a dead runner saves no caches: the
§5.9 resumability machinery protects against *time* overruns, not against
runner death. The fix must prevent the death, not resume after it.

**The mechanism, found in `_r5_matrix`.** Two compounding facts:

1. Chunking batches the side R5 searches FROM (`origin_chunk: 5000`). Forward,
   a chunk's dense result is 5000 × ~2k facilities ≈ 10 M pairs — fine.
   Reversed, the dense side is the *other* one: a walk service with 600–2 000
   facilities fits in ONE chunk, and r5py materialises a dense
   facilities × cells frame — up to ~2 000 × ~98k ≈ 200 M pairs, with both id
   columns as Python-object strings — before the NaN drop. Multi-GB in one
   allocation.
2. The k-nearest trim ran per chunk only in the FORWARD branch; reverse parts
   were accumulated untrimmed and trimmed once after the final concat (the old
   comment argued per-chunk trimming would keep k per facility-batch — wrong:
   the chunk frame is already transposed to origin=cell, so a per-chunk trim
   keeps k per *cell*, a strict superset of the global k nearest that the
   final cross-chunk trim reduces exactly). So even with smaller chunks, held
   memory grew toward the full dense product.

On top of that, r5py's default JVM heap is 80 % of physical RAM (~12.8 GB of
the standard runner's 16), so Python held those frames in what little the JVM
left. Hamburg never hit this: its successful cross-check (30275890587) reversed
only the two emergency car services (27 + 124 facilities), and its walk
matrices came forward-routed from cache. Köln was the first city to actually
exercise reverse *walk* — §5.11's "~30 min/city" premise — at scale.

**Fixes (all landed, `test_reverse_chunks_are_capped_by_pair_budget` and
`test_reverse_resume_across_a_chunk_size_change_does_not_duplicate`):**

1. `routing.reverse_pair_budget` (default 12 M) caps the reverse chunk by
   *pairs*, i.e. chunk ≈ budget / n_cells (~120 facilities per chunk for a
   ~100k-cell FUA), bounding each dense allocation.
2. The k-nearest trim now runs per chunk in both directions, and reverse
   parts fold as they accumulate (held memory ~k × n_cells), with a
   `drop_duplicates` guard so a resumed run whose checkpoints were written
   under a different chunk size cannot double-count tied pairs.
3. The workflow writes `max-memory: 8G` to `~/.config/r5py.yml` before
   routing: if memory pressure recurs anyway, it surfaces as a Java
   `OutOfMemoryError` inside the step — a real log line, a failed step whose
   always() cache saves still run — instead of a dead runner.

**Cost model correction.** Reverse walk is now ~n_facilities/120 chunks per
service instead of one, each a bounded search + transpose; the ~30-min/city
estimate for a complete r5 city survives, but the first Köln dispatch also
re-pays the NRW download/clip/build that died with the runner. Re-dispatch is
the whole remedy: same inputs (`city: koeln`, `engine: r5`, from `main`).

### 5.15 Köln E.1 run 30535437441: completed — headline says "offset not stable", but the everyday side is under a validity hold

The re-dispatch with the §5.14 fixes **completed**: 93 min in the routing step
(NRW fetch/clip + R5 build + all seven matrices), caches saved, artifact
uploaded, and the JVM cap + pair-budget chunking held — the memory-death mode
did not recur. `koeln_engine_check.csv`, face value:

| indicator | friction | r5 | Δ | Hamburg (§5.10) |
|---|---|---|---|---|
| gini_emergency | 0.531 | 0.433 | **−18.5 %** | −30 % |
| gini_everyday | 0.559 | 0.543 | −2.8 % | −17 % |
| spearman ρ | 0.448 | 0.461 | +2.9 % | −6 % |
| class shares Δ | | | ≤ 0.64 pp | ≤ 0.5 pp |
| flip_pop_share_50 | | | 19.2 % | 23.7 % |
| emergency median | 2.59 | 8.0 | +208 % | +187 % |

Taken at face value this answers §5.10's question: the `gini_emergency` offset
is **not** a stable engine bias (−30 % vs −18.5 %; the r5 Ginis are nearly
identical across cities — 0.437/0.433 — while the friction Ginis differ by
0.09, i.e. most of the FRICTION cross-city spread on that axis is engine
artifact). Per §5.11 that finding, if it survives, argues for promoting r5 to
the Tier-1 primary engine.

**But the run also carries an anomaly that puts the everyday side on hold.**
The four REVERSE-routed walk services agree with the friction baseline far too
well: gp ρ = 0.9997 (uncapped 0.9999 on 68 557 cells), median deltas of
0.001–0.011 min; the shadow's own summary reproduces friction's per-service
medians to hundredths (gp 5.200 vs 5.181, school 2.330 vs 2.307). A 1 km
friction raster cannot rank 100 m cells against a street network at ρ = 0.9997
— Hamburg's forward-routed walk gave ρ 0.73–0.87 and +34–81 % levels. The
control group behaves: `green_space` (forward-routed under r5 — the 20× guard
declined the transpose at 17.6×) disagrees with friction exactly as expected
(3.79 vs 0.0 median, ρ 0.85), and both reversed CAR services match Hamburg's
sane pattern (+197–207 %, ρ 0.78–0.89). The anomaly isolates precisely to
{reverse × walk}, the one path that had never run before today. Code reading
so far rules out: OD inheritance (`_INHERITED` copies only cells/boundary/
network-paths/facilities), shadow-dir cache pollution (the restored derived
cache predates any engine_r5 dir), and same-file comparison (car rows differ).

**Decisive test, ready to dispatch.** `debug-od-compare.yml` (branch
`claude/engine-cross-check-status-gqavae`, temporary) restores the run's
derived cache and compares base vs shadow OD parquets pair by pair, printing
to the job log. The sharpest tell costs one column: **r5py returns whole
minutes**, so if the shadow's reversed-walk `time` values are non-integer
floats, they are friction data wearing an r5 filename; if they are integers,
they are genuinely r5 and the agreement needs a different explanation.

Until that verdict: the **emergency-side numbers (the actual E.1 question) are
probably sound** — reversed car was validated on Hamburg with a measured
asymmetry check and behaves consistently here — but the everyday rows of the
Köln table (`gini_everyday` −2.8 %, part of the 19.2 % flip share) and any
"friction is fine for walk" reading must not be quoted.
