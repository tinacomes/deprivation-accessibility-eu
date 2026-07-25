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
> **Still open — where the non-population variables live.** The next run got
> through the download and the GeoPackage (1.27 GB extracted) and reported its
> default layer as `['GRD_ID', 'OBS_VALUE_T']`: total population only, which we
> already have at 100 m from GHS-POP. Two possibilities, both now handled
> without another code change: the other variables are further **layers** of the
> same GeoPackage — the loader enumerates layers, matches their names against
> the configured codes and merges the matches on the cell centroid — or they are
> **separate per-variable downloads**, in which case they go under
> `sources.census.urls` as a `{code: url}` mapping (mirroring
> `sources.ses.urls`) and are merged the same way. Which one applies is a single
> command:
>
> ```
> python -c "import pyogrio,sys; print(pyogrio.list_layers(sys.argv[1]))" \
>   data/cache/census/ESTAT_Census_2021_V1-0.gpkg
> ```
>
> Codes are also matched through the GISCO `OBS_VALUE_` wrapping (`T` resolves
> `OBS_VALUE_T`), with a guard that refuses an ambiguous match rather than
> collapsing several shares onto total population. **Until the age variables
> actually load, no city has a census vulnerability layer — confirm before
> publishing any census-based number.**

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

**…and the member was only half of it.** With the fix in place the next run
loaded the right members — `Zensus2022_Eigentuemerquote_100m-Gitter.csv`
(2 525 440 cells) and `Zensus2022_Leerstandsquote_100m-Gitter.csv` (2 566 712) —
and **both still matched no analysis cell**, while `net_rent` (25.3 %) and
`household_size` (44.5 %) joined normally off the same grid. Two follow-ups
landed for this:

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
