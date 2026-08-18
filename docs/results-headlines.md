# Headline results and reader's glossary

A plain-language summary of the study's main results, with the exact
numbers to quote and the caveat each one carries, followed by a glossary
of every abbreviation and indicator used in the outputs on
`depacc-results`. **The sample is complete and the numbers below are
final**: the last routing round (Paris, batch run 31816777776,
2026-08-14) landed, and every cross table, inference test, clustering
diagnostic and sensitivity sweep has been recomputed over all 67 cities
since.

Sample: **67 functional urban areas in 24 countries** (F.2 stratified
draw: 4 macro-regions × 4 size strata, 100 k – 12.9 M inhabitants),
routed with r5 over OSM street networks, walk for everyday services and
car for emergency care. All cross-city inference is cross-sectional
space-for-time and is tested at the country level (cities nest in
countries).

**Where everything lives.** Every number and figure cited below is on the
[`depacc-results` branch](https://github.com/tinacomes/deprivation-accessibility-eu/tree/depacc-results)
of this repository (an orphan branch that every workflow run appends to):
`cities/<city>/` holds the per-city tables and maps, `cross/` the
cross-city tables, inference tests and figures, `sensitivity/` the
robustness sweeps and specification curve, `validation/` the
engine-check evidence. Locally:
`git fetch origin depacc-results && git worktree add ../depacc-results
origin/depacc-results`. Methods: [`methods.md`](../methods.md) (§4.4 for
the cross-city analyses and inference).

---

## 1. The headlines

### H1 — City size buys everyday access, but not emergency care

Mean everyday deprivation falls by ~19 % for each e-fold (~2.7×) of
population: elasticity **−0.196** (country-clustered SE 0.023, wild
cluster bootstrap p = 0.0002, R² = 0.44), robust to country fixed
effects (−0.17), leave-one-out city deletion (envelope −0.204 to
−0.185), robust estimators (Huber −0.196, median regression −0.223) and
exclusion of the emergency-desert group (−0.203). Mean emergency
deprivation shows **no detectable size gradient** (−0.059, clustered
p = 0.16, wild p = 0.21) — and the TOST bounds it: the emergency
elasticity lies within **±0.13** (equivalence at the stricter ±0.10
bound is not shown, so say "no detectable scaling, bounded within
±0.13", never "proven flat"). The difference between the two slopes is
itself significant (paired regime test, +0.137, wild p = 0.002).

*Phrase as:* agglomeration benefits are regime-specific — bigger cities
deliver everyday services closer to people, but proximity to emergency
care does not improve with size.

### H2 — Everyday inequality grows with size; emergency inequality does not

The Gini of everyday deprivation rises with population (elasticity
**+0.062**, wild p = 0.0012), while the emergency Gini is size-flat
(+0.004, wild p = 0.84). The paired slope difference is **−0.058 with
wild p = 0.029** over all 67 cities. Robustness: the everyday-Gini slope
is positive under **all 14 deprivation parameterisations** of the
specification curve (+0.026 to +0.075), significant in 13/14 — the
exception is the concave Box-Cox form swap (+0.026, p = 0.082), a caveat
to state.

**The emergency half is conditional on beyond-benchmark escalation, and
must be reported as such.** The EMS benchmarks (negligible ≤3–4 min,
8-min urban standard, 15-min cut-off) define the cost scale up to
15 minutes, and all three literature-grounded escalation forms are
calibrated to coincide there (identical 4/8/15-min ratio anchors).
*Beyond* the 15-minute cut-off no benchmark exists —
times out there measure only "how bad things are" — and this is exactly
where the forms diverge (at 60 min: 1.6× / 11× / 120× the benchmark
cost), so the emergency-Gini size behaviour splits by escalation
hypothesis:

- **Saturating escalation (the bounded survival-based curve, 1 = full
  deprivation, saturation ~30–45 min emerging from the anchors):
  size-flat** (+0.001, p = 0.97) — the "should 1 not be full
  deprivation?" framing gives the same headline as the baseline.
- **Polynomial escalation (Box-Cox, the Cantillo/Delgado-Lindeman line;
  λ 1.4–2.2): size-flat** (slopes −0.006 to +0.014, all ns) — in
  agreement with the deprivation-FREE travel-time Gini, which is itself
  size-flat (−0.015, p = 0.42): a benchmark-free anchor point.
- **Exponential escalation (the Holguín-Veras line): rising** (+0.098,
  p = 0.0003), reversing the everyday-vs-emergency contrast. Mechanism,
  verified in the data: the beyond-cut-off tail *shares* are size-flat
  (beyond-30-min elasticity −0.003, p = 0.99), but exponential pricing
  makes the Gini track extreme-tail *depth* — it decouples from the time
  distribution's inequality (ρ = 0.04 with the travel-time Gini),
  correlates with the beyond-45-min share (ρ = 0.45), and saturates near
  its ceiling (median 0.96; above 0.9 in 43 of 67 cities). How many
  minutes past the cut-off a city's worst-served residents sit grows
  with FUA size, and only exponential-in-minutes pricing makes that
  dominate the Gini.

Form-independent statements, safe under everything: everyday inequality
rises with size under all 14 parameterisations; emergency inequality
**never falls** with size under any of them; and whether it is flat or
rising is decided by the beyond-benchmark escalation form, which no
benchmark pins down — flat under two of the three literature-grounded
escalation hypotheses (saturating and polynomial), rising only under
the exponential. The Box-Cox is the baseline by transfer provenance
(the ambulance-DCF line) and by its agreement with the raw-minutes Gini
— not because the exponential is extreme. (History: the superseded
45/60-min anchor window flattened the exponential to β = 0.024, slope
−0.001, p = 0.97 — i.e. the old calibration under-priced
beyond-benchmark escalation because it treated 45/60 min as a benchmark
window, which it is not.) Note what this robustness
is *not*: the Gini **levels** move a great deal under the same sweep
(median envelope width 0.24 everyday, 0.17 emergency under curvature alone), which is the point
— the calibration carries information, and the slope claim is defended by
the whole curve rather than by any one parameterisation. The curves being
swept, and the linear loss a pure-access measure would use instead, are
drawn in `figures/deprivation_curves.png`.

### H3 — The divergence has a geography, and it is country-level

Testing regional contrasts with the honest unit (permutation of whole
countries across regions): the emergency Gini (Cohen f 0.74,
p_perm = 0.0022), the divergence gap (p_perm = 0.010), the coupling ρ
(p_perm = 0.0016) and both compounding measures (p_perm = 0.0008 for the
HH share, 0.0023 for the continuous intensity) differ by macro-region.
**CEE compounds**: highest emergency inequality (median Gini 0.54) *and*
the strongest everyday–emergency coupling (median ρ 0.55) — the same
populations tend to carry both deprivations. **The West's inequality is
everyday-side** (median divergence gap −0.12); the North's is
emergency-side (+0.09). The everyday Gini's apparent regional contrast
does **not** survive country-level testing (p_perm = 0.28 despite
city-level p = 0.0007) — do not claim it.

### H4 — No city types; regional gradients plus one desert group

k-means cuts the sample 62-vs-5: **București, Rīga, Vilnius, Tallinn,
Ljubljana** — the emergency-desert capitals, driven by their
beyond-threshold emergency travel-time tails. The split is real
(silhouette 0.65, Gaussian-null p = 0.001, bootstrap ARI 0.87) but it is
an **outlier group, not a typology** (agreement with the region
partition ARI = 0.001). Ward selects the same k on the same axis and
isolates a *nested subset* — the two most extreme capitals, București
and Vilnius (65-vs-2, ARI vs k-means 0.52). Read that as corroboration
of a severity ordering, not as two algorithms agreeing on one group: the
methods disagree about where to cut a gradient, not about the gradient.
The peeled re-clustering (outliers
removed, everything recomputed — `cluster_null_peeled.csv`) finds one
further split, **along the same axis at lower intensity**: a 48/14 cut
isolating the *partial-desert* cities (Oslo, Stockholm, Göteborg,
Stavanger, Aalborg, Turku, Norrköping, Warszawa, Sofia, Zagreb, Palermo,
Luxembourg, Brăila, Łomża — real emergency tails). It clears the null
(p = 0.001, 999 sims) and is not the region partition (ARI 0.07), but
the separation is moderate (silhouette 0.38) and only borderline stable
(bootstrap ARI 0.74); Ward again nests inside it (56/6). Its borderline
stability is visible in the data's own history: under the pre-refresh
extraction state the same rule cut 50/12, with Brăila and Łomża —
the two smallest CEE cities — on the covered side of the boundary.
**Feature-set robustness (`cluster_feature_robustness.csv`)**: re-running
the whole pipeline with the 8/15-min benchmark shares *included* in the
feature set leaves the main partition identical (ARI 1.00, same five
capitals) and reproduces the peeled cut at ARI 0.97 — while flagging
Brăila+Łomża as their own micro-group, converging evidence that they sit
on the gradient boundary rather than in any type. The citable reading is
unchanged and strengthened: European cities do not form
multi-dimensional types — the only recoverable discrete structure is a
**severity ordering on one axis**, emergency-periphery coverage
(covered → partial desert → desert), presented as a gradient made
visible, not as city types, with the boundary between "covered" and
"partial desert" explicitly fuzzy.

### H5 — Who carries it: children, almost everywhere

Pooling the census-harmonised strata across all 67 cities
(covered-cell reference): **children live in cells with more everyday
deprivation than their comparison cells in 88 % of cities** (median
ratio 1.27) and in higher-compounding cells in 88 % (median HH gap
+0.13), strongest in CEE (median ratio 1.44) and the North. **The
elderly do not compound at the harmonised level** (median 0.96, above
parity in only 37 % of cities, below parity across most of CEE). The
sharper Tier-2 national results (Hamburg: elderly 1.37×, children
1.52×, low-rent 1.61×) use finer national data with different
definitions and are reported per city, never pooled.

### H6 — Compounding is the norm, not the exception

The population sharing both high-everyday and high-emergency deprivation
(HH share at the median split) averages **33 %** against the 25 %
independence benchmark and exceeds it in **66 of 67 cities**; coupling ρ
spans −0.02 to 0.74. The continuous `compounding_intensity` (which
removes the threshold's leverage) shows the same regional pattern
(p_perm = 0.0023). The class shares barely notice the deprivation
function — median envelope width across the 67 cities is 1.4 pp under the
curvature grid and 0.9 pp under the form swaps, against **29.8 pp for the
"how high is high" threshold**, a ~21× dominance
(`deprivation_sensitivity_summary.csv`). Per-city assumption
robustness: the "how high is high" threshold moves the HH share ~6×
more than any accessibility-model knob — which is exactly why the
continuous measure is the headline and the class shares carry a
threshold sweep.

### H7 — Deprivation is not access: the claims survive, the framing earns its keep

Re-running the size regressions on plain minutes (`deprivation_vs_access.csv`)
does three things at once. **The claims survive**: the everyday gradient is
there without any deprivation function (median walk time −0.237,
p = 3.8e-5; mean time −0.178), and the emergency non-gradient is there too
(−0.042 to −0.058, none significant below 0.05 except the p90 tail,
−0.058, p = 0.018). **The deprivation outcome is better behaved**:
R² = 0.44 against 0.16 for median minutes — the loss function discounts
variation in the flat part of the curve that carries no welfare content.
**And the deserts are invisible to access averages**: București's median
emergency minute count is 0.71× the sample median while its mean
emergency *deprivation* is 2.81× it; across the five deserts, median-time
ratios of 0.71–1.92× sit against deprivation ratios of 2.45–4.72×
(`desert_access_contrast.csv`). Only the convex, clinically anchored DCF
prices the tail that puts them there. The two Gini families agree closely
in ranking (Pearson r 0.965 everyday / 0.976 emergency), which is why the
*rank-based* results are safe to call parameterisation-free.

The emergency-coverage grade (covered 48 / partial desert 14 / desert 5 —
the k-means severity ordering of H4) sets the **level** above all: the
grade level shift is overwhelming (country-clustered Wald p ≈ 1e-15;
median mean-emergency deprivation 1.02 / 1.87 / 3.37 in multiples of the
15-min benchmark cost — the ordering itself is the policy result). The
slope × grade interaction is p = 0.010 under the current 48/14/5 grades
but was p = 0.17 under the pre-refresh 50/12/5 — a two-city boundary
change flips it, so treat the interaction as boundary-sensitive: lead
with "coverage class, not city size, sets emergency deprivation" and
never headline a grade-specific size gradient
(`scaling_by_grade.csv`, `figures/scaling_by_coverage_grade.png`).

### What is deliberately NOT claimed

- **Absolute travel times and Gini levels under the friction engine**
  (E.1: levels understated 34–314 %; r5 is the primary engine for this
  reason; friction is the declared sensitivity variant).
- **Per-cell typology classes on any map** — ~24 % of population flips
  class between routing engines; maps are for spatial patterns.
- **A causal or longitudinal reading** — every gradient is
  cross-sectional space-for-time.
- **An everyday-Gini regional contrast** (H3) and **elderly compounding
  at the European level** (H5).
- **An unconditional emergency-Gini trend** (H2: flat under saturating
  and polynomial beyond-benchmark escalation and under the raw-minutes
  Gini, rising only under exponential escalation — always report the
  conditionality; the safe unconditional statements are "never falls
  with size" and "the everyday Gini rises under everything").
- **Rank-agreement universality** (min ρ 0.90+ holds over the curvature
  grid and the everyday form swap; the two emergency escalation swaps
  change the measurand and are scoped exceptions — exponential makes the
  emergency-Gini ranking an extreme-tail-depth ordering, ρ = 0.19 vs
  baseline; the bounded survival swap makes it a benchmark-window
  inequality ordering, ρ = 0.49 — report both as changes of measurand,
  not as noise).
- **Two clustering algorithms agreeing on one desert group** (H4: Ward's
  cut nests inside k-means', it does not coincide with it).

---

## 2. Glossary

### Study design

| term | meaning |
|---|---|
| FUA | Functional Urban Area (Eurostat/OECD): a city plus its commuting zone — the unit "city" in this study. |
| Tier 1 / Tier 2 | Data depth. Tier 1 = every sampled FUA (EU-harmonised data). Tier 2 = deep-dive cities (DE/NL/FR…) with national fine-grid SES data and optionally transit. |
| everyday regime | The five chosen, repeated, substitutable services — GP, pharmacy, supermarket, school, green space — accessed on foot; deprivation from a gravity-type potential measure. |
| emergency regime | Emergency-department hospital and ambulance station — non-substitutable, time-critical — accessed by car; deprivation from the nearest facility only. |
| space-for-time | Reading the cross-sectional city-size gradient as a development trajectory; no longitudinal data is used. |
| macro-regions | North (SE/NO/DK/FI), West (DE/NL/FR/BE/AT + LU), South (ES/IT/PT/EL), CEE (Central–Eastern Europe: PL/CZ/RO/HU/SK + Baltics + HR/SI/BG). |
| E.1–E.5 / A–F | Validation exercises (engine cross-check, OSM completeness, external benchmark, resolution check, face validation) / plan workstreams. |

### Deprivation model

| term | meaning |
|---|---|
| DLF | Deprivation Loss Function — the everyday regime's increasing, S-shaped (logistic) function of effective travel time, in [0, 1]. Parameters: `t0` (inflection ≈ the 15-minute-city threshold), `k` (steepness/curvature), `Lmax` (ceiling). |
| DCF | Deprivation Cost Function — the emergency regime's convex, unbounded (Box-Cox) function of nearest travel time. Parameter `lam` (λ = 1.8) transferred from the DCF literature and consistent with the EMS response benchmarks (negligible below the 3–4 min ideal, the contested 8-min urban response standard,
10–15 min upper target); reported in multiples of g(15 min), so 1.0 = the deprivation of arriving at the 15-minute benchmark. (States before 2026-08-17 are in g(45 min) units, a factor 6.731 larger; ranks, Ginis and every ratio are identical under either anchor — verified to machine precision on the artifact-seeded cities.) |
| 2SFCA | Two-Step Floating Catchment Area — the congestion adjustment: a facility serving many people relative to its capacity inflates the effective travel time of everyone using it. `gamma` (γ) is the exponent (how strongly congestion bites). |
| soft-min (κ) | A smooth minimum over reachable facilities: with several nearby options the effective time is slightly better than the single nearest (substitutability bonus ln(n)/κ). `kappa` (κ) controls the smoothing; κ→∞ = plain nearest. |
| t_eff / t_nearest | Per-service effective (congestion-adjusted, soft-min) travel time / plain nearest-facility time, minutes. |
| t_regime_* | The composite travel time per regime (weighted mean over services) — deprivation-function-free; feeds the level indicators. |
| composite / weights | Regime deprivation = weighted mean of per-service deprivations (school and green sub-types weigh 0.5 each). |
| finite_fill | The large-but-finite time (default 120 min) assigned for a service a routable cell cannot reach within the walk cutoff — keeps the cell on the map at ~maximal deprivation. Level indicators contain this constant. |
| unreachable | A cell with no network path to any facility of any service (masked grey on maps) — distinct from reachable-but-service-deprived. |

### Indicators (city tables)

| term | meaning |
|---|---|
| mean_everyday / mean_emergency | Population-weighted mean deprivation per regime (everyday in [0, 1]; emergency in multiples of g(15 min)). |
| gini_everyday / gini_emergency | Population-weighted Gini (0 = equal, 1 = maximal inequality) of each deprivation surface *within* the city. |
| gini_t_* | The same Gini computed on travel times instead of deprivations — deprivation-function-free companion. |
| divergence_gap | gini_emergency − gini_everyday. Positive = the city's inequality problem is emergency-side; negative = everyday-side. |
| spearman_rho (ρ) | Rank correlation between the everyday and emergency percentile surfaces: do the same areas rank high on both? 0 = unrelated maps; high = the same areas lose twice. |
| LL / LH / HL / HH | The co-location typology at the median split of both percentile surfaces: Low/Low, Low-everyday/High-emergency, High/Low, **High/High = compounding**. At p50 the whole share table has one free number (HH); HH > 25 % = above-independence compounding. |
| compounding_pop_share_50 / _75 | HH population share at the median / 75th-percentile split. |
| compounding_intensity | Population-weighted mean of min(everyday pct, emergency pct) — the continuous compounding measure; anchors: 1/3 independent, 1/2 perfectly coupled, 1/4 divergent. |
| jaccard_high | Overlap of the two "high" sets (intersection / union) — a threshold-based coupling companion to ρ. |
| pop_share_beyond_X | Population beyond X minutes of composite regime time — policy-threshold levels (contain the finite_fill constant; carry that caveat). |
| p90_p50_ratio | 90th / 50th percentile of the surface — tail inequality. |
| elasticity | Slope of log(outcome) on log(population): % change in the outcome per 1 % change in city size. |
| slope_density_* / slope_ses_* | Within-city gradients of deprivation on density / on the harmonised SES covariate, used as cross-city features. |

### Equity / vulnerability tables

| term | meaning |
|---|---|
| SES | Socio-economic status covariates (`ses_*` columns): EU census shares (age, employment, foreign-born) and national grids (rent, ownership…). |
| stratum / level | A population subgroup (e.g. elderly = top-quartile share-65+ cells). `level` names the data layer: `age_census` (EU-harmonised, pooled cross-city), `age_national`, `income_tier2` (national; per-city only, never pooled). |
| covered reference (`*_covered`) | The comparison group restricted to cells where the stratum's SES column is actually published — the honest base (comparing against the whole FUA mixes in the data-coverage geography). |
| ratio / hh_share_gap | Stratum mean deprivation ÷ reference (1 = parity, 1.3 = 30 % more); stratum HH share − reference HH share (0 = parity). |
| concentration index | Income/SES-rank-based inequality measure of deprivation (negative = deprivation concentrated among low-SES cells). |
| coverage_pop_share | Share of the city's population living in cells where the SES column has a value — gate for trusting the stratum. |

### Statistics

| term | meaning |
|---|---|
| country-clustered SE | Standard errors allowing arbitrary correlation of cities within a country — the effective sample for country-level questions is ~24 countries, not 67 cities. |
| wild cluster bootstrap | Resampling scheme (Rademacher signs per country block, null imposed) giving reliable p-values with few clusters — the citable p for the scaling claims. |
| permutation p (p_perm) | For regional contrasts: whole countries reshuffled across regions — the primary test, since region is a property of countries. City-level ANOVA p's are reported as anti-conservative reference only. |
| Cohen f | ANOVA effect size (0.1 small / 0.25 medium / 0.4 large). |
| mixed model | Region fixed effect + country random intercept — triangulation for the regional tests. |
| TOST | Two One-Sided Tests — equivalence testing: positive evidence that a slope lies within ± a bound (vs mere non-significance). `smallest_passing_bound` = the tightest bound the data would support. |
| FE | Fixed effects (country dummies) — within-country version of a regression. |
| HC1 | Heteroskedasticity-robust standard errors (single-city-level regressions). |
| LOO | Leave-one-out: refit dropping each city; the envelope shows no single city carries a result. |
| Cook's distance | Influence measure identifying the most result-moving observation. |
| Huber / median regression | Outlier-robust re-estimates of a slope. |
| silhouette | Cluster-separation score in [−1, 1]; ~0.25 weak / 0.5 reasonable / 0.7 strong. Selects k. |
| ARI | Adjusted Rand Index — agreement of two partitions (1 identical, 0 chance). Used for bootstrap stability, engine comparisons, and cluster-vs-region checks. |
| Gaussian silhouette null | Parametric null: same-covariance multivariate-normal samples put through the same k-selection — is the observed silhouette surprising with NO cluster structure? |
| peeled clustering | The re-clustering with the flagged outlier group removed (fresh scaling, full diagnostics) — "is there a typology among ordinary cities?" |
| specification curve | The headline regression re-estimated under every deprivation parameterisation (curvature grid + form swaps); a claim is robust when the whole curve sits on one side of zero. |
| rank agreement (ρ/τ) | Spearman/Kendall correlation of the *city ranking* under a variant vs baseline — "do city orderings survive the assumption?" (min ρ 0.90 across the curvature grid and everyday form swap; the two emergency escalation swaps change what the emergency Gini measures and are the scoped exceptions — exponential → an extreme-tail-depth ordering, ρ 0.19; bounded survival → a benchmark-window inequality ordering, ρ 0.49 — changes of measurand, reported as such). |
| flip cells | Cells whose typology class changes under any deprivation variant — the spatial footprint of an assumption. Over all 67 cities the population-weighted sensitive share averages 18.1 % (5.2–53.0 %); the complementary ~82 % keeps its class under every parameterisation — including the bounded survival swap, the largest single mover because it reorders the emergency percentile surface hardest. Distinct from the ~24 % *engine* flip (E.1), which is a routing artifact, not an assumption. |
| Layer 1 / 2 / 3 | Sensitivity layers: deprivation curvature / functional-form swap / accessibility model (κ, γ, bandwidth, k-nearest, mode set, unreachable policy). |
| threshold axis | The "how high is high" percentile cut sweep — the dominant lever on the HH share (hence the continuous intensity as headline). |
| degenerate variant | A sensitivity variant where one tie block holds > 50 % of population (e.g. κ = 0.1 floors the core at zero) — flagged and excluded from acceptance ranges. |

### Data and infrastructure

| term | meaning |
|---|---|
| OSM / Overpass | OpenStreetMap and its query API — the facility source (completeness-benchmarked; extractions carry an expiry so all cities share an era). |
| GHS-POP | Global Human Settlement 100 m population grid — the analysis grid. |
| Eurostat Census 2021 grid / GISCO | The EU-harmonised 1 km census grid (age, employment, origin) broadcast onto the 100 m grid (`ses_census_*`); GISCO is Eurostat's geodata service. |
| EMP gap | Employment is voluntary in the census grid; DE and FR did not report it — their cities carry no harmonised SES slope by design (strict mode; never substituted). |
| Zensus / INSEE / CBS | National statistical sources for Tier-2 fine grids (DE 100 m, FR 200 m, NL 100 m). |
| INSPIRE grid id | The EU standard cell identifier (`CRS3035RES100mN…E…`) keying all grids. |
| r5 / R5 | Conveyal's routing engine (via r5py) — the primary travel-time engine over OSM networks. |
| friction (surface) | The 1 km Weiss/Malaria-Atlas cost-distance rasters — the fast routing path, demoted to sensitivity variant after E.1 (levels off 34–314 %, per-cell classes unstable; aggregate shares and ρ survive). |
| OD matrix | Origin–destination travel-time table (cells × facilities) per service and mode; carries a provenance sidecar naming the engine that built it. |
| reverse routing | Routing from the (few) facilities instead of the (many) cells — the transpose that makes an r5 city cost ~minutes. |
| routing budget | The per-run time cap that stops routing cleanly with progress checkpointed (exit 2 = resumable stop, not failure) — why big cities take several "rounds". |
| GTFS | Public-transit schedule format (Tier-2 transit option; not used in any published number). |
| ED | Emergency department (hospital with emergency care). |
| INKAR / BBSR | German federal accessibility indicators — the external benchmark (E.3, passed). |
| ABDA / Krankenhausverzeichnis | German pharmacy / hospital registries — the completeness benchmarks (E.2, passed; counts flagged for re-verification before publication). |
| `depacc-results` | The orphan git branch where every run accumulates its summary tables and figures — the single source for all numbers above. |
