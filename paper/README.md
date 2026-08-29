# Paper — The two geographies of urban deprivation

LaTeX draft of the manuscript, written from the master brief at
[`docs/paper-pack/BRIEF.md`](../docs/paper-pack/BRIEF.md) (final 67-city
state, re-anchored emergency scale). Every number in the text traces to a
table in `docs/paper-pack/data/` or to the `depacc-results` branch; the
claim → table pairing is the brief's evidence map, and the quoted numbers
are the ones `tools/audit_paper_pack.py` checks in CI.

## Layout

```
paper/
├── main.tex                 the manuscript (main text + Materials & Methods
│                            + Supplementary Information in one document)
├── main.pdf                 compiled output
├── references.bib           bibliography (paper copy of
│                            docs/paper-pack/references.bib with the
│                            editorial note fields stripped; the annotated
│                            master + claim map stay in docs/paper-pack/)
├── make_includes.py         regenerates tables/ from the paper-pack CSVs
├── tables/
│   ├── cities_descriptives.tex   SI per-city longtable (generated)
│   └── city_gallery.tex          SI 67-map gallery (generated)
└── figures/
    ├── main/                the 9 main-text figures
    │   ├── cityplane.png                 Fig 1  overview, all 67 cities
    │   ├── scaling_elasticity.png        Fig 2  H1 regime-specific scaling
    │   ├── specification_curve.png       Fig 3  H2 inequality scaling
    │   ├── region_strips.png             Fig 4  H3 regional structure
    │   ├── scaling_by_coverage_grade.png Fig 5  H4/H7 coverage grades
    │   ├── rho_ranked.png                Fig 6  H6 coupling
    │   ├── compounding_gallery.png       Fig 7  H6 spatial anatomy
    │   ├── vulnerability_strata.png      Fig 8  H5 who carries it
    │   └── deprivation_curves.png        Fig 9  the deprivation layer
    └── appendix/            the SI figures
        ├── robustness_architecture.png   Fig S1
        ├── size_gradient.png             Fig S2
        └── cities/                        the 67 per-city compounding maps
                                           (Figs S3+, gallery)
```

All figures are verbatim copies from `docs/paper-pack/figures/` (drawn by
CI from the final 67-city state); do not edit them here — refresh the pack
and re-copy instead.

## Build

```
cd paper
make            # latexmk -pdf main.tex
make includes   # regenerate tables/ after a paper-pack refresh
make clean
```

Requires TeX Live (`texlive-latex-base`, `-recommended`, `-extra`,
`texlive-fonts-recommended`) and `latexmk`.

## Editing rules (from the brief — binding)

- Cite only from `references.bib`; never introduce citations from memory.
  `docs/paper-pack/REFERENCES.md` maps each entry to the claim it supports.
- Every claim must trace to a file in `docs/paper-pack/data/` or on
  `depacc-results`. Re-run `tools/audit_paper_pack.py` after editing any
  claim.
- The framing and phrasing rules in `BRIEF.md` (level vs cost, the
  conditional emergency-Gini statement, gradient-not-types, space-for-time,
  the prohibited claims list) are binding on any revision.
