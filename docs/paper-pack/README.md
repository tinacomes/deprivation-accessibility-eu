# Paper pack

Self-contained working materials for drafting the paper. Start with
`BRIEF.md` — it is the master briefing (claims, evidence map, binding
framing and phrasing rules, methods facts, limitations, skeleton) and
tells you what order to read everything else in.

```
paper-pack/
├── BRIEF.md          the master briefing — read first, rules are binding
├── data/             every table the claims cite (see BRIEF evidence map)
│   ├── cityplane.csv                the 67-city master table
│   ├── cities_descriptives.csv     per-city appendix table (Table 1 / SI)
│   ├── inference_*.csv             the citable statistical tests
│   ├── cluster_null*.csv, cityvector_clustered*.csv   clustering
│   ├── vulnerability*.csv          who-carries-it synthesis
│   ├── deprivation_vs_access.csv, desert_access_contrast.csv,
│   │   scaling_by_grade.csv        the deprivation-vs-access contrast
│   ├── specification_curve.csv, rank_agreement.csv, flip_cells.csv,
│   │   typology_share_envelope.csv                    robustness
│   └── scaling.csv, size_gradient.csv, regime_slope_difference.csv
└── figures/          the publication-shaped figure set (9 PNGs)
```

Companion documents in this repository:

- `docs/results-headlines.md` — headlines, the statistical-tests reading
  guide, the glossary (SI material).
- `methods.md` — authoritative methods (§4.4 = cross-city analyses).
- `docs/validation.md`, `docs/face-validation-hamburg.md` — E.2–E.5.
- `docs/evidence/depacc_results_evidence.docx` — the human-facing
  evidence document.
- Branch `depacc-results` — every persisted per-city table and map
  (per-city compounding maps for figure remakes live under
  `cities/<city>/figures/`).

Freshness: **final**. All 67 cities have completed routing (Paris last,
2026-08-14) and everything here was refreshed from that state — see
`BRIEF.md § Provenance` for which file came from CI, which was
recomputed locally, and which was reconstructed as a 67-city union.
