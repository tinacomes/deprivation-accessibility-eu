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

## The emergency anchor recalibration (analysis, 2026-08-15)

The PI's three-window reading — deprivation negligible below ~3–4 min
(`vo2020vulnerable`), the WHO-recommended 8-min response as an
intermediate mark, 15 min as the realistic upper threshold
(`khan2026melbourne`, `pons2005response`) — was checked against the DCF
mathematics. Three findings, exactly reproducible from
`DeprivationFunction` (box_cox, shift = 1):

1. **A "half-max at 8 min" calibration is mathematically impossible for
   a convex DCF.** Any curve through g(4)/g(15) = 0.10 and
   g(8)/g(15) = 0.50 has chord slopes 0.025 → 0.100 → 0.071 — the slope
   *falls* between the 8- and 15-min segments, i.e. the curve is concave
   there. Convexity (the defining property of an escalating deprivation
   cost, `holguinveras2013objective`) caps g(8)/g(15) at **0.427** when
   the 4-min level is 0.10. So the 8-min mark cannot play the role the
   15-min inflection plays for the everyday DLF; it enters as an
   intermediate benchmark, not a half-max anchor.
2. **The existing curve, re-anchored at g(15), already encodes the
   feasible three-window structure.** With λ = 1.8:
   g(3)/g(15) = 0.076, g(4)/g(15) = 0.117, g(8)/g(15) = 0.351 —
   negligible-to-small below 3–4 min, about a third of the threshold
   cost at the WHO-recommended 8, 1.0 at 15, convex escalation beyond
   (3.3× at 30 min, 6.7× at 45).
3. **Calibrating λ *from* the new anchors lands where the curve already
   is.** Solving g(4)/g(15) = 0.10 gives λ = 1.945; solving
   g(8)/g(15) = 1/3 gives λ = 1.891. Both a hair from the published 1.8
   and inside the sensitivity sweep (1.4–2.2), whose envelope is already
   published (`deprivation_sensitivity_summary.csv`) and under which
   every emergency conclusion holds.

Consequently **(a) — re-anchor the reporting scale at g(15), keep
λ = 1.8 — is not just feasible but internally consistent with the new
anchors**; (b) — re-solving λ from the anchors — moves it to ≈1.9, a
within-sweep change that alters no conclusion. Estimated effort (no
re-routing under either; the OD matrices are cached, λ and the anchor
enter only the deprivation stage):

- **(a)**: config change (`reference_time_min` 45 → 15, add 8- and
  15-min emergency threshold shares) + one Tier-1 batch dispatch
  (~2–4 h wall-clock, unattended: each city re-runs
  deprivation→divergence→equity→viz from cached matrices) + pack/doc
  refresh and audit re-run (~1–2 h). Every rank/ratio result —
  percentiles, typology, both Ginis, ρ, all inference tables — is
  *unchanged exactly*; emergency levels re-express as multiples of
  g(15) (× 6.73 relative to today's g(45) units).
- **(b)**: identical CI compute (~2–4 h), but every emergency-side
  number changes (levels, Ginis, spec curve, envelopes, clustering
  features), so add a full re-verification and rewrite of the headline
  documents — roughly one working day end-to-end, for third-decimal
  movements already bounded by the published λ-sweep.

**Travel-time semantics caveat (both options).** The emergency surface
is the *civilian free-flow drive time* to the nearest ED/ambulance
station: R5 car times are time-independent (no congestion; speeds from
the OSM network's attributes), and the matrices are reverse-routed
(station → cell — for ambulance response the substantively correct
direction, methods §7.1, measured car asymmetry median 1 min).
Response-time benchmarks additionally contain dispatch and turnout
(~1–2 min) but lights-and-siren travel is faster than civilian flow —
partially offsetting, unmodelled. And free-flow understates congested
urban-core times relative to the periphery, which is *conservative* for
the desert/periphery findings. State this when using the 8/15-min
benchmarks: they anchor the cost scale, they are not literal response
predictions.

## Open questions for the PI

1. **Confirm (a) or (b)** given the analysis above (recommendation: (a),
   with the three-window consistency stated in methods; optionally
   present λ = 1.9 as "anchor-solved" in the SI since it is
   within-sweep).
2. **Please upload `vo2020vulnerable` and `khan2026melbourne`** (the
   publisher sites are blocked from this environment): needed to quote
   the exact 3–4-min statement and window definitions, to identify
   which **WHO 2020** document the benchmark sentence cites (absent from
   the .bib until identified, not guessed), and to complete the Khan
   author list (currently "and others" past the first three).
