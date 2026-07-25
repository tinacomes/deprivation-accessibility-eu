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
