# Methods

Every modelling choice in the pipeline, with the literature source of every
parameter. Sections marked **TODO(cite)** must be completed from the named
papers before the corresponding computation is run — the code enforces this
(`depacc.config.require_params` refuses null placeholders and repeats the
citation in its error message). **Never** fill a parameter with an invented
or "reasonable-looking" value.

## 1. Design

Cross-sectional, multi-city study modelled on Musso et al. (PNAS, 2026,
"Large cities lose their growth advantage as countries urbanize"): one
harmonised city definition across countries (Eurostat-OECD Functional Urban
Areas, cross-checked against JRC GHS-UCDB urban centres), and *trajectories
read from the cross-sectional city-size gradient* (space-for-time
substitution). **There is deliberately no longitudinal/temporal component**;
all statements about "trajectories" are cross-sectional inferences and are
labelled as such in every output.

## 2. Potential deprivation

For each populated 100 m grid cell *i* and service type *s*, potential
deprivation is an estimated deprivation function evaluated at an *effective*
travel time. The deprivation function is the impedance function of a gravity
model run in the opposite direction: increasing and convex in travel time,
rather than a decreasing discount. Two regimes, computed as separate
surfaces per city:

### 2.1 Everyday regime (chosen, repeated, substitutable)

1. **2SFCA congestion factor.** Step 1 computes the supply-to-demand ratio
   per facility *j*: `R_j = S_j / Σ_i P_i K(t_ij)` with kernel *K*
   (gaussian, mode-specific bandwidth; config `catchment.kernel`). The
   decreasing kernel appears *only* inside this competition weighting.
   Step 2 converts crowding into a travel-time inflation
   `c_j = (R_ref / R_j)^γ` (reference: demand-weighted median ratio in the
   city; exponent γ and clip bounds in config; γ = 0 disables congestion).
2. **Soft-minimum reducer.** Effective deprivation time
   `t_eff(i) = -(1/κ) ln Σ_j exp(-κ · t_ij · c_j)`, a smooth minimum with
   the deliberate property that several similar-time options reduce the
   effective time (substitutability bonus); bounds
   `min - ln(n)/κ ≤ t_eff ≤ min` (unit-tested). κ in config
   (`softmin.kappa`), sensitivity-swept.
3. **Deprivation.** `D_ev(i) = g_DLF(t_eff(i))`, evaluated **per service**
   before the composite (§2.5), so the deprivation function can carry a
   per-service threshold.

### 2.2 Emergency regime (non-substitutable, time-critical)

`D_em(i) = g_DCF(min_j t_ij)` — nearest facility only; the convexity of the
DCF is where its shape matters most.

### 2.3 Baseline

For **both** regimes, the plain nearest-facility travel time is always
computed and reported as a comparison baseline.

### 2.4 Two meanings of "unreachable" (kept apart)

"Unreachable" conflates two very different situations, and merging them
collapses the everyday–emergency divergence (it inflates the everyday mask by
orders of magnitude and silently promotes far-but-routable cells to maximal
deprivation). They are therefore split:

1. **No network path** — the cell is genuinely unroutable (disconnected from
   the network). This is a property of the *cell*, not the service, so it is
   detected once by a **shared, service- and mode-independent routability
   probe**: a cell has no network path iff it reaches **zero facilities of any
   service in any mode**. Because the probe ignores service type and mode, the
   everyday and emergency no-path sets are **equal by construction**
   (regression-tested). These are the **only** masked/greyed cells: at the
   city composite they are set to NaN on both the deprivation surface and the
   regime travel time, so the choropleths (`viz/`) and the typology
   (`divergence/`) share **one** mask and can never disagree (the bug where a
   capped-high value was greyed on the map yet classified as compounding
   downstream). `unreachable.policy` (`exclude` → NaN; `cap_at_max_time` →
   value at the cutoff) selects how the *per-service* surface treats them
   before compositing; either way the composite is masked. Their population
   share is always reported.

2. **Reachable but service-deprived** — the cell **is** routable but no
   facility of a given service lies within its cutoff (or its 2SFCA catchment
   supply is vanishing, which the congestion factor already inflates). This is
   **not** unreachability; it is a badly deprived cell. It is assigned a
   large-but-finite effective time (`unreachable.finite_fill_min`, default
   `routing.max_time_min`) so the DLF saturates near `Lmax` (high everyday
   deprivation) and the cell **stays on the map**.

The distinction is what keeps a single walking-scale service (green space,
school) from masking the entire city and being re-read as compounding (HH)
deprivation downstream.

### 2.5 Composite across everyday services

Per-service DLF surfaces `D_s(i)` are combined into `D_ev(i)` by an
**equal-weight (config-overridable) population-independent mean over the
services reachable at cell i**, renormalising the weights per cell so a
service-deprived layer that was excluded (policy `exclude`) does not NaN the
composite unless *every* service is missing. The composite **mask is the
shared no-path mask of §2.4** — never the union (`any`) of the per-service
service-deprivation flags, which would let one sparse layer mask the city.
The same rule and mask are applied to the emergency composite over its
services.

**Travel-time summaries are reachable-only.** A cell handled by
`cap_at_max_time` carries the cutoff as its travel time (a placeholder, not a
measured time); under `exclude` it is `NaN`. Either value would distort the
travel-time distribution — the cap in particular floods the upper tail, so a
naive p90 collapses onto the cutoff whenever the unreachable share exceeds
10%. The accessibility indicators (§4.2) therefore compute the
population-weighted mean / median / p90 over **reachable cells only**, and
report the reachable p90 as `pop_p90_time_min_reachable` **alongside** the
`unreachable_pop_share`. The two are complementary and must be read together:
the reachable p90 says how far the served population travels, the unreachable
share says how much of the population is not served at all. The
`pop_share_beyond_<t>min` columns count an unreachable cell as beyond every
finite threshold (it is, by definition), over the whole population.

## 3. Deprivation functions (form transferred, curvature calibrated)

The two regimes use deliberately different shapes (t in **minutes**):

| Regime | Kind | Form | Parameters | Source |
|---|---|---|---|---|
| Everyday | DLF (dimensionless) | **logistic** (saturating) `g(t) = Lmax / (1 + e^{−k(t − t0)})` | Lmax = 1.0; t0, k **per service** (§3.1; base t0 = 15 min, k = 0.2 /min) | Wang et al. 2017 — logistic S-curve of needs-based severity |
| Emergency | DCF (monetary) | **Box-Cox** (convex, escalating) `g(t) = scale·((t+shift)^λ − shift^λ)/λ` | λ = 1.8, shift = 1 min, scale = 1.0 (relative) | Cantillo et al. 2018; Delgado-Lindeman 2019 — ambulance / time-to-care DCF |

**Everyday deprivation SATURATES** — everyday services are substitutable and
non-critical, so relative deprivation tops out at the ceiling Lmax once
access is poor enough; the inflection t0 = 15 min encodes the "15-minute
city" access threshold (g(15) = 0.5), and the surface is ~saturated by
~45 min. This is a deliberate departure from a globally convex impedance:
the logistic is convex below t0 and concave above, and g(0) is a small
positive baseline (= Lmax/(1+e^{k·t0}) ≈ 0.05) rather than exactly 0.

**Emergency deprivation ESCALATES** without bound — it is time-critical, so
the convex Box-Cox (λ > 1) rises ever more steeply; the curvature is tuned so
the cost climbs sharply through the clinical time-to-care threshold
(g(60)/g(45) ≈ 1.66, i.e. +66% over that 15-minute window). g(0) = 0.

**Provenance — form transferred, curvature calibrated (NOT raw coefficient
transfer).** The published DLF/DCF estimates are on an *hours*-scale
deprivation-time basis (hours without water/food/care), not the *minutes*
scale of intra-urban access, so their coefficients are not directly
transferable. We therefore transfer the *functional form* from the cited
work and *calibrate the curvature* to domain anchors: the everyday S-curve to
the intra-urban 15-minute access threshold, and the emergency convexity to
the ~45–60 min clinical time-to-care threshold. This is recorded honestly
here and in each spec's `note:` field in `config/deprivation.yaml`; the
curvature parameters (k, λ) are the primary sensitivity-analysis targets.

The emergency `scale` is left at 1.0 (relative units); anchor it to a value
of statistical life / value of time only if absolute monetary magnitudes are
needed — relative results (Ginis, typology, rankings) are scale-invariant.
Alternative specifications for sensitivity analysis live in
`config/deprivation.yaml → deprivation.alternatives`.

### 3c. Reporting anchor for the unbounded DCF

Scale-invariance protects the *relative* results, but not the **reported
levels**: with λ = 1.8, shift = 1, scale = 1 the raw Box-Cox gives
g(45) = (46^1.8 − 1)/1.8 ≈ 545, so Hamburg's population-weighted mean emergency
deprivation printed as **15.76** — a number with no interpretation, sitting in
the same tables as the everyday 0–1 DLF and inviting exactly the cross-regime
magnitude comparison §3a forbids. The vulnerability table (§6.2) surfaces those
levels prominently, so they have to mean something.

`deprivation.emergency.reference_time_min` (= 45 min, the *same* clinical
time-to-care anchor the curvature was calibrated to) divides g by g(t_ref).
The emergency surface is then in **multiples of the deprivation of arriving at
the clinical threshold**: 1.0 = at the threshold, > 1 = worse. It does *not*
bound the function — the escalation is preserved — and because it is division
by a positive constant, the population-weighted percentiles, the typology, ρ,
Jaccard, both Ginis, the p90/p50 ratio and the concentration index are
unchanged **exactly** (regression-tested in
`tests/test_deprivation_functions.py`). Only levels move: 15.76 → 0.0289. The
Layer-2 form-swap alternative carries the same anchor, so the two forms coincide
at 1.0 there and the alternative's free `scale` cancels. The everyday DLF needs
no anchor (it is bounded by Lmax = 1); set `reference_time_min: null` to report
raw relative units instead. Every reported level names its own scale via the
`units` column of `equity_indices.csv`.

**Full references (to complete with volume/page):** Wang et al. (2017);
Cantillo, Serrano, Macea, Holguín-Veras (2018); Delgado-Lindeman et al.
(2019); anchored in the deprivation-cost-function programme of Holguín-Veras
et al. (2013).

## 3.1 Per-service everyday thresholds

Tolerated travel time falls as usage frequency rises, and some categories have
an internal size hierarchy, so a single `t0 = 15` across every everyday service
is wrong in both directions: too generous for dense, near-daily,
goods-carrying services, and too coarse for categories that span a size
gradient. `t0` (and `k`) are therefore a **per-service mapping**
(`config/deprivation.yaml → deprivation.everyday.per_service`), applied to each
service's surface **before** the composite (§2.5). The mode is selected by
`deprivation.everyday.threshold_mode`:

- `uniform` (**default**) — every service uses the base `t0 = 15`, `k = 0.2`.
  This is the defended simplification and the comparison variant in §7.3.
- `per_service` — the seeds below override `t0`/`k` per service.

Every seed is **transferred from a named standard but flagged `verify: TODO`**
in config (confirm against the primary source before treating as settled — the
values are indicative, not calibrated coefficients):

| Service | Seed t0 (min) | Basis (all `verify: TODO`) |
|---|---|---|
| pharmacy | 8 | dense, near-daily, location-regulated (DE Apothekenbetriebsordnung and comparable EU pharmacy-siting rules) |
| supermarket | 10 | frequent, goods-carrying; food-access "food desert" walking thresholds (USDA ERS; DEFRA/ONS) |
| gp | 18 | registration-based, less frequent (NL/UK); 15-minute-city baseline (Moreno et al. 2021) plus appointment friction |
| school — primary | 12 | local, daily; statutory safe-walking-distance norms (e.g. UK DfE lower band; DE Schulweg) |
| school — secondary | 27 | sparser, wider catchment; statutory secondary walking distance (UK DfE ~3 mi) |
| green space — local | 5 | Natural England ANGSt / WHO Europe (2017): a site within ~300 m (~5 min) of every home |
| green space — district | 20 | ANGSt larger-site distance tiers (2 km / 5 km) |

The two hierarchical categories are **split in the config**
(`config/services.yaml`): `school → school_primary/school_secondary`,
`green_space → green_space_local/green_space_district`. Until the OSM
extraction can distinguish them (schools by `isced:level`/level tags; green
space by `min_area_m2` bands) the second sub-type **reuses the first's
extraction** via `extract_alias` — the same facilities are routed once and each
sub-type applies its own threshold; a `composite_weight` of 0.5 on each keeps
the split category counting once so the five everyday categories stay equally
weighted.

### 3.1a `t0` acts on the *effective* time, not raw walk time

`t0` is a threshold on the **effective** deprivation time `t_eff` — the
soft-min over reachable facilities (§2.1 step 2), of travel time already
inflated by the 2SFCA congestion factor `c_j` (§2.1 step 1) — **not** on a raw
point-to-point walk time. A published walking standard (ANGSt 300 m ≈ 5 min)
is a raw single-facility walk time, so it is mapped onto the `t_eff` basis, not
dropped in raw:

- the soft-min sits at or **below** the nearest raw time (substitutability
  bonus, bounded by `ln(n)/κ`), so for a lone reachable facility `t_eff ≈`
  nearest raw time and the raw standard transfers directly;
- congestion **inflates** it: at the city's reference crowding `c_j ≈ 1`, but a
  facility with half the reference supply-per-demand carries `c_j = 2^γ`, so
  the same raw standard corresponds to a *larger* `t_eff` where supply is
  scarce. The seeds are stated on the (reference-crowding) `t_eff` basis, and
  the sensitivity of the outputs to this mapping is tracked in §7.3 — it is not
  asserted to be exact.

### 3.1b Mode

The published standards are **walking** thresholds. The everyday regime is
evaluated on the **walk** network only (`regimes.everyday.modes: ["walk"]`), so
a single walking `t0` per service is **mode-consistent** by construction — no
per-mode `t0` is needed while everyday is walk-only. This is a deliberate
decision, not an oversight: reaching a pharmacy in 15 min *by car* is a
different construct from 15 min *on foot*, so **if** `car` were added to the
everyday regime, `t0` would have to vary by mode (a single `t0` across modes
would be as questionable as a single `t0` across services). That switch is
flagged here and gated on the mode set; the emergency regime, which is
car-based and non-substitutable, keeps its own convex DCF and is unaffected.

## 3a. Cross-regime standardisation (mandatory)

The everyday (bounded logistic DLF) and emergency (unbounded Box-Cox DCF)
surfaces are on incomparable scales — and the emergency reporting anchor of
§3c does **not** change that: it makes the emergency level interpretable in its
own units (multiples of the 45-min clinical-threshold cost), which is not the
everyday unit (a fraction of the saturation ceiling). Raw magnitudes are
**never** summed,
differenced, co-plotted on a shared axis, or clustered together. The
`standardize/` module is the single choke point: a `RegimeSurface` carries its
`scale_state` and only population-weighted transforms produce comparable
values —

- `to_percentile`: the population-weighted **mid-rank** empirical CDF (values
  in [0,1], invariant to any strictly increasing rescaling — this tames the
  unbounded emergency tail). Used for the typology and all co-location
  statistics. Mid-rank, not the inclusive rank P(X ≤ x): a tie group is a set of
  cells the surface cannot tell apart, so it is placed at the midpoint of its
  own weight span. The difference is invisible until a tie group is large and
  then it inverts the cut — a surface whose least-deprived 90 % share one value
  gets percentile 0.90 under the inclusive rank and is classified "high" at both
  the p50 and p75 thresholds. Mid-rank is also what §4.1's accounting identity
  assumes: cutting at q leaves exactly (1−q) of the population above the cut.
- `to_zscore`: population-weighted z-score, used only for feature vectors.

Hard guards (`require_standardised`, `require_same_standardised`,
`require_percentile`) reject raw surfaces at every cross-regime entry point;
there is no bypass flag. Within-regime statistics (each regime's Gini) are
computed on raw values — that is a within-regime, scale-invariant statistic,
never a cross-regime comparison. All aggregation is population-weighted;
empty/unreachable cells are excluded from weights.

## 4. Divergence outputs (the central result)

1. **Cell-level co-location:** bivariate typology at population-weighted
   median thresholds (quantile configurable): LL/LH/HL/**HH** (compounding
   deprivation), population-weighted and mapped.
2. **City-level divergence:** each city as a point in the
   (Gini of everyday deprivation, Gini of emergency deprivation) plane;
   off-diagonal spread measured alongside population-weighted mean levels. The
   plane is drawn with **curvature-envelope error bars** — the min–max Gini
   across the deprivation-function curvature variants (§7a Layer 1) — because
   the curvature assumption moves each city's Gini by a non-trivial amount
   (~0.2), so a single point would overstate the precision; the bars are the
   honest way to place a city. A **deprivation-function-free variant** of the
   plane uses `gini_t_everyday` / `gini_t_emergency` (§4.3): the Gini of the
   regime-representative *travel time* over reachable cells, which needs no
   DLF/DCF calibration at all and so carries no curvature envelope.
3. **Trajectory:** cities ordered along the FUA-population size gradient;
   test whether everyday and emergency deprivation/inequity co-evolve or
   diverge with size. Cross-sectional (space-for-time) inference only.

### 4.1 Reading the compounding map (area vs. population)

The bivariate co-location map (`figures/compounding_map_<pct>.png`) is drawn on
the **population-weighted percentile** surfaces, and the class thresholds are
population-weighted. Two consequences matter when reading it:

- The **map is area-weighted** while the **class shares are population-
  weighted**. A dense, low-deprivation core holds many people in few cells, so
  `LL`/`HL` can be a large *population* share yet occupy little *map area*, and
  the sparse periphery (`HH`) can dominate the picture at a modest population
  share. The on-figure legend prints each class's population share, and
  `typology_summary_<pct>.csv` gives the exact numbers — read those, not the
  coloured area, for "how many people".
- **The four median-split shares are not four independent numbers — they are
  an accounting identity with a single degree of freedom.** At a
  population-weighted *median* split each axis is cut at its own weighted
  median, so by construction `P(everyday high) = P(emergency high) = 0.5`.
  Writing the marginals out, `HL + HH = 0.5` and `LH + HH = 0.5`, which forces

  > `HL = LH = 0.5 − HH`   and   `LL = HH`.

  The whole 2×2 table is therefore fixed by the single compounding share
  `HH`. For Hamburg `HH ≈ 30.8%`, which *mechanically* gives
  `LL ≈ 30.8% · HL = LH ≈ 19.2%` — exactly the observed
  `LL 30.7% · HL 19.2% · LH 19.2% · HH 30.8%`. The apparent "balance"
  (`LL ≈ HH`, `HL ≈ LH`) is thus a property of the median split, **not** a
  finding about Hamburg; reading it as "an even spread across the four
  quadrants" is a mistake.
- **The informative scalars are the `HH` (compounding) share, the Jaccard
  index of the two high-deprivation sets, and the Spearman `ρ` between the
  two percentile surfaces** — these measure genuine co-location *beyond* the
  marginal identity (statistical independence would give `HH = 0.25`, so
  `HH − 0.25` is the excess co-location; `HH = 30.8%` signals positive
  co-location). All three are reported in `cityplane_row.csv`. The raw
  `LL/HL/LH` shares add nothing once `HH` is known and should not be
  interpreted as independent evidence.
- **`compounding_intensity` is the threshold-free headline.** The Layer-3
  acceptance table (§7a) showed the "how high is high" threshold moves the
  `HH` share ~6× more than the strongest accessibility assumption, so any
  thresholded compounding number is substantially a statement about the cut.
  `compounding_intensity` — the population-weighted mean of
  `min(everyday_pct, emergency_pct)`, i.e. how deep into *both* percentile
  distributions the typical person sits — removes the threshold entirely.
  Because both marginals are population-weighted-uniform by construction, it
  has fixed anchors: **1/3 under independence, 1/2 under perfect coupling,
  1/4 under perfect divergence**. Reported in `cityplane_row.csv` beside the
  thresholded shares (which remain, for their map and their interpretability).
- Each cell is rendered **exactly once**, sized to the grid pitch. (An earlier
  per-class draw loop with oversized markers let the last-drawn class overplot
  the others at high cell counts, so Hamburg's map showed ~80% `HH` regardless
  of the true ~31% share; that artifact is fixed.)
- The **percentile choropleths** (`figures/percentile_{everyday,emergency}.png`)
  show the continuous rank surfaces the split cuts. They are the bridge between
  the magnitude maps (which, under a saturating DLF, push most cells toward the
  ceiling and look uniformly dark) and the categorical map.

### 4.2 Intermediary accessibility indicators (the evidence layer)

Under the deprivation surfaces sit **deprivation-function-free** accessibility
indicators, written by the deprivation stage and directly interpretable in
minutes (no DLF/DCF calibration needed):

- `accessibility_by_service.csv` — one row per infrastructure (GP, pharmacy,
  supermarket, school, green space, ED hospital, ambulance): facility count,
  population-weighted mean / median of the regime-representative travel time
  and the reachable p90 (`pop_p90_time_min_reachable`), population share
  beyond each policy threshold, unreachable share (`unreachable_pop_share`),
  and mean deprivation. All travel-time quantiles are reachable-only (§2.4).
  `figures/accessibility_by_service.png` maps the same.
- `accessibility_by_regime.csv` — the composite everyday / emergency rollup.

These are the per-infrastructure justification for the composite surfaces, and
they are city-level indicators in their own right.

### 4.3 Where the city-level indicators live

| indicator | file |
| --- | --- |
| Ginis (deprivation), Spearman ρ, `divergence_gap`, compounding & Jaccard shares, level features | `cityplane_row.csv` (this city) / `cityplane.csv` (all cities) |
| travel-time Ginis (deprivation-function-free): `gini_t_everyday`, `gini_t_emergency` on reachable `t_regime_*` | `cityplane_row.csv` / `cityplane.csv` |
| class population shares per threshold | `typology_summary_<pct>.csv` |
| per-regime mean/Gini/concentration index; gradient regressions | `equity_indices.csv`, `equity_regressions.csv` |
| per-infrastructure accessibility | `accessibility_by_service.csv`, `accessibility_by_regime.csv` |
| deprivation-assumption sensitivity | `sensitivity/<city>_deprivation_sensitivity.csv` |

## 5. Travel times

Two engines, selected per city config (`routing.engine`):

- **r5 (PRIMARY, every tier):** R5 via r5py (JDK 21) for walk + car
  (+ transit in Tier-2 deep-dives) over the real OSM street network (.pbf,
  clipped to the FUA window) and GTFS; street-level resolution; departure
  window in `routing.departure`. What makes this affordable at continental
  scale is **reverse routing** (§7.1): matrices are routed facilities → cells
  and transposed back, so a complete walk+car city costs roughly the R5
  network build plus minutes of routing (~30–60 min), not the ~8–12 h of
  forward routing.
- **friction (sensitivity variant):** least-cost paths (Dijkstra on the
  8-connected pixel graph, latitude-corrected metric distances) over the
  Weiss et al. (2020) 30-arc-second friction surfaces — motorised for car,
  walking-only for walk — fetched as per-city WCS windows. Run against an
  r5 baseline via `depacc engine-check --engine friction`.

The ordering is a **measured decision, not a preference**. Friction was the
planned Tier-1 primary because it needs no per-city bulk downloads; the §7.1
engine cross-check on two cities then showed its error is *city-specific* —
`gini_emergency` understated by 30 % in Hamburg but 18.5 % in Köln, per-service
travel times by 34–314 % — which is not correctable by a constant offset, while
under r5 the two cities' Ginis nearly coincide where friction spreads them
apart. An uncorrectable engine artifact on the axes of the central result
outweighs friction's cost advantage once reverse routing removed that
advantage's justification.

**The facility set never follows the engine.** Facilities come from Overpass
API queries under both engines (`sources.facilities`, default `overpass`;
polygon features reduced to centre points), so switching `routing.engine`
changes travel times only — the same decoupling the engine cross-check relies
on (§7.1). The .pbf configured per city is the r5 street network, not a
facility source.

Origins: centroids of populated GHS-POP 100 m cells within the FUA;
destinations: OSM facilities per service (`config/services.yaml`, capacity
sources flagged where proxied).

## 6. Equity statistics

Population-weighted mean deprivation; population-weighted Gini (covariance
form); concentration index against SES rank; within-city gradient regressions
(deprivation on the SES covariates, each regressed **univariately** so
heterogeneously-suppressed themes keep their own support).

### 6.1 Two demographic levels, never pooled

Vulnerability enters on two levels, matching the two-tier design. Every
covariate is prefixed `ses_*`, which is what carries it into the equity stage
(`equity/pipeline.py` picks up every `ses_*` column).

| level | source | resolution | availability |
|---|---|---|---|
| `age_census` | **Eurostat Census 2021 1 km grid**, release V3 (GISCO, EPSG:3035, INSPIRE `GRD_ID`; one wide table as GeoPackage/CSV/Parquet/GeoTIFF). Variables of EU Reg. 2018/1799 — `T`/`M`/`F`, broad age `Y_LT15`/`Y_1564`/`Y_GE65`, employed persons `EMP` (voluntary), place of birth, prior residence; `-8888` withheld for confidentiality and `-9999` otherwise unavailable are stripped to NaN. Prefix `ses_census_*` (`ingest/census.py`) | 1 km → **broadcast** to 100 m | **every city** |
| `age_national`, `income_tier2` | national fine SES grids — DE Zensus 2022 100 m (population, age, household size, net rent, ownership, vacancy), NL CBS 100 m, FR INSEE Filosofi 200 m, UK LSOA+IMD. Prefix `ses_<layer>_*` (`ingest/ses.py`) | 100–200 m, native | Tier-2 countries |

**The broadcast is a real limitation, stated not hidden.** A 1 km census value
is replicated onto every 100 m analysis cell inside that kilometre, so the
census shares carry no within-kilometre variation: they are a *neighbourhood*
attribute of the cell, exactly like the Tier-2 ownership/vacancy covariates.
Both levels are joined by the same mechanism, each keyed on its own grid
(`ingest/ses.py::join_ses_to_cells`), and the resolution actually used per layer
— plus a `broadcast_to_analysis_grid` flag — is written to
`data/derived/<city>/ses_resolutions.json`.

**One download, many cities.** Both demographic levels are published as *whole
territories*: one EU-wide census grid, one Zensus theme file for all of Germany
(3.09 M 100 m cells). They are downloaded once per checkout into
`data/raw/{census,ses}` — shared, not city-scoped — and `depacc prefetch --city
… --city …` populates them for a whole batch before the per-city jobs start, so
a ten-city run fetches each national archive once rather than ten times. The
workflows split the raw cache to match: a shared cache
(`boundaries`, `census`, `ghs`, `ses`, keyed on the configs) and a per-city one
(`friction`, `gtfs`, `osm`, `overpass`); the split is declared in
`depacc.ingest.prefetch` and regression-tested against both workflow files. Each
national grid is then clipped to the FUA bounding box *as it is read*, so one
city's ingest never materialises six national themes in memory.

**Selecting the right grid out of a national archive.** Each destatis
"Gitterdaten" zip bundles the *same* theme at 10 km, 1 km and 100 m (plus a
`Datenzusatzbeschreibung` readme), e.g.
`Leerstandsquote_in_Gitterzellen-100m-Gitter.csv`. The member is therefore
chosen by resolution token (`sources.ses.resolution_m`, with per-layer
`resolutions` / `members` overrides), the resolution is re-derived from the
loaded file's own coordinate columns (`x_mp_100m`) and cross-checked against
what the config asked for, and a layer that matches zero analysis cells is
reported. Taking "the first CSV in the archive" is what silently loaded a
coarser grid for the ownership and vacancy layers in the first Hamburg run:
every 100 m join key missed, the covariates arrived all-NaN, dropped out of the
gradient regressions, and left the `low_ownership` stratum with a zero
population share.

**Levels are never mixed in one cross-city comparison.** Age is comparable
everywhere but *only at one level*: the DE Zensus cut is under-**18** at 100 m
while the census cut is under-**15** at 1 km, so those are different variables
and carry different `level` labels. Income/rent exists only where a Tier-2 grid
does. Two config keys keep this explicit: `equity.ses_rank_column` (per city;
Tier-2 cities point it at their rent grid) ranks the concentration index, while
`equity.cityvector_ses_column` (the harmonised census employment share by
default) is the single variable behind the cross-city `slope_ses_*` feature —
the covariate actually used is recorded per city as `slope_ses_column`. That
feature is **strict** (`equity.cityvector_ses_strict`, default true): a city
whose harmonised column is unusable gets no `slope_ses_*` rather than a
substitute, because a column silently pooling a different variable per city is
worse than a missing one. Hamburg forced the issue — activity status is
*voluntary* under Reg. 2018/1799 and DE did not report it, so EMP arrives
non-null on 295 of 176 137 cells and constant zero.

Every `ses_*` column also passes a support gate before it may be regressed,
rank the concentration index or define a stratum
(`equity.min_covariate_valid_share`, default 0.2, on the share of analysis cells
carrying a value; a column constant over its support is rejected too). A
covariate published on a small, non-random subsample yields a p-value about that
subsample, not the city, and a coefficient alone hides which it is. Per-covariate
support is always written to `equity_ses_coverage.csv`.

### 6.2 Vulnerability-stratified deprivation

Beyond the gradients: for each stratum — the population-weighted tail of a
vulnerability variable (`equity.vulnerability_strata`: highest 65+ share,
highest child share, lowest rent, lowest ownership) — we report the
population-weighted mean deprivation the sub-population *experiences* and the
compounding (HH) typology share within it, against **two** references — the
whole-FUA baseline (`*_ratio`) and the cells on which that stratum's own column
is published (`*_ratio_covered`), with `coverage_pop_share` naming how far apart
the two bases are. Read the covered ratio whenever coverage is well under 1: a
stratum is a quantile tail of the covered cells, and national grids publish where
the denominator is large enough, which is not a random subset of a metropolitan
area. Hamburg's tenure grid covers 35 % of cells, concentrated in the dense core,
so `low_ownership` against the whole-FUA reference reads 0.27 — mostly the
statement that cells with published tenure data are urban. With
ratio/gap columns so each row is a self-contained cross-city feature. Written
to `equity_vulnerability.csv` (one row per stratum, so a separate file from the
per-regime `equity_indices.csv`). Each row carries its `level`; a stratum whose
column is absent drops out with a note, which is how income strata simply
disappear for Tier-1 cities.

**A withheld count is not a zero.** Both grids suppress cells for
confidentiality (census `-8888`/`-9999`; Zensus `–`/empty). A share whose
categories are *all* withheld is NaN, never 0 — zero-filling would place the
cell at the bottom of the distribution, i.e. inside the low-vulnerability
comparison group, which is worse than excluding it. A share summing several
published categories keeps its partial sum when only some are withheld.

**Read the ratios, not the absolute means, across regimes.** The everyday DLF
is a fraction of its saturation ceiling and the emergency DCF is unbounded
(§3): the two `mean_dep_*` columns are on incomparable scales even after the
emergency reporting anchor. `equity_indices.csv` carries a `units` column
naming the scale of every reported level.

## 7. Data quality

OSM facility completeness characterised **per country** by benchmarking OSM
hospital/pharmacy counts against national registries (or OSM intrinsic
quality metrics); completeness table produced by `quality/`; the Tier-1
sample can be restricted to cities above `quality.completeness_threshold`.
For Tier 2 we test whether adding transit changes city *rankings* and
clustering, not just levels.

### 7.1 Routing-engine cross-check (E.1)

The friction fast path approximates a street network by a ~1 km raster; this
check measures what that approximation costs, and its two-city answer is what
demoted friction from planned Tier-1 primary to sensitivity variant (§5).
`depacc engine-check --city <id> --engine <alt>` re-runs one city under an
alternative engine and reports the disagreement
(`validation/<city>_engine_check.csv`, a hexbin scatter, both persisted); with
r5 now the primary, `--engine friction` is the standing sensitivity direction,
and the check raises if the alternative equals the city's own engine.

The comparison isolates the **routing engine**. The shadow run inherits the
baseline's `cells.parquet` and its `facilities_*.parquet` verbatim — never
re-extracting them — because a friction city takes facilities from Overpass while
an r5 city takes them from the .pbf, and letting that vary would confound engine
disagreement with facility-set disagreement (§7's separate question). Only the OD
matrices and everything downstream are recomputed, through the *same*
`run_access` / `run_deprivation` the pipeline uses. The shadow lives at
`data/derived/<city>/engine_<engine>/`, nested so it can never be mistaken for a
city, and divergence/equity are not run, so it never reaches `cityplane.csv`.

Four families of number. **Travel time**, per regime and per service: the
population-weighted median and p90 under each engine, plus the population-weighted
Spearman between them. The Spearman is the one that matters here — every headline
output is rank-based, so an engine that shifts all times by a constant costs
nothing while one that *reorders* cells invalidates the typology. Both summaries
are computed on the cells **both** engines reach: summarising each engine over
its own reachable set would confound a level difference with a composition one,
since an engine that gives up on the far periphery would post a lower median for
that reason alone. **Coverage** keeps that composition difference visible rather
than discarding it — the population share each engine reaches at all, per item.
**Indicators**: both Ginis, ρ and the four class shares, recomputed identically
on each engine's surfaces. **Typology**: the population share whose co-location
class changes.

**Cost, and resumption.** Measured on Hamburg (176 137 origins, run
30164334307): ~12 min to build the R5 network, 21–35 min per walk service at a
30-minute cutoff (~2 h 22 for the five everyday services), and multiples of that
per emergency service, whose car regime carries a 60-minute cutoff over a road
rather than footpath network. A full r5 cross-check of one large FUA is ~8–12 h
— longer than a CI job may live. The access stage therefore takes an optional
wall-clock budget (`routing.time_budget_min`, or `DEPACC_ROUTING_BUDGET_MIN`;
unlimited by default) and checkpoints at two levels: a finished (service, mode)
matrix is skipped on re-entry, and within a matrix each finished origin chunk is
written to `od_<service>_<mode>.partial/chunk_NNNNN.parquet`. On exhausting the
budget it raises `RoutingBudgetExhausted` rather than continuing, because
deprivation surfaces built on a partly-routed city would report every unrouted
cell as service-deprived; the CLI surfaces this as exit code 2, distinct from a
failure. A cross-check of a large city is thus run over several dispatches, each
of which is strictly forward progress.

**Reverse routing for the emergency regime.** Measured on run 30251028718, a
60-minute-cutoff car matrix costs ~39.5 min per 5 000-origin chunk — ~24 h per
emergency service, ~47 h for the two of them, which no sequence of CI jobs
should be spent on. R5's cost is one street search **per origin**, with
destinations read off the resulting cost surface, so for a service whose
facilities are far outnumbered by cells the matrix is routed **facilities →
cells** and transposed back: 27 emergency departments cost 27 searches instead
of 176 137. Enabled per mode by `routing.reverse_direction` (empty by default),
and refused where cells do not outnumber facilities by at least 20×, below
which the transpose loses.

The transposed matrix is identical to the forward one only if the network is
symmetric, and a car network is not — one-way streets and turn restrictions
make travel time direction-dependent. That error is therefore **measured, not
assumed**: `asymmetry_report` compares the reverse matrix against any
forward-routed chunks already on disk (for Hamburg, the 20 000 origins
checkpointed before run 30251028718 hit its budget, which cost nothing extra to
reuse) and writes the median, p90 and maximum absolute discrepancy to
`validation/<city>_engine_reverse_asymmetry.csv`. Read that file before reading
the emergency rows of the comparison. Hamburg's measured car asymmetry
(234 788 pairs): median |Δ| 1.0 min on an 11-min median, mean signed
+0.22 min — and R5 reports whole minutes, so part of that is quantisation.
Note also that for `ambulance_station` the reversed direction is arguably the
substantively correct one: emergency response time is station-to-patient, not
patient-to-station.

**Reverse routing extends to walk.** Walking is not subject to one-way streets
or turn restrictions, so the symmetry assumption is *safer* for walk than the
measured-1-minute car case, and every everyday service has 600–2 000 facilities
against 176 137 cells — well past the 20× guard. The workflow therefore
defaults `reverse_modes` to `car walk`, which turns the ~2 h 22 forward walk leg
into minutes per service: a **complete second-city cross-check now costs
roughly the network build plus minutes of routing** (~30 min end to end),
where the first Hamburg attempt burned a 5-hour job and produced nothing. That
matters because §5.10's open question — is the −30 % `gini_emergency` offset a
stable engine bias (correctable) or city-specific (not)? — needs exactly one
or two more r5 cities to answer, and they are now cheap.

Two findings from run 30160444058 make this the validation that gates the rest.
The friction *car* surface gives 99.0 % of Hamburg's cells a zero-minute pair for
everyday services — a 1 km pixel holding a facility is a zero-minute trip for
every cell inside it — which made the Layer-3 walk+car variant degenerate and
unevaluable. And the **emergency regime is car-only**: its median 3.9 min to an ED
and its Gini of 0.62, an axis of the central city-plane result, rest entirely on
that same quantised surface with nothing bounding the error.

**The measured answer (Hamburg, run 30275890587).** The error is now bounded.
Population-weighted over the cells both engines reach, friction understates
travel time everywhere and worst where facilities are dense: the emergency
median moves 2.96 → 8.50 min (+187 %), the everyday median 3.95 → 6.67 (+69 %),
green space 1.23 → 5.10 (+314 %) and ambulance stations 1.96 → 6.00 (+207 %) —
precisely the services a 1 km pixel is most likely to contain. Rank agreement is
moderate, not high: ρ ranges from 0.732 (schools) to 0.890 (emergency
departments), so this is genuine reordering rather than a constant shift.
`gini_emergency` falls 0.621 → 0.437 (−30 %) and `gini_everyday` 0.657 → 0.545
(−17 %). Against that, the divergence ρ between the two percentile surfaces
holds at 0.428 → 0.402 (−6 %) and all four typology class shares move by ≤ 0.5
pp — while **23.7 % of the population changes class**, i.e. cells swap
symmetrically and the aggregate composition is engine-robust even though the
per-cell assignment is not.

Consequently: class shares, the divergence ρ and rank-based city orderings are
reportable from the Tier-1 friction sample; absolute travel times, both Ginis as
levels, and any per-cell typology map are not, without an engine-error band.

Two rows of the comparison table are artefacts rather than results. Every
everyday `p90_min` reads `120.0 → 120.0`: that is `max_time_min` acting as the
`cap_at_max_time` finite fill, so at least 10 % of the population is capped on
all five everyday categories under both engines and the row carries no
information. Relatedly, the everyday scatter is a six-band lattice at
~24-minute intervals — `finite_fill / total composite weight` = 120/5 — because
a cell cut off from *j* of the five categories sits at ≈ 24 *j*. Above the
deprivation threshold `t_regime_everyday` therefore stops behaving like a travel
time and behaves like a count of unmet categories, and the everyday ρ is
substantially a measure of agreement on that count. The emergency panel, where
no cap is in play, is the interpretable one.

The comparison table therefore carries **two rank agreements per item**:
`spearman`, over all paired cells, and `spearman_uncapped` (with `n_uncapped`),
computed after removing every cell whose value contains the finite fill under
*either* engine — for a per-service item the cells at the fill, for a regime
composite the cells with any filled component. `spearman` partly measures
agreement on who is cut off; `spearman_uncapped` measures agreement on travel
time where both engines actually route. A large gap between them says the
headline ρ leans on the cap.

**The second city (Köln, run 30546596359) answered the open question: the
offset is NOT stable, and r5 was promoted.** With reverse routing extended to
walk, the Köln cross-check cost ~93 min cold (network fetch/clip + R5 build +
all seven matrices) and minutes warm. Against Hamburg:

| indicator | Hamburg Δ (friction→r5) | Köln Δ |
|---|---|---|
| gini_emergency | −30.0 % | −18.5 % |
| gini_everyday | −17 % | −12.2 % |
| divergence ρ | −6 % | −11.4 % |
| class shares | ≤ 0.5 pp | ≤ 0.7 pp |
| flip_pop_share_50 | 23.7 % | 25.5 % |

The engine bias differs by city on both Gini axes, so it cannot be removed by
a correction factor. Hence the promotion recorded in §5: r5 is the primary
engine for every tier, friction the sensitivity variant. What the two-city
check licenses either way: aggregate typology class shares and the divergence
ρ are engine-robust (≤ 0.7 pp, ≤ 11 %); per-cell typology class, absolute
travel times and Gini *levels* are not.

**A caution the first r5-primary baselines added (runs 30614554456 /
30619284021): the emergency deprivation Gini is fragile to how ~0.1 % of
cells are handled.** Hamburg's r5-primary baseline reproduced its E.1 shadow
on everything (gini_everyday Δ 0.001, ρ Δ 0.003, identical emergency OD pair
counts) *except* `gini_emergency`: 0.437 → 0.492. The cause is not routing
but the **routability mask**: forward-routed walk (the shadow) left 218 cells
with no pairs in any matrix — masked NaN — while reverse routing links those
same cells as destinations, so the baseline masks 0 and finite-fills their
emergency times at 120 min instead. Passing ~0.1 % of the population between
"excluded" and "included at the fill" moves the unbounded convex DCF's Gini
by +0.055; the bounded everyday DLF barely notices. Consequently the earlier
observation that the two cities' r5 Ginis "nearly coincide" (0.437/0.433) was
partly a mask artifact — the r5-primary values are 0.492/0.433. Read
`gini_emergency` alongside the deprivation-function-free travel-time Gini
`gini_t_emergency` (0.282/0.265, insensitive to the tail treatment), and
treat the off-network-cell policy as an explicit sensitivity axis rather than
an implementation detail.

**Every OD matrix carries engine provenance, and reuse requires a match.**
Found the hard way: a cancelled forward-r5 run left four r5 walk matrices in
Köln's derived cache, a later friction run silently reused them
(`od_path.exists()` was the whole reuse test), and the published "friction"
baseline was a hybrid — exposed only because the next cross-check agreed with
it at an impossible ρ = 0.9997. Each `od_<service>_<mode>.parquet` is now
written with a sidecar `od_<service>_<mode>.meta.json` recording engine, mode,
cutoff and `k_nearest`; `run_access` reuses a matrix only when the sidecar
matches what the current run would route, and a missing sidecar means
re-route. Reverse direction is deliberately not part of the identity — the
transpose is the same data, and the asymmetry report prices that claim.

## 7a. Robustness harness (structured, not probabilistic)

`sensitivity/` recomputes only the **standardised / rank-based** targets
(within-regime Ginis, typology shares, city rankings, cluster membership,
`divergence_gap`) across a defensible parameter envelope
(`config/sensitivity.yaml`); raw deprivation magnitudes are never tracked.
Layers: (1) curvature sweep and (2) functional-form swap — both evaluated on
the saved deprivation-free travel times (`t_regime_*`), so no re-routing;
(2b) the **everyday-threshold calibration** — uniform `t0 = 15` vs per-service
`t0` (§3.1), the one deprivation-calibration layer that must be applied *per
service* and re-composited from the saved per-service effective times
(`t_eff_<service>`), still no re-routing; (3) the **accessibility axis**, run
with `depacc sensitivity --layer access` — the knobs (mode set, `softmin.kappa`,
`catchment.gamma`, bandwidth, `k_nearest`, unreachable treatment) that build the
travel times and can therefore actually move the ranks; (4) flip-cells — cells
whose typology class changes across the sweep,
reported as a stable-vs-sensitive population share and mapped. Reported as
rank-agreement (Spearman/Kendall of city orderings) and cluster agreement
(adjusted Rand) versus baseline.

**Layer 2 (form swap) is ACTIVE, and it is calibrated the honest way — form
transferred, *anchors* held fixed.** Where Layer 1 varies curvature within a
fixed form, Layer 2 replaces the form itself while pinning the *same domain
anchors* the baselines were calibrated to (§3), so only the functional shape
between/beyond the anchors differs:

- Everyday: the saturating **logistic DLF → a concave Box-Cox DLF** (`lam < 1`)
  that passes through the same `g(15) = 0.5·g(45)` half-max and the `g(45) = 1`
  ceiling. `lam` is *solved* from the ratio anchor, `scale` from the ceiling
  anchor — not chosen.
- Emergency: the convex **Box-Cox DCF → an exponential DCF** matching the
  baseline at *both* 45 and 60 min, so the clinical-threshold ratio
  `g(60)/g(45) ≈ 1.66` is identical. `beta` is *solved* from that ratio.

The calibrated parameters and their anchor equations live in
`config/deprivation.yaml → deprivation.alternatives.*` (`note:` fields, exactly
reproducible), and the swap is wired in `config/sensitivity.yaml → form_swap`.
Because every admissible `g(t)` is still strictly increasing, the co-location
typology stays rank-invariant across Layer 2 as well; what Layer 2 tests is
whether the **Ginis and the plane** survive a change of *form* (not just
curvature), tracked separately on the `form_swap` axis so it never contaminates
the Layer-1 curvature envelope.

**Layer 3 (accessibility) — the cheap variants are ACTIVE.** They re-run the
*deprivation stage only*, from the **saved OD parquets** — no re-routing. Each
knob is swept one at a time from the config baseline: `softmin.kappa`
∈{0.1, 0.25, 0.5, 1, 2}, `catchment.gamma` ∈{0, 0.25, 0.5, 1}, walk catchment
bandwidth ∈{10, 15, 20} min, `k_nearest` ∈{10, 30} (subsetting the saved
k = 30 OD), nearest-only vs soft-min (κ→∞), `unreachable.finite_fill_min`
∈{60, 90, 180} min, and the everyday **mode set** (walk vs walk+car, the
element-wise minimum travel time — the car OD is kept by the access stage once
a declared variant needs it).

The `unreachable` axis sweeps the **finite fill**, not the unroutable-cell
policy. Since the reachability split (§2) `policy` governs only genuinely
unroutable cells, of which a well-connected FUA has none — Hamburg has zero, so
sweeping it produced two identical rows. The knob that actually sets the
deprivation of the 12–13 % of the population with no walkable GP is the
large-but-finite time assigned to *reachable-but-service-deprived* cells.

Every variant recomputes the everyday per-service deprivations, composites them
exactly as the deprivation stage does (the weighted mean of `g(t_s)` — **not**
`g` of the mean travel time; `g` is nonlinear, and compositing times first put
the sweep's own baseline at a point the model never occupied), then percentiles →
typology, and reports how far the **HH share, coupling ρ and within-regime
Ginis** move, plus which cells flip class
(`sensitivity/<city>_access_sensitivity.csv`, a flip-cell map, and an acceptance
table naming which knobs beat the threshold axis). A test pins the `baseline`
variant to the pipeline's saved surfaces.

Two additions close gaps the first corrected sweep left open. **The
composite-time LEVEL features** (`pop_share_beyond_everyday_<thr>`, §4.3) are
reported per variant and their per-knob ranges join the acceptance table: the
*deprivation* targets proved fill-invariant (the DLF saturates well before
60 min), but the level features are built from the composite **time**, which
contains the finite fill whenever a cell misses a service, so their
fill-dependence has to be measured rather than presumed absent. And the
**coupling ρ is quoted with its accessibility envelope**: the min–max ρ across
the non-degenerate variants (`rho_envelope`; on Hamburg the congestion exponent
alone spans 0.39–0.56 around a baseline 0.43), printed by the sweep and
annotated per city on the plane figure — the point estimate alone overstates
the accessibility model's precision.

**Degenerate variants are flagged and excluded from the acceptance ranges.** A
variant whose everyday surface collapses into a single exact-tie block holding
more than half the population cannot support a median split at all: its class
shares record where the block fell, not a sensitivity. Two variants reach that
state on Hamburg. At κ = 0.1 the soft-min substitutability bonus is ln(k)/κ ≈ 34
minutes at k = 30, so effective time floors at zero across the whole core; and
walk+car over the 1 km friction *car* surface gives ~95 % of cells a
zero-minute pair. Between them they had produced the headline "κ moves the HH
share most" — both reporting the identical range because both returned the same
degenerate split. The walk+car degeneracy is a friction artifact, not a fact
about the mode set: under the r5 primary engine (§5) the car times are
street-resolved and the `everyday_mode` axis becomes evaluable in principle.
Not yet in practice: the sweep reads *saved* everyday-car ODs, which are only
routed when `route_sensitivity_modes` is on, and the first r5-primary runs
showed the sweep happily consuming the friction-era everyday-car matrices
left in the derived cache (identical degenerate split to the friction runs) —
the sweep does not yet honour the OD provenance sidecars that `run_access`
does. Until it checks them and the everyday-car ODs are re-routed under r5,
the walk+car variant's rows measure a friction artifact and must not be
read. The per-variant table carries `max_tie_everyday`,
`zero_floor_pop_share` and `degenerate` so this is visible rather than inferred.
Only the HH share carries an "exceeds the threshold axis" verdict: ρ is computed
after the percentile transform, which the typology threshold does not touch, so
the threshold axis's ρ range is 0 by construction and any knob would "beat" it.
The
**expensive** Layer-3 variants that need per-variant *re-routing* — friction vs
r5 engine (Workstream E, Hamburg) and transit inclusion for Tier-2 — are
deferred until the pilot sample exists.

**The calibration finding (Layer 2b vs Layer 3).** The uniform-vs-per-service
contrast is reported as a first-class result against the Layer-3 hypothesis:
the outputs should move **more** with the accessibility model (supply/mode)
than with deprivation calibration. If the contrast barely moves the stable
targets (Spearman/Kendall on city rankings, typology-class ARI, typology
shares, Ginis, `divergence_gap`), uniform `t0 = 15` is **retained as a stated,
defended simplification**; if it moves them, per-service `t0` was necessary and
is adopted. Either way the choice becomes a reported robustness finding, not an
attackable default. Outputs: `sensitivity/calibration_rank_agreement.csv`,
`calibration_typology_ari.csv`, `calibration_target_drift.csv`. (The per-service
seeds carry `verify: TODO` in `config/deprivation.yaml`; the decision is
re-read once they are confirmed against primary sources.)

**Framing:** this is a *structured robustness check over a defensible
parameter envelope*, NOT a probabilistic uncertainty quantification — it is
not presented as a posterior.

**Single-city view (`sensitivity/<city>_deprivation_sensitivity.csv`,
`figures/sensitivity_deprivation.png`).** The cross-city rank-agreement and
cluster-agreement targets need the multi-city sample; for one city the sweep
still reports the two things that *are* well-defined:

- *Curvature axis.* Across the deprivation-function curvature variants the
  within-regime **Ginis move** (they are computed on raw magnitudes), but the
  **co-location typology does not**: it is built on population-weighted ranks,
  and every admissible `g(t)` is strictly increasing, so the ranks — and hence
  the `LL/HL/LH/HH` classes and their shares — are **invariant by
  construction**. The table makes this explicit (Gini columns spread, class-
  share columns constant); it is the scale-free property, not a null result.
- *Threshold axis.* "How high is high" is a genuine assumption, so the `HH`
  (compounding) share is swept over several percentile cut-offs (0.40–0.75).
  This is where the headline number actually moves, and it is reported so the
  reader can see the split's leverage.

It follows that the assumptions which move the **spatial** result are the
**accessibility** ones (Layer 3: mode set, `softmin.kappa`, `catchment.gamma`,
bandwidth, `k_nearest`, unreachable treatment) — because they change the travel
times and therefore the ranks — not the deprivation-function curvature. The
cheap ones run from the cached OD (above); the Hamburg acceptance table
(`sensitivity/hamburg_access_acceptance.csv`) ranks each knob by how far it
moves the HH share and ρ against the threshold axis, and the expectation is
that the **everyday mode set dominates** — swapping walk for walk+car reshapes
the effective-time field far more than any within-model knob. (ρ is a coupling
of the two surfaces and is threshold-independent, so *any* knob that moves it
beats the threshold axis, whose ρ range is zero by construction.)

## 8. Reproducibility

Config-driven (YAML per city + tier); cached downloads with SHA-256
provenance sidecars; no raw data committed; unit tests on the DLF/DCF
mapping, soft-min reducer, 2SFCA factor, unreachable handling (incl. the
shared no-path mask and the reachable-but-service-deprived finite-fill,
§2.4), the per-service `t0` seam and the divergence typology; CI runs the
tests on every push. **Derived travel-time matrices carry their own
provenance** (§7.1): every `od_*.parquet` has a `.meta.json` sidecar naming
the engine, mode, cutoff and `k_nearest` that produced it, and the access
stage refuses to reuse a matrix whose sidecar does not match the current run —
the guard that stops a cached matrix from one engine silently entering another
engine's outputs.

**Deprivation parameters are never hardcoded in `src/`.** The per-service
everyday thresholds (§3.1) live in `config/deprivation.yaml` with a `source`
and a `verify: TODO` flag on every value; the pipeline still refuses null
placeholders. The uniform-vs-per-service choice is not asserted as settled —
it is decided by the §7a Layer-2b robustness result and re-read once the seeds
are confirmed against the primary sources cited in §3.1.
