# Paper brief — potential-deprivation accessibility across 67 European cities

This is the master briefing for writing the paper. Everything a writer
needs is either in this directory (`data/`, `figures/`), in this
repository (`methods.md`, `docs/results-headlines.md`), or on the
`depacc-results` branch (every persisted table and map). Do not re-derive
numbers — cite them from `data/` and check `## Pending` below for the few
that may still refresh.

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
   evidence document these materials condense).

## House style: PNAS, after Musso et al. (2026)

The model paper is **Musso, Rybski, Helbing & Neffke (2026), "Large
cities lose their growth advantage as countries urbanize", PNAS 123(26)
e2529430123, doi:10.1073/pnas.2529430123** — already this project's
methodological anchor for space-for-time inference, and now the style
template. Write to its conventions:

- **Structure**: title (a finding, not a topic) → Abstract (~180 words,
  numbers in it) → *Significance* box (~100 words, lay-readable) → short
  framed Introduction (the two competing readings, then "we analyse
  which") → numbered **Results** sections that carry the argument →
  Discussion → Materials & Methods at the end (compressed; depth in SI).
- **Voice**: short declarative sentences; the number immediately after
  the claim ("The numbers speak clearly: …"); present tense for results;
  every figure referenced in order and doing argumentative work; no
  hedging where a bound exists (state the bound instead).
- **Figures**: multi-panel composites lettered A–D; definitional insets
  inside panels (their Fig. 1C carries the β-definition inset and a
  density inset — our Fig. 1 mirrors this grammar); captions that
  restate the finding, not just the encoding; methods details pushed to
  captions and SI sections referenced as "Section X.Y".
- **Tables**: few and small in the main text (their Table 1 = the
  datasets, Table 2 = one regression); everything else SI.

### Figure plan (main text)

| Fig | Content | File(s) in `figures/` |
|---|---|---|
| 1 | The sample and the central quantity: Europe map of the 67 FUAs, colour = divergence gap, size = population, desert rings; definition inset (mini city plane) + density inset — Musso Fig. 1C grammar | `fig1_sample_map.png` (script: `scripts/make_map.py`) |
| 2 | Regime-specific agglomeration: mean deprivation vs size by regime (A), everyday-vs-emergency inequality slopes with the spec-curve robustness inset (B) | `scaling_elasticity.png`, `specification_curve.png` |
| 3 | The geography of divergence: regional strips (A), the coverage-grade scaling panels (B), desert access-contrast (C, table-in-figure) | `region_strips.png`, `scaling_by_coverage_grade.png`, `data/desert_access_contrast.csv` |
| 4 | Compounding and its carriers: ranked coupling ρ (A), vulnerability strata (B), compounding-map gallery excerpt (C) | `rho_ranked.png`, `vulnerability_strata.png`, `compounding_gallery.png` |
| M&M / SI | Methods overview schematic: places → travel times → anchored deprivation functions → typology and indicators | `fig_methods_overview.png` (script: `scripts/make_methods_fig.py`) |

Main-text Table 1 = sample composition + key descriptives
(`cities_descriptives.csv`); Table 2 = the country-clustered scaling
elasticities (`inference_scaling_clustered.csv`). Everything else SI.
The panel composites (Figs 2–4) are assembled from the listed singles at
layout time; regenerate any single from `depacc-results` if numbers
refresh.

## Significance statement (seed, ~100 words)

Cities are expected to bring services closer to people as they grow.
Whether that promise covers *urgent* care as well as daily needs — and
whether the same residents miss out on both — has been unmeasurable
across countries. Comparing walking access to everyday services with
driving access to emergency care in 67 European city regions, we find
city size improves daily access but not emergency protection, and that
the two deprivations concentrate in the same places, most strongly in
Central-Eastern Europe and among families with children. Five capital
regions are "emergency deserts" that standard access statistics cannot
see. Where a city grows does not decide who is protected; national
coverage does.

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
| H1 | Size buys everyday access, not emergency care | ev elasticity −0.196 (wild p 2e-4, R² .44); em −0.058 (p .17; TOST bound ±0.13); paired diff +0.14 (p .002); LOO [−.20,−.18] | inference_scaling_clustered, inference_equivalence, inference_regime_paired, inference_influence | scaling_elasticity.png |
| H2 | Everyday inequality grows with size, emergency doesn't | gini_ev slope +0.062 (p .0014); gini_em +0.005 (ns); paired diff −0.057 (wild p .028, 67 cities); spec curve +0.02..+0.08, 12/13 significant | inference_scaling_clustered, inference_regime_paired, specification_curve | specification_curve.png |
| H3 | Country-level regional structure | gini_em f .77 p_perm .002; gap p .012; ρ p .0016; compounding p ≤.002; gini_ev NOT regional (p .33) | inference_regional | region_strips.png |
| H4 | No city types — a coverage severity gradient + desert group | main 62/5 (sil .65, ARI .88, null p .001, ARI-vs-region .07); peeled 50/12 same axis (sil .38, ARI .77, p .001) | cluster_null, cluster_null_peeled, cityvector_clustered(_peeled) | cityplane.png |
| H5 | Children carry it almost everywhere; elderly locally | children ratio 1.27, >1 in 88 % of cities, HH gap +0.14; elderly 0.96, 37 % | vulnerability_summary, vulnerability | vulnerability_strata.png |
| H6 | Compounding is the norm | HH mean 33 % vs 25 % independence; ρ ∈ [−0.02, 0.74]; threshold moves HH ~6× more than any access knob | cityplane (compounding_*), per-city acceptance tables on depacc-results | rho_ranked.png, compounding_gallery.png |
| H7 | Deprivation ≠ access; claims survive both | ev median-time elasticity −0.237 (p<1e-4) but R² .16 vs .44; Gini corr .965/.977; Bucharest median time 0.7× sample vs deprivation 2.8×; grade interaction p .010 | deprivation_vs_access, desert_access_contrast, scaling_by_grade | scaling_by_coverage_grade.png |
| — | Size gradient of divergence measures | gap slope −0.065/log10 (p .014); weak (R² .06) | size_gradient, regime_slope_difference | size_gradient.png |
| — | Sample | 67 FUAs, 24 countries, 113.9 M people, 101 k–12.9 M | cities_descriptives, cityplane | (Table 1 material) |

Robustness inventory (cite as a block): rank agreement min ρ .89/.94/.96
(rank_agreement.csv); flip-cell shares (flip_cells.csv); engine
cross-check E.1 (friction levels off 34–314 %, class shares ≤0.7 pp, per
this repo's methods §7.1 — per-cell maps carry a ~24 % flip caveat);
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
  splits as a city typology.
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
- No regional everyday-Gini claim (p_perm = 0.33).
- No European elderly-compounding claim (median 0.96).
- No absolute travel times or Gini levels from the friction engine; no
  per-cell class readings from any map (patterns only, ~24 % engine flip).
- Everyday-Gini slope robustness: name the exception (Box-Cox form swap,
  p = 0.16).
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

## Pending (check before submission)

Paris's refreshed-extraction rerun may nudge its row and the cross
tables marginally (paired-Gini p currently 0.028 on 67 rows with
Paris's persisted row; spec-curve baseline +0.065 with one stale Paris
sensitivity table). Re-pull final values from `depacc-results`
`cross/` + `sensitivity/` once Paris's final collect lands, and refresh
`data/` here (`git fetch origin depacc-results`). The three
dep-vs-access tables in `data/` were computed on the 67-city state
locally; CI-generated versions land on `depacc-results` after the next
collect and should replace them. DE registry counts carry
verify-before-publication flags (`docs/validation.md`).

## Suggested skeleton (PNAS order)

1. **Title options** (a finding, not a topic): "Cities deliver everyday
   access but not emergency protection as they grow" / "Urban growth
   narrows daily-access gaps but leaves emergency deserts behind".
2. **Abstract** (seed above) + **Significance** (seed above).
3. **Introduction** (~5 short paragraphs): the 15-minute-city promise vs
   emergency capability; the two-regime measurement gap; what we build
   (two anchored deprivation measures, 67 FUAs/24 countries); the
   findings preview in one paragraph with numbers; deprivation-not-access
   framing stated up front (RQ1–4).
4. **1. Results** (numbered subsections, one per figure)
   1.1 The sample and the divergence landscape (Fig. 1 — the map).
   1.2 City size buys everyday access, not emergency protection
       (Fig. 2A; H1; TOST bound stated, not hedged).
   1.3 Everyday inequality scales; emergency inequality does not
       (Fig. 2B + spec-curve inset; H2).
   1.4 The divergence is national, not size-driven: regions, the
       coverage-severity gradient, deserts invisible to access averages
       (Fig. 3; H3 + H4 + H7's desert contrast).
   1.5 Compounding and who carries it (Fig. 4; H6 + H5).
5. **2. Discussion** — regime-specific agglomeration meets national
   emergency-system geography; everyday inequality is a big-city
   problem, emergency deprivation a national-coverage problem; children
   as the systematic carriers; limitations paragraph (list above).
6. **3. Materials and Methods** (compressed; `fig_methods_overview.png`
   as the schematic) — condensed from methods.md §§1–5 + §4.4; point
   every detail to SI.
7. **SI** — per-city table, all sensitivity/robustness tables (spec
   curve, rank agreement, engine check E.1, threshold-vs-knob), the
   deprivation-vs-access full table, validation E.2–E.5, glossary and
   stats guide from docs/results-headlines.md.
