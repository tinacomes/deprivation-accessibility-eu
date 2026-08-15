# Results summary, analysis audit, and storyline plan (full 67-city sample)

Status: written against `main` @ `ffdf598` (post-PR #40) and `depacc-results`
@ `6de1a96` (67 cities, 24 countries, all under the r5 engine). Three parts:
(1) what the results say, (2) an audit of the statistical analysis, the
k-means clustering and the figures — including two defects found while
auditing, (3) what is still needed to build the paper storyline.

---

## 1. What the results say

The programme is essentially complete on the data side: all 67 cities of the
F.2 stratified draw have full per-city outputs on `depacc-results`
(cityplane rows, typology summaries at both cuts, accessibility tables,
equity/vulnerability tables, deprivation-sensitivity tables, and the
percentile/compounding map set — 67/67 for each), plus the cross-city
tables, five cross figures, and the specification curve.

### 1.1 Scaling: size buys everyday access, not emergency relief

From `cross/scaling.csv` and `cross/inference_scaling_clustered.csv`
(country-clustered SEs, wild cluster bootstrap over 24 countries):

| outcome | elasticity per ln pop | p (wild cluster) | reading |
|---|---|---|---|
| mean_everyday | **−0.196** (SE 0.023) | 0.0002 | strong economies of scale in everyday access; survives country FE (−0.166) |
| mean_emergency | −0.058 (SE 0.042) | 0.21 | no detectable size gradient |
| gini_everyday | **+0.062** (SE 0.019) | 0.0012 | everyday *inequality* grows with size |
| gini_emergency | +0.005 (SE 0.018) | 0.81 | emergency inequality is size-flat |

The paired contrast (`regime_slope_difference.csv`) confirms both
differences are themselves significant: the emergency mean-slope is 0.138
shallower than the everyday one (p = 0.001) and the emergency Gini-slope is
0.057 shallower (p = 0.023, city-clustered — the country-clustered
re-test is coded but not yet run, see §2.3). The TOST
(`inference_equivalence.csv`) is the honest cap on the claim: emergency
flatness is **not** positively demonstrated at ±0.10 — the smallest bound
that would pass is ±0.13. So the storyline phrase is "no detectable
scaling, bounded within ±0.13", never "shown flat".

### 1.2 Geography: the divergence is regionally structured — at the country level

`inference_regional.csv` (permutation over whole countries is the primary
test; city-level ANOVA is reported as anti-conservative reference):

| outcome | Cohen f (city) | p permutation (countries) |
|---|---|---|
| gini_emergency | 0.74 | 0.0023 |
| divergence_gap | 0.69 | 0.0100 |
| compounding_pop_share_50 | 0.53 | 0.0008 |
| compounding_intensity | 0.51 | 0.0023 |
| spearman_rho | 0.50 | 0.0016 |
| gini_everyday | 0.56 | **0.27** — does not survive country-level testing |

Substantively (see `region_strips.png`): **CEE** carries the highest
emergency inequality (median Gini ≈ 0.54) and the strongest
everyday–emergency coupling (median ρ ≈ 0.55) — compounding is worst there;
**West** has a *negative* divergence gap (everyday inequality exceeds
emergency); **North** a positive one; South sits low on both Ginis. The
gini_everyday row is a textbook case of why the country-level correction
matters: p = 0.0007 at city level, 0.27 once region is treated as the
country-level variable it is.

### 1.3 The emergency-desert group

k-means and Ward (k = 2 by silhouette, 0.65 after tail declumping) both
isolate the same five capitals — **București, Rīga, Vilnius, Tallinn,
Ljubljana** — driven by the beyond-threshold emergency tail shares. The
code and figures already treat this correctly as a *flagged outlier group*
(ring on the plots), not a two-type partition: k-means vs region ARI is
~0.07, so the honest cross-city structure is "regional gradients plus one
outlier group", which is itself a findable finding.

### 1.4 Compounding

Coupling ρ spans ~0 to 0.74 across cities (`rho_ranked.png`); HH shares sit
above the 25 % independence benchmark in most cities;
`compounding_intensity` is on every row and its regional contrast is
significant (p_perm = 0.0023). The size gradient of the compounding share
is weakly negative (−0.019 per log10 pop, p ≈ 0.05).

### 1.5 Robustness spine (already in place)

- **Typology is rank-invariant to deprivation curvature by construction**;
  the threshold axis dominates every accessibility knob (HH range ~0.30 vs
  γ at ~0.05, Hamburg and Köln both) — hence the continuous
  `compounding_intensity` as headline.
- **Specification curve** (13 parameterisations): everyday-Gini size slope
  positive and significant under all variants (+0.04 to +0.15);
  emergency-Gini slope ≈ 0 under all; divergence-gap regional permutation
  p ≤ 0.013 under all. (But see §2.1 — the curve's baseline must be fixed
  before this is citable.)
- **Engine cross-check (E.1, closed)**: r5 promoted to primary after the
  friction offset proved unstable across cities; aggregate class shares
  (≤ 0.7 pp) and rank orderings survive engines; per-cell class maps do not
  (~24 % flip).
- **E.2–E.5**: DE completeness passes (pharmacy 0.976, hospital 1.24 in the
  expected direction), INKAR external benchmark passes after the Köln
  stale-cache catch, resolution QQ and face validation in place.

### 1.6 Equity / vulnerability

All 67 cities carry `equity_indices/regressions/ses_coverage/vulnerability`
tables. The Tier-2 Hamburg deep dive (covered-cell reference) shows
elderly 1.37×, children 1.52×, low-rent 1.61× the everyday deprivation of
their comparison groups. **There is no cross-city synthesis of any of this
yet** — 67 tables, no figure, no pooled claim (§3.3).

---

## 2. Audit findings

### 2.1 DEFECT — the Layer-1/2 harness evaluates a different estimator than the pipeline (spec curve inherits it)

`sensitivity/harness.py` `city_stable_targets` applies the deprivation
function to the **composite** time (`g(t_regime_everyday)`), while the
pipeline composites per-service deprivations (`Σ w_s g(t_s) / Σ w_s`).
This is exactly §5.2 defect (1) of the plan, which was fixed for the
Layer-3 sweep but **not** for the Layer-1/2 harness. Verified on Hamburg:
sensitivity-table baseline gini_everyday = 0.583 vs the published row's
0.543. Consequence up the chain: the specification curve's "baseline"
elasticity is **+0.125**, which is not the published claim (+0.062 in
`scaling.csv` / `inference_scaling_clustered.csv`, same 67 cities). The
curve is internally consistent (every variant vs its own estimator) and its
qualitative conclusion almost certainly survives, but it cannot be quoted
as "the headline claim under every parameterisation" while the ringed
baseline is not the headline. Fix as for Layer-3: build per-service
deprivations from the saved `t_eff_<service>` columns (the machinery
already exists in `city_calibration_targets`) and pin the baseline row to
`cityplane_row.csv` in a test. Then regenerate the sensitivity tables and
the spec curve.

Note the emergency side has the same shape of defect (g of the composite
nearest time vs the pipeline's weighted mean of the two per-service
deprivations), just with a smaller Jensen gap (two services, one g).

> **FIXED (this branch).** `variant_regime_deprivations` now applies each
> variant's g PER SERVICE to the saved `t_eff_<s>` / `t_nearest_<s>` columns
> and composites with the pipeline's own weighted row mean, for both
> regimes; the shared no-path masks are applied; `run_sensitivity` warns if
> the baseline recompute deviates from the saved `deprivation_<regime>`
> columns by more than 1e-9 (which can only mean stale surfaces vs config).
> Tests pin the estimator to a hand-built pipeline composite and to the
> Jensen gap (`test_variant_composite_is_per_service_not_g_of_mean`).
>
> A consequence worth stating: the *exact* curvature-invariance of the
> typology was itself an artifact of the old estimator (g of a composite
> time is monotone; a weighted mean of per-service g's is not). Under the
> correct estimator the typology is NEAR-invariant — per-service ranks are
> fixed, the composite mix can drift (~0.5 pp class-share range on a
> synthetic fixture, vs Ginis moving an order of magnitude more). methods.md
> §7a and the spec-curve docstring now say "near-invariant" and the tables
> measure the drift instead of asserting zero. Expect the per-city
> flip-cell shares to become small-but-nonzero when the tables regenerate.

### 2.2 DEFECT — `sensitivity/rank_agreement.csv` is all-NaN

36 rows, every ρ/τ empty. Cause: `run_sensitivity` computes rank agreement
only over cities whose `surfaces.parquet` is staged in the *current* run;
the last sweep run had ≤ 2 staged cities and Spearman needs ≥ 3. So the
claim "city rankings survive the deprivation sweep" — the thing rank
agreement exists to show — currently has no evidence on the branch. Fix:
compute it from the persisted per-city variant tables (as
`spec_curve.load_variant_planes` already does) instead of from staged
surfaces; it then covers all 67 cities regardless of what a given run
staged.

> **FIXED (this branch).** `rank_agreement_from_tables` reads the unioned
> `<city>_deprivation_sensitivity.csv` tables (the same source the spec
> curve reads), pairs each variant with the baseline per city, and reports
> ρ/τ with an `n_cities` column. `run_sensitivity` writes it only when at
> least 3 cities pair (otherwise the existing file is left as-is).
> Caveat until the tables regenerate: a partial dispatch would mix
> old-estimator and new-estimator tables in the union — run the batch over
> the full sample once after merging (see the run instructions).

### 2.3 The PR #40 additions have not produced results yet

`inference_regime_paired.csv` (country-clustered regime-slope difference —
the citable replacement for the city-clustered p = 0.023),
`inference_influence.csv` (LOO envelope, Cook's, Huber/median re-estimates,
desert-excluded fits) and `cluster_null.csv` (Gaussian silhouette null) are
all coded, tested and in the persist list, but absent from
`depacc-results`: the cross stage has not been dispatched since #40 merged.
One `tier1-batch` collect (or `depacc cross`) dispatch closes this.

### 2.4 Statistical analysis — verdict

Beyond the two defects above, the inference stack is sound and unusually
careful: country-clustered SEs with wild cluster bootstrap (Rademacher,
null-imposed), whole-country permutation tests for the region contrasts
(the right exchangeable unit), mixed-model triangulation, TOST with a
pre-stated bound plus the achieved bound (no bound-shopping), LOO/Cook's/
robust re-estimates, and the anti-conservative city-level tests explicitly
labelled as reference-only. Two minor notes:

- the spec-curve plot's CI whiskers use t with n_cities − 2 dof on
  country-clustered SEs; cluster dof (~n_countries − 1) would widen them
  slightly — cosmetic, but fix when regenerating under 2.1;
- `p_cluster_country` from statsmodels uses asymptotic dof; the wild
  bootstrap column is the one to cite (it already is, in the printouts).

### 2.5 k-means clustering — verdict

The clustering code is well-guarded: scaled-token-only entry, silhouette k
selection over 2–6, bootstrap ARI, the zero-inflated tail shares
log1p-opened before distances (documented as the reason the earlier 0.84
silhouette was a scaler artefact; 0.65 survives), and the 62/5 result
consistently interpreted as an outlier group. What remains:

1. **Run the null** (§2.3) so "the desert group is not just any small
   outlier set" has a p-value on the branch.
2. **Persist the clustering diagnostics** (k, silhouette, bootstrap ARI)
   as a table — currently they exist only in run logs.
3. **SES-slope imputation now bites 9 real cities.** `slope_ses_*` is
   missing for the 6 DE + 3 FR cities (EMP not reported) — 13 % < the 25 %
   drop bound, so Berlin, Hamburg, München, Köln, Chemnitz, Landshut,
   Paris, Grenoble and Toulon enter the k-means matrix **median-imputed**
   on those dimensions. The imputation is logged (§5.7 fix) but a
   robustness check belongs in the appendix: recluster without
   `slope_ses_*` and confirm the 62/5 split is unchanged (it should be —
   the split is driven by the emergency tails).
4. **Storyline role**: with k = 2, ARI-vs-region ≈ 0.07 and one small
   outlier group, clustering's narrative contribution is *negative
   evidence* — "European cities do not fall into discrete
   everyday/emergency types; the structure is regional gradients plus five
   emergency-desert capitals". Write it that way rather than presenting a
   typology of two clusters.

### 2.6 Plots — what exists and what is missing

Exists and is publication-shaped: `cityplane.png` (region colour + desert
rings + selective labels), `scaling_elasticity.png` (the headline figure),
`size_gradient.png`, `region_strips.png` (the regional ANOVA visualised),
`rho_ranked.png` (all 67 cities by coupling), `specification_curve.png`
(regenerate after 2.1), and the full per-city map set (percentile,
compounding at both cuts, core zooms) for all 67 cities.

Missing for a paper:

1. **Envelope on the plane** — the curvature min–max Gini whiskers per city
   point (planned in Workstream B.3; the ρ envelope made it to the plane
   annotation, the Gini envelope did not).
2. **A compounding-map gallery** — small multiples of 6–9 contrasting
   cities (one desert capital, a West negative-gap city, a CEE high-ρ
   city…) with the ~24 % per-cell engine-flip caveat in the caption; the
   per-city PNGs exist, the composition does not.
3. **A vulnerability figure** — nothing cross-city exists (§3.3).
4. **Provenance annotations** — extraction dates / engine on or beside
   every cross-city figure, per the E.3 policy lesson ("the extraction date
   is part of the model").

---

## 3. What is still needed for the storyline

### 3.1 The storyline itself (proposed arc)

1. **Question**: as cities grow, do everyday access and emergency
   capability improve together — and do the same residents carry both
   deprivations?
2. **Design**: two-regime deprivation surfaces (potential/soft-min everyday
   vs nearest-facility emergency), rank-based co-location typology, 67
   FUAs / 24 countries, r5 routing, space-for-time inference, all claims at
   the level the design supports (country-clustered / country-permuted).
3. **Finding 1 — regime-specific agglomeration**: size buys everyday access
   (elasticity −0.20) but not emergency relief (−0.06, ns, bounded within
   ±0.13); everyday inequality *rises* with size (+0.06) while emergency
   inequality is size-flat; both differences significant as paired
   contrasts.
4. **Finding 2 — the geography of divergence**: country-level regional
   structure (emergency Gini, divergence gap, coupling); CEE compounds
   (high emergency inequality × strongest coupling); West's problem is
   everyday-side inequality; plus the five emergency-desert capitals. No
   discrete city types (clustering as negative evidence).
5. **Finding 3 — who carries it**: compounding above independence nearly
   everywhere; and the cross-city vulnerability synthesis (now built —
   `cross/vulnerability.csv` + `figures/vulnerability_strata.png`) splits
   the strata: **children face more everyday deprivation than their
   covered reference in 88 % of the 67 cities** (median ratio 1.27, HH
   gap +0.14, worst in CEE and the North), while **the elderly do not
   compound at the harmonised level** (median 0.96, > 1 in only 37 %,
   below parity throughout CEE) — the sharp Hamburg elderly result
   (1.37×) is the *national* fine-grid stratum, a different cut kept
   strictly un-pooled. Tier-2 national/income strata remain the per-city
   depth layer (low-rent 1.61× in Hamburg).
6. **Robustness spine**: rank-invariance by construction → spec curve →
   threshold-axis dominance → continuous intensity → engine cross-check →
   completeness/external benchmarks.

### 3.2 Blocking items, in order

1. **Fix 2.1** (harness per-service composite), regenerate the 67
   sensitivity tables + spec curve; pin baseline = pipeline in a test.
2. **Fix 2.2** (rank agreement from persisted variant tables) — this is
   the last unevidenced robustness claim.
3. **One cross/collect dispatch** to produce the paired, influence and
   cluster-null tables (§2.3) and refresh figures.
4. **Cross-city vulnerability synthesis (§3.3)** — the only genuinely new
   analysis still required by the storyline.
5. Figures: plane envelope whiskers, map gallery, provenance annotations.

### 3.3 The vulnerability synthesis (new, small)

Aggregate the census-harmonised strata (`age_census`, 94–96 % coverage
everywhere) across the 67 `equity_vulnerability.csv` tables into one table
+ one figure: per city, the covered-reference deprivation ratio and HH-gap
for elderly/children strata, by region. This turns Finding 3 from a
Hamburg anecdote into a European claim. Keep national/income strata
(Tier-2) strictly out of the pooled figure (the three-level rule already in
place). Never pool `age_census` with `age_national`.

### 3.3a Status addendum (2026-08-13, after the full-sample regeneration)

The corrected-estimator regeneration ran as two batches (the second after
the 2026-08-06 GitHub Actions outage). Final state on `depacc-results` @
`4c1c85d`: 64/67 sensitivity tables reproduce their published city rows to
1e-9; `rank_agreement.csv` is real for the first time (67 cities, min ρ
0.888/0.956/0.937 for gini_ev/gini_em/gap); the spec-curve baseline sits at
+0.0626 ≈ the published claim; `cluster_null.csv` (silhouette 0.63,
p = 0.001, ARI 0.81), `inference_regime_paired.csv` and
`inference_influence.csv` all exist.

**CLOSED (2026-08-15).** Three cities were owed to the tables, all traced
to one mechanism — a budget-stopped city job stages a PARTIAL dir whose
presence shadowed the persisted summaries in `cmd_import`, silently
dropping the city from the cross union (fixed in
`tools/persist_results.py`). All three have since landed:

- **berlin** and **madrid** — batch run 31721976666 (2026-08-13), which
  regenerated their variant tables on the corrected estimator.
- **paris** — resume round 13, batch run 31816777776 (2026-08-14): the
  pipeline step ran to completion inside its budget (96 min of the 130),
  so the full stack (surfaces → typology → equity → sensitivity) ran and
  the cross tables were rebuilt over all 67 cities. Its final row moved
  the fourth decimal at most (mean_everyday 0.13511 → 0.13516,
  gini_emergency 0.4978 → 0.4970), and no headline number changed at the
  precision it is quoted: the paired Gini-slope difference holds at
  −0.057, wild p = 0.028.

Verification of that final state (2026-08-15): a local `depacc cross`
over the persisted 67-city union reproduces every CI cross and inference
table to ~1e-13, so the published tables are exactly what the code
produces from the persisted inputs.

One spec-curve reading to carry into the paper: the everyday-Gini size
slope is positive under all 13 parameterisations but loses significance
under the concave Box-Cox form swap (+0.026, p = 0.083 on the final
67-city curve) — the claim is curvature-robust and *nearly* form-robust,
and that caveat should be stated rather than smoothed over.

### 3.4 Non-blocking loose ends (state or close)

- **Registry verification before publication**: the DE hospital/pharmacy
  registry counts carry "verify against current release" flags in
  `docs/validation.md`; the multi-country completeness pass that would set
  `quality.completeness_threshold` is still open — either do it or state
  the DE-benchmarked, OSM-intrinsic-proxy position in methods.
- **INKAR emergency side** open (no car-time hospital indicator) — state it.
- **Transit / Tier-2**: the 67-city sample is walk+car; transit remains a
  deliberate Tier-2 dispatch that no published number uses — state scope.
- **Extraction-date policy**: expiry landed (PR #34); confirm all 67
  extractions post-date it or list dates in the provenance appendix.
- **methods.md**: update for the full-sample stage (it still reads
  pilot-era in places) once 1–3 land.
