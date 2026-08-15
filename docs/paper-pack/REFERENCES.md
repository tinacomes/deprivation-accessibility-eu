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
| `meerow2016defining` | Urban-resilience definitional anchor for the emergency-capability framing. |

### The clinical anchor (PROPOSED — see open questions)

| cite | supports |
|---|---|
| `nicholl2007distance` | Mortality rises with distance/time to emergency care — proposed empirical anchor for the DCF's 45–60 min calibration window. |

### Statistics

| cite | supports |
|---|---|
| `cameron2008bootstrap` | Wild cluster bootstrap (all country-clustered scaling p's). |
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

## Open questions for the PI

1. **Clinical anchor for the DCF (45–60 min).** The config says
   "calibrated to clinical time-to-care anchors" but names no source.
   Proposed: `nicholl2007distance` (mortality–distance gradient,
   UK ambulance cohort). Alternatives if you prefer: golden-hour trauma
   literature, or stroke/STEMI time-to-treatment guidelines. **Which?**
2. **Per-service t0 seeds.** `config/deprivation.yaml` seeds per-service
   thresholds from named standards (DE Apothekenbetriebsordnung, RCGP/NHS
   GP access, school catchment norms) all flagged `verify: TODO`. The
   published baseline uses uniform t0 = 15 so nothing cited depends on
   them — but if the per-service variant is mentioned in the SI, those
   standards need verified citations. **Cite the per-service variant, or
   keep it config-internal?**
3. **Resilience framing depth.** Currently `sirenko2026heatwaves` +
   `meerow2016defining`. If you want the discussion to engage the
   resilience literature more broadly (e.g. infrastructure-resilience or
   crisis-logistics lines from your group), name the papers and I'll
   verify and add them.
4. **Macea et al. 2018** (*Influence of attitudes and perceptions on
   deprivation cost functions*, Transp. Res. E 112:125–141) is the other
   Cantillo-line DCF paper; I left it out to keep the DCF block tight.
   **Include?**
5. **Wild-bootstrap small-cluster refinement.** With 24 clusters,
   `cameron2008bootstrap` suffices; if a referee pushes, MacKinnon &
   Webb's later work is the standard fallback — can add pre-emptively.
