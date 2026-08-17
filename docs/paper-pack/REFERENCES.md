# Bibliography — claim map and open questions

Companion to [`references.bib`](references.bib). Every entry was verified
against the publisher's record (authors, venue, volume, pages, DOI) on
2026-08-15; none is cited from memory. This file maps each reference to
the claim it supports, so a writer knows what to cite where — and lists
the open questions to settle with the PI before submission.

## Claim map

### The deprivation framework (methods §3, contribution claim 1)

| cite | supports |
|---|---|
| `holguinveras2013objective` | The concept: deprivation cost as the economic valuation of suffering from lack of access — the framing that separates deprivation from access. **The anchor citation for "deprivation, not access".** |
| `holguinveras2016econometric` | Deprivation cost functions are estimable and convex in deprivation time — licence for the calibrated-curvature approach. |
| `wang2017deprivation` | The everyday DLF's logistic S-form ("form transferred": saturating severity of substitutable services). Van Wassenhove co-authors both lines, tying DLF and DCF to one literature. |
| `cantillo2018discrete` | Discrete-choice estimation of deprivation costs — the empirical line the convex DCF form comes from. |
| `macea2018attitudes` | Attitudes/perceptions in DCF estimation (hybrid latent-variable discrete choice) — completes the Cantillo-line block. |
| `delgadolindeman2019ambulance` | DCFs specifically for *emergency medical* services, higher than goods-deprivation estimates — the emergency regime's own anchor. |

### Access measurement (RQ4 / H7 — what we improve over)

| cite | supports |
|---|---|
| `nicoletti2023disadvantaged` | The access-based urban-infrastructure-equity baseline (54 cities, minutes/proximity metrics). Cite in the introduction as the line this study extends — H7 shows what the anchored deprivation layer adds over exactly this kind of measure. |
| `wu2025global` | State of the art in global minutes-based accessibility to daily services; also a model for the write-up structure (measurement → global pattern → inequality). |
| `weiss2020healthcare` | Source of the friction surfaces (the demoted sensitivity engine, E.1) *and* the canonical global travel-time-to-healthcare map — cite for both. |
| `luo2003measures` | 2SFCA — the congestion adjustment's method source. |
| `luo2009enhanced` | E2SFCA distance-decay weighting — the kernel used inside depacc's catchment. |

### The everyday anchor (15-minute city)

| cite | supports |
|---|---|
| `moreno2021fifteenminute` | The 15-minute proximity norm anchoring the DLF inflection t0 = 15. |
| `papadopoulos2023compliance` | Review of how 15-minute-city compliance is measured — positions the everyday regime's choices (services, walk mode, thresholds) in that literature. |

### The cross-city design (space-for-time, scaling)

| cite | supports |
|---|---|
| `musso2026cities` | The design template: harmonised city definition, trajectories from the cross-sectional size gradient. Cite once, early, with the space-for-time qualifier (framing rule). |
| `bettencourt2007growth` | Urban scaling: log-log elasticity on population as the estimand — grounds H1/H2's functional form. |

### The everyday / emergency split (resilience framing)

| cite | supports |
|---|---|
| `sirenko2026heatwaves` | The empirical case that everyday vulnerability does not predict crisis-time resilience — i.e. everyday access and emergency capability are distinct regimes that must be measured separately. **The motivating citation for the two-regime design.** |
| `logan2020reframing` | Resilience *defined as* equitable access to essential services — the conceptual bridge from the equity results (H5/H6) to the resilience framing; supports reading the everyday regime as the resilience baseline. |
| `fan2022equality` | Equality of access and network resilience move together in population–facility networks — the compounding result (the same people deprived in both regimes) is the pathological case of this interplay. |
| `meerow2016defining` | Urban-resilience definitional anchor for the emergency-capability framing. |

### Emergency time-to-care benchmarks (the DCF anchors — PI direction: lower than the config's 45–60 min)

| cite | supports |
|---|---|
| `pons2005response` | The 8-minute EMS response-time criterion (urban cores) — the benchmark the ideal-urban anchor rests on. |
| `khan2026melbourne` | States the adopted framing verbatim: ideal 8-min response in dense urban cores vs realistic 10–15-min targets peri-urban/rural (citing Pons 2005 and WHO 2020). |
| `vo2020vulnerable` | Persistent low emergency-care accessibility concentrates in socially vulnerable regions — supports both the lower thresholds and the H5 vulnerability lens. |
| `nicholl2007distance` | Mortality rises with distance/time to emergency care — evidence for the DCF's *convexity*, independent of any specific threshold. |

### Statistics

| cite | supports |
|---|---|
| `cameron2008bootstrap` | Wild cluster bootstrap (all country-clustered scaling p's). |
| `mackinnon2023cluster` | The modern few-clusters practice guide — the referee-proofing companion to CGM 2008 at 24 country clusters. |
| `lakens2017equivalence` | TOST equivalence bounds (the emergency null, H1). |
| `simonsohn2020specification` | Specification curve (H2 robustness). |
| `rousseeuw1987silhouettes` | Silhouette (cluster k-selection, H4). |
| `hubert1985comparing` | Adjusted Rand index (stability, cluster-vs-region, H4). |
| `wagstaff1991measurement` | Concentration index (equity stage). |

### Data and software

| cite | supports |
|---|---|
| `schiavina2023ghspop` | GHS-POP 100 m population grid (the analysis grid). |
| `fink2022r5py` | r5py / R5 (the primary routing engine). |

Datasets with citation-format DOIs beyond these (Eurostat Census 2021
grid, GISCO URAU, OSM, national Tier-2 grids) are attributed per
`data/README.md`; journals normally take those as data-availability
attributions rather than bibliography entries.

## Decisions taken (PI, 2026-08)

- **Emergency thresholds: lower than the config's 45–60 min.** Anchor on
  EMS response benchmarks — ideal 8 min in dense urban cores, realistic
  10–15 min peri-urban/rural (`pons2005response`, `khan2026melbourne`,
  `vo2020vulnerable`, WHO 2020 pending identification).
  `nicholl2007distance` is kept as convexity evidence only. **The
  pipeline consequence is a real decision — see open question 1.**
- **Per-service t0 thresholds: not used.** The published baseline is the
  uniform t0 = 15 (`threshold_mode: "uniform"`); the per-service seeds
  stay config-internal and uncited. (Where they live, for reference:
  `config/deprivation.yaml → deprivation.everyday.per_service`, one
  block per service with a seed value and a `verify: TODO` source note;
  methods §3.1 describes the frequency-of-use rationale. None of them
  affects any published number.)
- **Resilience block**: `logan2020reframing` and `fan2022equality` added
  alongside `sirenko2026heatwaves` and `meerow2016defining`.
- **`macea2018attitudes`: in** (PI: important).
- **`mackinnon2023cluster`: added** as the few-clusters practice guide.

## Open questions for the PI

1. **What does the lower emergency anchor do to the pipeline?** The
   benchmarks (8 / 10–15 min) replace the 45–60 min window in the
   *justification*, but the shipped surfaces were computed with
   `lam = 1.8` "calibrated to ~45–60 min" and reported in multiples of
   g(45). Two options:
   - **(a) Re-anchor the reporting scale only** (`reference_time_min`
     45 → 15): division by a positive constant, so *every rank- and
     ratio-based result is unchanged exactly* — percentiles, typology,
     both Ginis, ρ, Jaccard, all inference tables. Only the reported
     emergency *levels* rescale (1.0 then means "the deprivation of
     arriving at the 15-min benchmark"). Cheap: config change + a
     deprivation-stage re-run from cached ODs, or an exact constant
     rescale of the level columns.
   - **(b) Recalibrate the curvature too** (solve `lam` from anchors in
     the 8–15 min window): the Ginis and level results move; per-service
     cell rankings are preserved (any strictly increasing g), but every
     level/inequality table and the spec curve need a full
     deprivation-stage + cross re-run. Note the current sensitivity sweep
     (λ ∈ 1.4–2.2) already brackets curvature uncertainty, and the
     emergency conclusions (no size gradient, size-flat Gini) hold across
     that whole range — so (b) is unlikely to change any claim, but it is
     a re-run of everything emergency-side.
   Recommendation: **(a)**, keeping λ = 1.8 as "form and curvature
   transferred from the DCF literature" (`cantillo2018discrete`,
   `delgadolindeman2019ambulance`) with the *benchmark* anchoring the
   reporting scale — and state in limitations that results are robust
   across λ 1.4–2.2. **Confirm (a) or (b).** Also: a
   `pop_share_beyond_emergency_15` level indicator does not exist yet
   (only 30/45/60) and would need the same deprivation-stage re-run —
   worth adding under either option, since the 10–15 min benchmark makes
   it the policy-relevant threshold share.
2. **Which WHO 2020 document?** `khan2026melbourne` cites "World Health
   Organization, 2020" for the EMS benchmarks; I could not identify the
   exact WHO publication from the abstract alone. **Please upload the
   Khan et al. PDF (or name the WHO document)** and I'll add a verified
   entry — until then WHO 2020 is deliberately absent from the .bib
   rather than guessed. The upload would also let me complete
   `khan2026melbourne`'s author list (currently "and others" past the
   first three, per the publisher's listing).
