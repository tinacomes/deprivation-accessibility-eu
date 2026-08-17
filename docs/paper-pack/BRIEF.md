# Paper brief — potential-deprivation accessibility across 67 European cities

This is the master briefing for writing the paper. Everything a writer
needs is either in this directory (`data/`, `figures/`), in this
repository (`methods.md`, `docs/results-headlines.md`), or on the
`depacc-results` branch (every persisted table and map). Do not re-derive
numbers — cite them from `data/`.

**Status: the sample is closed and this pack is final.** All 67 cities
are computed on the re-anchored emergency scale (g(15 min), EMS
benchmarks; runs 32012438178 + 32055983121, 2026-08-17), and every table
and figure here is refreshed from that state. `## Provenance` at the
bottom says which file came from where and documents the re-anchor
verification (a controlled rescale, machine-precision checked).

## How to use this pack

1. Read this brief end to end, then `docs/results-headlines.md`
   (headlines + the statistical-tests reading guide + glossary), then
   `methods.md` (authoritative methods; §4.4 covers the cross-city
   analyses and inference). Cite from `references.bib` only — every entry
   there is verified against the publisher's record, and `REFERENCES.md`
   maps each entry to the claim it supports (plus the open citation
   questions). Do not introduce citations from memory.
2. Draft from the skeleton at the bottom. Every claim you write must
   trace to a file in `data/` or on `depacc-results`; the evidence map
   below gives the pairing. The phrasing rules are binding — they encode
   what the analyses can and cannot support.
3. Background (only if needed): `docs/results-summary-and-storyline.md`
   (results audit + storyline history), `docs/validation.md` (E.2–E.5
   evidence), `docs/plan-next-steps.md` (full project history),
   `docs/evidence/depacc_results_evidence.docx` (the human-facing
   evidence document these materials condense — written before Paris's
   final run, so where it disagrees with `data/` or this brief, `data/`
   and this brief win).

## The paper in one paragraph (abstract seed)

Do cities deliver everyday services and emergency care together as they
grow — and do the same residents carry both burdens? We measure
potential deprivation — literature-anchored loss functions of effective
travel time, not raw access — for two regimes (everyday walkable
services via a congestion-adjusted soft-minimum; emergency care via
nearest-facility time under a convex cost anchored on EMS response
benchmarks) on a 100 m grid across 67 European functional urban areas in 24 countries.
City size buys everyday access (elasticity −0.20) but not emergency
relief (−0.06, bounded within ±0.13), and everyday inequality *rises*
with size while emergency inequality is size-flat; the divergence is
structured by country and macro-region, not size — culminating in a
one-dimensional severity ordering of emergency-periphery coverage whose
extreme is five capital-city "emergency deserts" invisible to access
averages. Compounding — the same population deprived in both regimes —
exceeds independence nearly everywhere, is strongest in Central-Eastern
Europe, and falls on families with children in 88 % of cities. All
rank-based results are invariant to the deprivation parameterisation;
the level results are where the calibration carries information access
measures cannot.

## Research questions

RQ1. Does city size deliver everyday access and emergency capability
     together (levels and inequality)?
RQ2. Where do the two deprivations diverge, and what structures the
     divergence (size, country, region, coverage)?
RQ3. Who carries compounding deprivation (co-location typology;
     vulnerability strata)?
RQ4. What does the deprivation framing add over pure access?

## Contribution claims

1. A two-regime *deprivation* (not access) framework: functional forms
   transferred from literature, curvature calibrated to anchors
   (15-minute-city inflection; the EMS response benchmarks — negligible
   below the 3-4 min ideal, the contested 8-min urban response
   standard, 10-15 min upper
   target), substitution (soft-min), congestion (2SFCA), on a 100 m grid,
   comparably across 67 FUAs / 24 countries.
2. Regime-specific agglomeration: size buys everyday access, not
   emergency relief — with the difference itself tested (paired, wild
   p = 0.002/0.028) and the emergency null bounded (TOST).
3. The geography of divergence: country-level regional structure; the
   emergency-coverage severity gradient (covered → partial desert →
   desert) replacing any city typology; deserts invisible to access
   averages.
4. Compounding and its carriers: above-independence co-location nearly
   everywhere; children the consistently burdened stratum at the
   European level.
5. A robustness architecture usable as a template: rank-invariance by
   construction, specification curve, rank agreement, engine
   cross-check, access-based re-estimation of every headline.

## Evidence map (claim → number → data file → figure)

| # | Claim | Key numbers | Table (data/) | Figure (figures/) |
|---|---|---|---|---|
| H1 | Size buys everyday access, not emergency care | ev elasticity −0.196 (wild p 2e-4, R² .44); em −0.059 (clustered p .16, wild p .21; TOST bound ±0.13); paired diff +0.137 (wild p .002); LOO [−.204,−.185] | inference_scaling_clustered, inference_equivalence, inference_regime_paired, inference_influence | scaling_elasticity.png |
| H2 | Everyday inequality grows with size, emergency doesn't | gini_ev slope +0.062 (wild p .0012); gini_em +0.004 (wild p .84); paired diff −0.058 (wild p .029, 67 cities); spec curve +0.026..+0.075, 12/13 significant; emergency null holds under curvature + everyday swap, FLIPS under the benchmark-anchored exponential (+0.098, p .0003 — state it) | inference_scaling_clustered, inference_regime_paired, specification_curve | specification_curve.png |
| H3 | Country-level regional structure | gini_em f .74 p_perm .0024; gap p_perm .010; ρ p_perm .0015; compounding p_perm .0008 / .0023; gini_ev NOT regional (p_perm .27) | inference_regional | region_strips.png |
| H4 | No city types — a coverage severity gradient + desert group | main k-means 62/5 (sil .65, bootstrap ARI .87, null p .001, ARI-vs-region .001); Ward nests inside it 65/2; peeled 48/14 same axis (sil .38, ARI .74, p .001, ARI-vs-region .07), Ward nested 56/6; feature-set robustness: main ARI 1.00, peeled ARI .97 (cluster_feature_robustness) | cluster_null, cluster_null_peeled, cityvector_clustered(_peeled) | cityplane.png |
| H5 | Children carry it almost everywhere; elderly locally | children ratio 1.27, >1 in 88 % of cities, HH gap +0.13 (CEE 1.44, North 1.30); elderly 0.96, 37 % | vulnerability_summary, vulnerability | vulnerability_strata.png |
| H6 | Compounding is the norm | HH mean 33 % vs 25 % independence, above it in 66/67 cities; ρ ∈ [−0.02, 0.74]; threshold moves HH ~6× more than any access knob | cityplane (compounding_*), typology_share_envelope, per-city acceptance tables on depacc-results | rho_ranked.png, compounding_gallery.png |
| H7 | Deprivation ≠ access; claims survive both | ev median-time elasticity −0.237 (p 3.8e-5) but R² .16 vs .44; Gini corr .965/.976; Bucharest median time 0.71× sample vs deprivation 2.81×; grade sets the LEVEL above all (Wald p 1.3e-15); slope × grade interaction p .010 under the current 48/14/5 grades (p .17 under the pre-refresh 50/12/5 — quote as level-first, slope-interaction secondary) | deprivation_vs_access, desert_access_contrast, scaling_by_grade | scaling_by_coverage_grade.png |
| — | Size gradient of divergence measures | gap slope −0.066/log10 (p .012); weak (R² .06) | size_gradient, regime_slope_difference | size_gradient.png |
| — | Sample | 67 FUAs, 24 countries, 113.9 M people, 101 k–12.9 M | cities_descriptives, cityplane | (Table 1 material) |
| — | Facilities routed to | median per FUA: 93 GPs, 228 pharmacies, 325 supermarkets, 409 schools, 636 green spaces, 6 EDs, 6 ambulance stations; median pop-weighted walk 4–8 min per everyday service, 12 min car to either emergency service | accessibility_by_service_pooled, accessibility_by_service_cities | (Methods table) |

## The deprivation layer's own robustness (the referee's first question)

The paper measures deprivation, not access, so the loss functions are the
thing to attack. Three artefacts answer that attack directly, and the
answer has two halves that must both be stated.

**What is varied** — `figures/deprivation_curves.png` draws the functions
themselves: the baseline everyday DLF and emergency DCF, the Layer-1
curvature grid (`k` ∈ {0.1, 0.2, 0.3} × `t0` ∈ {10, 15, 20} minutes;
λ ∈ {1.4, 1.8, 2.2}), the Layer-2 form swaps calibrated to the *same*
domain anchors (concave Box-Cox DLF; exponential DCF), and — the
comparison the framing rests on — the **linear loss that a pure-access
minutes average implies**, matched to the baseline at 45 minutes. The gap
between that straight line and the calibrated curves is the paper's
methodological claim in one picture: near the clinical threshold the DCF
prices a marginal minute far more heavily than any average can, and past
the 15-minute anchor the saturated DLF prices it far less.

**How far the results move** — `data/deprivation_sensitivity_summary.csv`,
per city × sweep axis, baseline / min / max / width:

| axis | gini_everyday | gini_emergency | HH share |
|---|---:|---:|---:|
| curvature (Layer 1) | 0.244 | 0.170 | 0.014 |
| form swap (Layer 2) | 0.035 | 0.484 | 0.007 |
| "how high is high" threshold | — | — | 0.298 |

The form-swap gini_emergency envelope (0.484) is dominated by the
benchmark-anchored exponential, which prices the beyond-threshold tail
~10× harder than the Box-Cox at 60 min — see the H2 exception in
`docs/results-headlines.md`: under that variant the emergency-Gini size
slope flips positive and significant and the city ranking reorders
(ρ = 0.19). State it as the boundary of the null's validity, never
average over it.

(median envelope width across the 67 cities.) Read it as the two-sided
claim the framing rules demand. **Levels are not robust and are not meant
to be**: curvature moves a city's everyday Gini by a quarter of a Gini
point, which is exactly why the calibration carries information and why
the *slope* claims are defended by the specification curve rather than by
any single parameterisation. **Ranks and classes are robust**: the same
curvature moves the compounding share by 1.4 pp, the form swap by 0.7 pp
(the typology is rank-based, so even the harsh exponential barely
touches it), against 29.8 pp for the threshold choice — the threshold
dominates curvature by ~21×, which is why the continuous
`compounding_intensity` is the headline and the class shares always
travel with a threshold sweep. City-level *Gini orderings* are robust
with the same scoped exception: rank agreement min ρ 0.90 over the
curvature grid and everyday form swap; the benchmark-anchored
exponential reorders the emergency-Gini ranking (ρ = 0.19) exactly
because it changes what the Gini measures there.

**What survives dropping the layer entirely** — H7 above
(`deprivation_vs_access.csv`): the everyday gradient and the emergency
non-gradient are both there in plain minutes, so no headline depends on
the deprivation functions; what the functions add is a better-behaved
outcome (R² 0.44 vs 0.16) and the deserts, which access averages hide.

Robustness inventory (cite as a block): rank agreement min ρ
.90/.95/.98 for gini_everyday / divergence_gap / gini_emergency over the
curvature grid + everyday form swap (rank_agreement.csv, 67 cities; the
benchmark-anchored exponential is the flagged exception, emergency ρ
.19); deprivation-variant flip-cell share 15.8 % of population on
average, 5.2–36.1 % across the 67 cities (flip_cells.csv), with the HH
class share moving 1.9 pp on average and 5.7 pp at most
(typology_share_envelope.csv); the clustering feature-set check (main
partition ARI 1.00, peeled .97 with the benchmark shares included —
cluster_feature_robustness.csv); engine
cross-check E.1 (friction levels off 34–314 %, class shares ≤0.7 pp, per
this repo's methods §7.1 — per-cell maps carry a ~24 % *engine* flip
caveat, a separate and larger number than the assumption flip above);
OSM completeness E.2 (DE pharmacy 0.976, hospital 1.24) and INKAR
external benchmark E.3 passed (`docs/validation.md`).

## Framing rules (binding)

- **Deprivation, not access.** Access measures the network (minutes);
  deprivation measures anchored welfare burden. Use H7's three moves:
  claims robust to dropping the deprivation layer; deprivation the
  better-behaved outcome (R² .44 vs .16 — the DLF discounts
  welfare-irrelevant variation); deserts invisible to access averages.
  Never present the deprivation functions as decoration on travel times.
- **Robust-to-g, meaning-from-g.** Rank-based results (typology, ρ, city
  orderings) are near-invariant to the deprivation parameterisation —
  say so; level/inequality results are where calibration carries
  information — say that too.
- **Gradient, not types.** k-means output is a severity ordering on one
  axis (emergency-periphery coverage). Never present the 62/5 or 50/12
  splits as a city typology, and never say the two algorithms "agree on"
  a group — Ward cuts the same axis more conservatively (65/2, 56/6),
  nesting inside k-means. That nesting is the evidence for a gradient;
  writing it as agreement would claim a discrete type the data denies.
- **Coverage grades are the clustering, not a threshold.** covered (48) /
  partial desert (14) / desert (5) come from the two clustering passes
  (`dep_vs_access.coverage_grades`). Do not re-cut them on a hand-set
  threshold. The covered/partial boundary is explicitly fuzzy: the
  pre-refresh extraction state put Brăila and Łomża on the covered side
  (50/12), the refreshed state and the extended-feature check both put
  them partial — quote the boundary as soft, the ordering as robust.
- **Space-for-time.** Every size gradient is cross-sectional. No causal
  or longitudinal language ("as cities grow" only with the
  space-for-time qualifier stated once, early).
- **Three-level vulnerability rule.** Pool only census-harmonised strata
  across cities; national/income strata are per-city depth (Hamburg
  elderly 1.37× is `age_national`, NOT the European claim — the European
  elderly result is a null, 0.96).
- **Inference at the country level.** Cite wild-bootstrap p's for
  scaling, country-permutation p's for regions. City-level ANOVA p's are
  anti-conservative reference only.

## Phrasing rules / prohibited claims

- Emergency scaling: "no detectable size gradient, bounded within
  ±0.13" — never "proven flat" (TOST does not pass at ±0.10).
- No regional everyday-Gini claim (p_perm = 0.28).
- No European elderly-compounding claim (median 0.96).
- No absolute travel times or Gini levels from the friction engine; no
  per-cell class readings from any map (patterns only, ~24 % engine flip).
- Everyday-Gini slope robustness: name the exception (Box-Cox form swap,
  +0.026, p = 0.083).
- Coverage grades: lead with the level ("coverage class, not city size,
  sets emergency deprivation", Wald p ≈ 1e-15). The slope × grade
  interaction is p = 0.010 under the current 48/14/5 grades but was
  p = 0.17 under the pre-refresh 50/12/5 — a two-city membership change
  flips it, so treat it as boundary-sensitive and never headline it.
- Emergency-Gini null and rank agreement: always scope to "the
  calibrated Box-Cox family and anchor-matched form swaps", and state
  the benchmark-anchored-exponential exception (slope +0.098, p .0003;
  emergency rank ρ .19). Never claim form-universality.
- Level indicators (`pop_share_beyond_*`) contain the finite-fill
  constant — footnote when used.
- The everyday composite time above the walk cutoff behaves as a count
  of unmet service categories, not a travel time (methods §4.2 caveat).

## Methods facts the writer needs (full text: methods.md)

Sample: F.2 stratified draw, 4 macro-regions × 4 size strata, 67 FUAs,
24 countries. Grid: GHS-POP 100 m. Facilities: OSM/Overpass,
expiry-refreshed extractions. Routing: r5 over OSM (walk everyday, car
emergency; reverse-routed); friction is the declared sensitivity
variant (E.1). Everyday deprivation: per-service logistic DLF of
congestion-adjusted (2SFCA) soft-min effective time, t0 = 15 min anchor;
composite = weighted mean of per-service deprivations. Emergency:
convex Box-Cox DCF of nearest time, λ = 1.8 (transferred; anchor-solved
1.89–1.95 coincides), anchored on the EMS response benchmarks — negligible
below the 3–4 min ideal, the contested 8-min urban response standard,
10–15 min upper
target — and reported in multiples of g(15 min). The 8-min mark is NOT a
half-max (convexity caps g(8)/g(15) at 0.427): state the two regimes'
anchor structures as genuinely different. Typology: population-weighted percentile split per regime at
p50 (p75 companion); continuous compounding_intensity as the headline
compounding measure. Equity: census-2021 1 km strata broadcast to the
grid; covered-cell reference. Inference conventions per §4.4.

## Limitations to state

Cross-sectional space-for-time; census EMP missing for DE/FR (no
harmonised SES slope there, by design); walk/car only (transit
deliberately out of scope; say so); 1 km census broadcast vs 100 m grid;
engine sensitivity of per-cell classes; emergency-side external benchmark
(INKAR) unavailable; finite-fill constant inside level indicators.

**OSM facility completeness — two specifics, both from
`accessibility_by_service_cities.csv`, both to state rather than
smooth over.**

*GP density varies by a factor of ~12 across countries in a way that is
about tagging conventions, not health systems*: the median FUA has
10.8 mapped GPs per 100 k, but the medians are 2.1 in SE, 2.3 in PT,
2.6 in FI and 3.5 in IT against 24.5 across the West. In the Nordics and
southern Europe primary care sits in health centres that OSM tags
differently from `amenity=doctors`, so the GP layer under-counts there
and those cities' everyday deprivation levels are correspondingly
overstated. What this does **not** do is bias the size gradients: mapped
GP density is uncorrelated with city size (log-log slope +0.09,
country-clustered p = 0.29; −0.00 with country fixed effects), and every
scaling claim is country-clustered. Treat it as a reason not to compare
everyday *levels* across countries — and as one plausible reason the
everyday-Gini regional contrast does not survive country-level testing
(H3). The E.2 registry benchmark covers DE only and would not have caught
this; the per-city facility counts do.

*Eight cities have only one of the two emergency services mapped* —
Athina, Brăila, Helsinki, Lahti, Norrköping, Szeged, Talavera de la Reina
and Žilina (Szeged missing the ED hospital, the other seven missing
ambulance stations). The composite renormalises its weights over the
services present (methods §4), so their emergency surface measures
proximity to the one mapped service. Their median mean-emergency
deprivation is 0.197 against 0.169 for the rest — the expected direction
and a modest size, and none of them is in the desert group, so no
headline turns on it. `cities_descriptives.csv` carries
`n_emergency_services` so Table 1 shows it; say it in the limitations and
move on.

Registry ratio flags (DE hospital/pharmacy) still to re-verify before
submission (`docs/validation.md`).

## Provenance of the files in `data/` and `figures/`

Every table and figure here traces to the final 67-city state; nothing
is awaiting a rerun.

- **From `depacc-results` `cross/` and `sensitivity/`** (CI output of
  the re-anchor runs 32012438178 + 32055983121): every data table and
  every figure in this pack — the persist whitelist now covers the
  deprivation-vs-access, descriptives, per-service accessibility,
  sensitivity-summary and feature-robustness files, so CI produces the
  whole pack surface from now on.
- **Recomputed locally over that same state**:
  `cluster_feature_robustness.csv` (tools/cluster_feature_robustness.py,
  also pushed to the branch). A local `depacc cross` reproduced the CI
  cross tables to ~1e-13 in the pre-anchor verification, so local and CI
  are one state.
- **Copied per city from `depacc-results`**: `figures/cities/<city>.png`,
  the median-split compounding map of each of the 67 cities, with an
  index in `figures/cities/README.md`. The percentile surfaces, the p75
  maps and the core zooms stay on the branch (~30 MB).
- **Re-unioned once more**: `flip_cells` and `typology_share_envelope`
  are built only from cities whose cell-level surfaces a run stages, and
  the truncation recurred at the seed round because the collect's import
  step didn't restore the accumulating tables before the harness merge —
  both halves of the fix are now in (harness merges; import restores),
  and the current union is 64 cities from run 32012438178 + 3 from
  32055983121, every row on the new variant set.

**The re-anchor, executed and verified (2026-08-17).** The emergency
reporting anchor moved g(45) → g(15) (EMS benchmarks, methods §3) and
the Layer-2 exponential swap was recalibrated to the same 8/15-min
anchors. Two batch runs carried it out. Run 32012438178 recomputed 64
cities from cached OD matrices; Berlin, Madrid and Paris fell victim to
GitHub's 10 GB cache-eviction limit (their continental PBFs alone exceed
it), started re-routing from scratch and budget-stopped — so run
32055983121 seeded their complete pre-anchor derived state from stored
artifacts (the batch's new `seed_map` input) and recomputed
deprivation-onward. That seeding makes the verification exact: for those
three cities every rank-based indicator (Ginis, ρ, typology shares,
percentiles) is **identical to machine precision** (max |Δ| ≈ 1e-16) and
the level ratio equals g(45)/g(15) = 6.7307 to 1e-15 — the controlled
rescale, demonstrated rather than asserted. The remaining 64 cities were
byte-identical between the two runs. Side effect to know: four small
cities (Chemnitz, Caserta, Milano, Palma de Mallorca) had lost their raw
caches too and picked up **refreshed OSM extractions**, moving their
rows by up to a few percent — which nudged fourth-decimal inference
values, shifted the peeled clustering boundary by two cities
(50/12 → 48/14, see H4), and flipped the boundary-sensitive
slope × grade interaction (see H7). All prose and audit numbers in this
pack are from the final consistent state.

Every number this brief and `docs/results-headlines.md` quote is checked
against its source table by `tools/audit_paper_pack.py` (133 checks, run
in CI). Re-run it after editing any claim or refreshing any table.

Still open, and outside the results: the DE registry counts carry
verify-before-publication flags (`docs/validation.md`).

## Suggested skeleton

1. **Introduction** — 15-minute city vs emergency capability; the
   compounding question; deprivation-not-access framing (RQ1–4).
2. **Methods** — condensed from methods.md §§1–5 + §4.4; Table 1 =
   sample composition + descriptives (cities_descriptives.csv).
3. **Results**
   3.1 Regime-specific agglomeration (H1, Fig scaling_elasticity).
   3.2 Inequality scales with size only for the everyday regime (H2,
       Fig specification_curve as robustness inset).
   3.3 The geography of divergence (H3 + H4: Fig cityplane with
       envelope whiskers, Fig region_strips; the severity gradient,
       Fig scaling_by_coverage_grade; desert contrast table).
   3.4 Compounding and its carriers (H6 + H5: Fig rho_ranked,
       Fig vulnerability_strata, Fig compounding_gallery).
   3.5 Deprivation vs access (H7 table; fold into 3.1–3.3 if tight).
4. **Robustness** — lead with the deprivation layer itself (Fig
   deprivation_curves: what is varied, and the pure-access line it is
   varied against; the envelope table: levels move, ranks do not), then
   the inventory block (spec curve, rank agreement, engine check,
   threshold-vs-knob dominance). Most of it can live in SI with one
   summarising paragraph, but the curve figure earns a main-text slot in
   a paper whose contribution is the deprivation framing.
5. **Discussion** — regime-specific agglomeration meets national
   emergency-system geography; policy: everyday inequality is a big-city
   problem, emergency deprivation a national-coverage problem; children
   as the systematic carriers.
6. **SI** — per-city table (cities_descriptives), the 67 per-city
   compounding maps (`figures/cities/`, indexed in its README), all
   sensitivity tables, validation (E.1–E.5), the glossary and stats guide
   from docs/results-headlines.md.
