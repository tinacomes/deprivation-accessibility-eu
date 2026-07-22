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
k = 30 OD), nearest-only vs soft-min (κ→∞), the unreachable-cell treatment
(cap value / exclude), and the everyday **mode set** (walk vs walk+car, the
element-wise minimum travel time — the car OD is kept by the access stage once
a declared variant needs it). Every variant recomputes the everyday
effective-time surface → percentiles → typology and reports how far the **HH
share, coupling ρ and within-regime Ginis** move, plus which cells flip class
(`sensitivity/<city>_access_sensitivity.csv`, a flip-cell map, and — for
Hamburg — an acceptance table naming which knobs beat the threshold axis). The
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
tests on every push.

**Deprivation parameters are never hardcoded in `src/`.** The per-service
everyday thresholds (§3.1) live in `config/deprivation.yaml` with a `source`
and a `verify: TODO` flag on every value; the pipeline still refuses null
placeholders. The uniform-vs-per-service choice is not asserted as settled —
it is decided by the §7a Layer-2b robustness result and re-read once the seeds
are confirmed against the primary sources cited in §3.1.
