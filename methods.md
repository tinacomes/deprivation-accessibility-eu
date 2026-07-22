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

## 3. Deprivation functions (form transferred, curvature calibrated)

The two regimes use deliberately different shapes (t in **minutes**):

| Regime | Kind | Form | Parameters | Source |
|---|---|---|---|---|
| Everyday | DLF (dimensionless) | **logistic** (saturating) `g(t) = Lmax / (1 + e^{−k(t − t0)})` | Lmax = 1.0, t0 = 15 min, k = 0.2 /min | Wang et al. 2017 — logistic S-curve of needs-based severity |
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

**Full references (to complete with volume/page):** Wang et al. (2017);
Cantillo, Serrano, Macea, Holguín-Veras (2018); Delgado-Lindeman et al.
(2019); anchored in the deprivation-cost-function programme of Holguín-Veras
et al. (2013).

## 3a. Cross-regime standardisation (mandatory)

The everyday (bounded logistic DLF) and emergency (unbounded Box-Cox DCF)
surfaces are on incomparable scales. Raw magnitudes are **never** summed,
differenced, co-plotted on a shared axis, or clustered together. The
`standardize/` module is the single choke point: a `RegimeSurface` carries its
`scale_state` and only population-weighted transforms produce comparable
values —

- `to_percentile`: the population-weighted empirical CDF (values in [0,1],
  invariant to any strictly increasing rescaling — this tames the unbounded
  emergency tail). Used for the typology and all co-location statistics.
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
   off-diagonal spread measured alongside population-weighted mean levels.
3. **Trajectory:** cities ordered along the FUA-population size gradient;
   test whether everyday and emergency deprivation/inequity co-evolve or
   diverge with size. Cross-sectional (space-for-time) inference only.

## 5. Travel times

Two engines, selected per city config (`routing.engine`):

- **r5 (reference, Tier 2):** R5 via r5py (JDK 21) for walk + car + transit
  on OSM (.pbf) and GTFS; street-level resolution; departure window in
  `routing.departure`.
- **friction (Tier-1 fast path):** least-cost paths (Dijkstra on the
  8-connected pixel graph, latitude-corrected metric distances) over the
  Weiss et al. (2020) 30-arc-second friction surfaces — motorised for car,
  walking-only for walk — fetched as per-city WCS windows. Facilities come
  from Overpass API queries (polygon features reduced to centre points; no
  min-area filter — immaterial at ~1 km resolution). This scales the
  continental sample without per-city bulk downloads; it is coarser, so
  Tier-2 r5 runs cross-check whether ENGINE choice changes city rankings
  (§7), exactly as the transit-vs-no-transit check does.

Origins: centroids of populated GHS-POP 100 m cells within the FUA;
destinations: OSM facilities per service (`config/services.yaml`, capacity
sources flagged where proxied).

## 6. Equity statistics

Population-weighted mean deprivation; population-weighted Gini (covariance
form); concentration index against SES rank (Tier 2: income/rent proxies
from national 100–200 m grids); within-city gradient regressions
(deprivation on income/rent proxy, age structure, household composition).

## 7. Data quality

OSM facility completeness characterised **per country** by benchmarking OSM
hospital/pharmacy counts against national registries (or OSM intrinsic
quality metrics); completeness table produced by `quality/`; the Tier-1
sample can be restricted to cities above `quality.completeness_threshold`.
For Tier 2 we test whether adding transit changes city *rankings* and
clustering, not just levels.

## 7a. Robustness harness (structured, not probabilistic)

`sensitivity/` recomputes only the **standardised / rank-based** targets
(within-regime Ginis, typology shares, city rankings, cluster membership,
`divergence_gap`) across a defensible parameter envelope
(`config/sensitivity.yaml`); raw deprivation magnitudes are never tracked.
Layers: (1) curvature sweep and (2) functional-form swap — both evaluated on
the saved deprivation-free travel times (`t_regime_*`), so no re-routing;
(3) the accessibility axis (supply: nearest vs 2SFCA; mode: walk vs
walk+transit), which changes the travel times and is the comparison against
which deprivation-calibration sensitivity is judged; (4) flip-cells — cells
whose typology class changes across the sweep, reported as a stable-vs-
sensitive population share and mapped. Reported as rank-agreement
(Spearman/Kendall of city orderings) and cluster agreement (adjusted Rand)
versus baseline.

**Framing:** this is a *structured robustness check over a defensible
parameter envelope*, NOT a probabilistic uncertainty quantification — it is
not presented as a posterior.

## 8. Reproducibility

Config-driven (YAML per city + tier); cached downloads with SHA-256
provenance sidecars; no raw data committed; unit tests on the DLF/DCF
mapping, soft-min reducer, 2SFCA factor, unreachable handling and the
divergence typology; CI runs the tests on every push.
