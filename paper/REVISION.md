# Revision protocol — round 1 (PI review, 2026-08-31)

Maps each review point to concrete edits, with acceptance checks. Source of
truth for numbers stays `docs/paper-pack/` (brief + data tables); nothing is
re-derived.

## R1 — Recentre the paper on deprivation ("what matters"), everyday vs emergency

**Critique.** The key contribution is deprivation; access/accessibility
studies are many. Make the paper about *what matters* and show the
differences between the regimes.

**Edits.**
1. The framework figure (`deprivation_curves.png`) moves from the Discussion
   to the head of the Results as **Fig. 1**: the two calibrated loss
   functions against the linear loss every minutes average implies. The
   paper's object (welfare burden, two different mathematical objects for
   two different kinds of need) is on the page before any regression.
2. Results opening rewritten so the level-vs-cost asymmetry is presented as
   the substantive claim about what matters (saturation because everyday
   needs substitute; escalation because emergency outcomes worsen), with
   all machinery moved to Methods (see R4).
3. Section 2.5 (deprivation vs access) becomes the closing argument of the
   Results, roughly tripled in length, with its own figure (see R5) and the
   desert-contrast table moved into it (it is the access-vs-deprivation
   contrast, so it lives there).
4. Abstract and introduction lead with the measurement-theory gap (uniform
   minutes discard welfare), and every access citation is positioned as the
   benchmark being extended.

**Check.** Read the abstract, the first intro paragraph, the Results
opening and 2.5 in sequence: each states the deprivation contribution
without leaning on access framing; the two regimes' difference is explicit
in each.

## R2 — Rewrite the abstract (and significance) in PNAS register

**Critique.** No references in the abstract, no colloquial examples; model
on the Helbing abstract.

**Note.** Network egress from this environment blocks pnas.org/doi.org, so
the Musso–Rybski–Helbing–Neffke (2026) abstract could not be fetched
verbatim. The genre conventions are encoded instead, cross-checked against
the other Helbing PNAS abstract in our bibliography (Bettencourt et al.
2007): (i) one or two sentences of broad context ending in an open problem;
(ii) a "Here we show/measure..." pivot naming the design and scale;
(iii) declarative results in logical order, few numbers, no hedging
clutter; (iv) a closing sentence on what the finding means for theory.
No citations, no examples, no rhetorical questions.

**Edits.** Abstract fully rewritten to that structure (≤250 words, zero
citations, zero colloquial examples). Significance statement rewritten
theory-first (50–120 words, no references).

**Check.** Word counts in range; `\citep` count in abstract = 0; no
example-style sentences ("Twenty-five minutes instead of twenty..."
deleted).

## R3 — Theory first; state of the art as benchmark

**Critique.** Advance theory, benchmark against the state of the art; what
we learn for urbanism, accessibility, resilience is core; practice second.

**Edits.**
1. Introduction extended with a background block (three short subsections'
   worth of prose, no subsection headings): (a) urban scaling theory and
   what it implies for service access, with its universality claim as the
   benchmark; (b) the accessibility/15-minute-city literature and the
   uniform-impedance assumption it rests on; (c) deprivation theory from
   humanitarian logistics and the resilience argument for treating everyday
   and crisis capability as distinct. Each ends in an explicit gap the
   paper fills; key concepts (deprivation level, deprivation cost,
   compounding, coverage) defined in the introduction.
2. Discussion restructured:
   - 3.1 robustness (kept, tightened, now referencing Fig. 1);
   - 3.2 **What the results change for theory** — three numbered
     contributions with named benchmarks: (i) agglomeration/scaling theory
     (returns to scale in welfare are regime-specific; inequality of
     welfare scales only in the everyday regime), (ii) accessibility and
     urbanism (impedance must be welfare-anchored; the 15-minute-city as an
     everyday-only doctrine; deserts and coverage grades as tail objects
     averages cannot represent), (iii) resilience theory (two capabilities,
     compounding as the coupling pathology);
   - 3.3 implications for planning and policy (short, second);
   - 3.4 limitations (unchanged content).

**Check.** 3.2 contains no policy sentences; 3.3 contains no theory
sentences; each contribution in 3.2 names the literature it revises.

## R4 — Disentangle Results from Methods

**Critique.** Results are confounded with methods.

**Edits.** The Results opening loses all mechanics: 2SFCA/congestion,
soft-minimum details, mid-rank percentiles, finite-fill, standardisation
guards move to (or stay only in) Materials and Methods. What remains in the
Results opening: what each indicator means for a reader (two short
paragraphs), the units, the two-sentence comparability discipline, sample
table, overview figures. The inferential conventions paragraph is
compressed to two sentences with a pointer to Methods.

**Check.** Grep the Results for method terms (`2SFCA`, `soft-min`,
`mid-rank`, `finite fill`, `kernel`): none present; each defined in
Methods.

## R5 — Expand 2.1, 2.4 and especially 2.5; figure for 2.5

**Edits.**
1. **2.1** gains: the interpretation of the elasticity in plain terms, the
   full influence battery (LOO, FE, Huber, median regression, desert
   exclusion), what the equivalence bound does and does not license, the
   paired-test logic, the descriptive access context (median walk times
   4–8 min per everyday service; 12 min drive to either emergency
   service), and the theoretical set-up it tests (scaling universality vs
   nationally planned emergency systems).
2. **2.4** gains: the median-split accounting identity in one sentence
   (why HH is the single free number), the continuous intensity and its
   anchors, threshold dominance (29.8 pp vs 1.4 pp; ~21×), regional
   compounding tests, reading rules for the maps (area vs population),
   and a fuller vulnerability treatment (harmonised vs national tiers,
   coverage gates, CEE/North depth, the elderly null stated as a result).
3. **2.5** roughly tripled: one paragraph per move (claims survive; better
   behaved outcome; deserts invisible), the desert table moved here, the
   coverage-grade level result folded in as the fourth move, and a new
   composed figure:
   - **new Fig. `dep_vs_access.png`** (generated by
     `make_fig_dep_vs_access.py` from `deprivation_vs_access.csv` and
     `desert_access_contrast.csv`; no new statistics, presentation of
     table values only): panel A, size elasticities of deprivation-based
     vs minutes-based outcomes with 95% CIs and R² annotations; panel B,
     the five deserts' ratio-to-sample under access (median minutes) vs
     deprivation cost, dumbbell form, parity line at 1.
4. 2.3 keeps the clustering/geography content; forward-references the
   desert table in 2.5.

**Check.** Section word counts: 2.1, 2.4 ≥ ~450 words, 2.5 ≥ ~550 words;
new figure renders, is referenced in text, and every plotted value traces
to the two CSVs.

## R6 — Cross-check pass (mandatory before push)

1. Every quoted number re-grepped against `docs/paper-pack/data/*.csv` or
   the brief/headlines files.
2. Prohibited-claims scan: no "proven flat"; no regional everyday-Gini
   claim; no European elderly claim; no unconditional emergency-Gini
   trend; no per-cell class readings; no absolute friction-engine levels;
   Box-Cox everyday-Gini exception named; slope×grade interaction never
   headlined.
3. Style scan: no `---` em-dashes in prose; no "not X, but Y"
   constructions; no rhetorical triplets; level/cost terminology strict
   ("deprivation cost" whenever an emergency level is quoted).
4. Abstract ≤250 words with 0 references; significance 50–120 words.
5. Clean compile: no undefined citations/references; overfull boxes < 5 pt.

## Open decisions for the PI (not blocking this round)

- **Title.** Kept as "The two geographies of urban deprivation: everyday
  services and emergency care in 67 European cities". Alternatives if a
  sharper deprivation-first signal is wanted: "What access misses: the two
  geographies of urban deprivation in Europe" or "Urban growth serves
  everyday needs and leaves emergency care behind".
- **Journal fit.** The revision is benchmarked to the PNAS register
  (abstract + significance + methods-at-end). If another venue is
  intended, section limits may need a second pass.
- The Musso et al. (2026) abstract should be checked once by a human
  against the rewritten abstract (egress block prevented fetching it
  here).
