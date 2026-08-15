# Paper brief — potential-deprivation accessibility across 67 European cities

This is the master briefing for writing the paper. Everything a writer
needs is either in this directory (`data/`, `figures/`), in this
repository (`methods.md`, `docs/results-headlines.md`), or on the
`depacc-results` branch (every persisted table and map). Do not re-derive
numbers — cite them from `data/`.

**Status: the sample is closed and this pack is final.** All 67 cities
have completed routing (the last, Paris, on 2026-08-14, batch run
31816777776), and every table and figure here was refreshed from the
final cross-city state afterwards. `## Provenance` at the bottom says
which file came from where.

## How to use this pack

1. Read this brief end to end, then `docs/results-headlines.md`
   (headlines + the statistical-tests reading guide + glossary), then
   `methods.md` (authoritative methods; §4.4 covers the cross-city
   analyses and inference).
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
nearest-facility time under a clinically anchored convex cost) on a
100 m grid across 67 European functional urban areas in 24 countries.
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
   (15-minute-city inflection; 45/60-min clinical time-to-care),
   substitution (soft-min), congestion (2SFCA), on a 100 m grid,
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
| H1 | Size buys everyday access, not emergency care | ev elasticity −0.196 (wild p 2e-4, R² .44); em −0.058 (clustered p .17, wild p .21; TOST bound ±0.13); paired diff +0.138 (wild p .0018); LOO [−.204,−.185] | inference_scaling_clustered, inference_equivalence, inference_regime_paired, inference_influence | scaling_elasticity.png |
| H2 | Everyday inequality grows with size, emergency doesn't | gini_ev slope +0.062 (wild p .0014); gini_em +0.005 (wild p .82); paired diff −0.057 (wild p .028, 67 cities); spec curve +0.026..+0.075, 12/13 significant | inference_scaling_clustered, inference_regime_paired, specification_curve | specification_curve.png |
| H3 | Country-level regional structure | gini_em f .74 p_perm .0022; gap p_perm .010; ρ p_perm .0016; compounding p_perm .0008 / .0023; gini_ev NOT regional (p_perm .28) | inference_regional | region_strips.png |
| H4 | No city types — a coverage severity gradient + desert group | main k-means 62/5 (sil .65, bootstrap ARI .88, null p .001, ARI-vs-region .001); Ward nests inside it 65/2 (ARI vs k-means .52); peeled 50/12 same axis (sil .38, ARI .77, p .001, ARI-vs-region .06), Ward again nested 56/6 | cluster_null, cluster_null_peeled, cityvector_clustered(_peeled) | cityplane.png |
| H5 | Children carry it almost everywhere; elderly locally | children ratio 1.27, >1 in 88 % of cities, HH gap +0.14 (CEE 1.44, North 1.30); elderly 0.96, 37 % | vulnerability_summary, vulnerability | vulnerability_strata.png |
| H6 | Compounding is the norm | HH mean 33 % vs 25 % independence, above it in 66/67 cities; ρ ∈ [−0.02, 0.74]; threshold moves HH ~6× more than any access knob | cityplane (compounding_*), typology_share_envelope, per-city acceptance tables on depacc-results | rho_ranked.png, compounding_gallery.png |
| H7 | Deprivation ≠ access; claims survive both | ev median-time elasticity −0.237 (p 3.8e-5) but R² .16 vs .44; Gini corr .965/.977; Bucharest median time 0.71× sample vs deprivation 2.81×; grade sets the LEVEL (Wald p 1.8e-17), not the slope (interaction p .17) | deprivation_vs_access, desert_access_contrast, scaling_by_grade | scaling_by_coverage_grade.png |
| — | Size gradient of divergence measures | gap slope −0.066/log10 (p .014); weak (R² .06) | size_gradient, regime_slope_difference | size_gradient.png |
| — | Sample | 67 FUAs, 24 countries, 113.9 M people, 101 k–12.9 M | cities_descriptives, cityplane | (Table 1 material) |

Robustness inventory (cite as a block): rank agreement min ρ
.90/.94/.96 for gini_everyday / divergence_gap / gini_emergency
(rank_agreement.csv, 67 cities, 12 variants); deprivation-variant
flip-cell share 15.6 % of population on average, 5.2–35.6 % across the
67 cities (flip_cells.csv), with the HH class share moving 1.9 pp on
average and 5.7 pp at most (typology_share_envelope.csv); engine
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
- **Coverage grades are the clustering, not a threshold.** covered (50) /
  partial desert (12) / desert (5) come from the two clustering passes
  (`dep_vs_access.coverage_grades`). Do not re-cut them on a
  beyond-30-minute share: a hand-set threshold produces a different
  partition and a different interaction p.
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
- Coverage grades: "the grade sets the level, not the slope" — the
  slope × grade interaction is p = 0.17 and must not be reported as a
  differential size gradient.
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
convex Box-Cox DCF of nearest time, λ = 1.8, reported in multiples of
g(45 min). Typology: population-weighted percentile split per regime at
p50 (p75 companion); continuous compounding_intensity as the headline
compounding measure. Equity: census-2021 1 km strata broadcast to the
grid; covered-cell reference. Inference conventions per §4.4.

## Limitations to state

Cross-sectional space-for-time; OSM facility completeness
(benchmarked in DE, ratio flags to re-verify before submission);
census EMP missing for DE/FR (no harmonised SES slope there, by
design); walk/car only (transit deliberately out of scope; say so);
1 km census broadcast vs 100 m grid; engine sensitivity of per-cell
classes; emergency-side external benchmark (INKAR) unavailable;
finite-fill constant inside level indicators.

## Provenance of the files in `data/` and `figures/`

Every table and figure here traces to the final 67-city state; nothing
is awaiting a rerun.

- **From `depacc-results` `cross/` and `sensitivity/`** (CI output of
  batch run 31816777776, the run that closed Paris): `cityplane`,
  `cityvector_clustered(_peeled)`, `cluster_null(_peeled)`,
  `inference_*`, `scaling`, `size_gradient`,
  `regime_slope_difference`, `vulnerability(_summary)`,
  `specification_curve`, `rank_agreement`, and every figure except
  `scaling_by_coverage_grade.png`.
- **Recomputed locally over that same state** (`depacc cross`, which now
  emits them — earlier packs predated the code):
  `deprivation_vs_access`, `desert_access_contrast`, `scaling_by_grade`,
  `cities_descriptives`, and `scaling_by_coverage_grade.png`. A local
  `depacc cross` reproduces every CI cross table to ~1e-13, so the two
  sources are one state.
- **Reconstructed as the 67-city union**: `flip_cells` and
  `typology_share_envelope`. Both are built only from the cities whose
  cell-level surfaces are staged in a run, and the persisted copies had
  been overwritten down to the last batch's cities; the union was
  recovered from the `depacc-results` history and the harness now merges
  instead of replacing.

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
4. **Robustness** — the inventory block (spec curve, rank agreement,
   engine check, threshold-vs-knob dominance) — most of it can live in
   SI with one summarising paragraph.
5. **Discussion** — regime-specific agglomeration meets national
   emergency-system geography; policy: everyday inequality is a big-city
   problem, emergency deprivation a national-coverage problem; children
   as the systematic carriers.
6. **SI** — per-city table, all sensitivity tables, validation (E.1–E.5),
   the glossary and stats guide from docs/results-headlines.md.
