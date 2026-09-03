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
├── analysis_regional_structure.py
│                            revision-2 regional analyses (variance
│                            decomposition, dispersion, no-desert re-test,
│                            South split); writes five CSVs into the pack
├── _figstyle.py             shared style + data helpers for the figure scripts
├── make_fig_curves.py       Fig 1  the two deprivation functions (from config/)
├── make_fig_scaling.py      Fig 3  size vs mean deprivation and vs Gini
├── make_fig_map.py          Fig 4  the 67 cities by coverage grade and region
├── make_fig_cityplane.py    Fig 6  Gini plane by coverage grade
├── make_fig_region_strips.py Fig 7 regional strips by country code
├── make_fig_dep_vs_access.py Fig 2 deprivation vs access
├── city_coords.csv          city-centre coordinates for the map
├── tables/
│   ├── cities_descriptives.tex   SI per-city longtable (generated)
│   ├── city_gallery.tex          SI 67-map gallery (generated)
│   └── regional_*.tex, grade_by_region.tex, south_split.tex
│                                 SI regional-structure tables (generated)
└── figures/
    ├── main/                the 9 main-text figures
    │   ├── deprivation_curves.png        Fig 1  the two deprivation functions
    │   ├── dep_vs_access.png             Fig 2  deprivation vs access
    │   ├── scaling_elasticity.png        Fig 3  size: means (A) and Ginis (B)
    │   ├── scaling_by_coverage_grade.png Fig 5  coverage grades
    │   ├── city_map.png                  Fig 4  map of grades and regions
    │   ├── cityplane.png                 Fig 6  Gini plane by grade
    │   ├── region_strips.png             Fig 7  regional strips by country
    │   ├── compounding_gallery.png       Fig 8  spatial anatomy
    │   └── vulnerability_strata.png      Fig 9  who carries it
    └── appendix/            the SI figures
        ├── robustness_architecture.png   Fig S1
        ├── specification_curve.png       Fig S2
        ├── rho_ranked.png                Fig S3
        ├── size_gradient.png             Fig S4
        └── cities/                        the 67 per-city compounding maps
                                           (gallery)
```

Figures `dep_vs_access`, `deprivation_curves`, `scaling_elasticity`,
`city_map`, `cityplane` and `region_strips` are drawn by the `make_fig_*.py`
scripts from the pack tables (and `config/` for the curves); the others
are verbatim copies from `docs/paper-pack/figures/` (drawn by CI from the
final 67-city state). To refresh: re-run the pack, copy the CI figures,
re-run `analysis_regional_structure.py`, the `make_fig_*.py` scripts and
`make_includes.py`, then `make`.

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
